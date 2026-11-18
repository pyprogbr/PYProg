"""Conexão USB com rádios DMR da família MD-UV380 (Retevis RT3S).

O rádio entra em modo DFU (USB 0483:DF11) quando é ligado com o cabo conectado ao
computador. O protocolo é o mesmo usado por projetos livres como o dmrconfig:
comandos DFU com extensões do fabricante (0x91 = modo de programação, 0xA2 =
identificação, 0x21 = endereço).

Nesta versão o módulo só LÊ o rádio. Nada é gravado.
"""
import os
import sys
import time

VID, PID = 0x0483, 0xDF11
BLOCO = 1024
MEMSZ = 0xD0000                 # igual a dmr380.MEMSZ
ATE_BURACO = 256                # blocos 0..255 ficam em 0x000000; os demais a partir de 0x110000
DESLOCA = 832                   # (bloco 256 -> 1088 * 1024 = 0x110000)

# requisições e estados DFU
DNLOAD, UPLOAD, GETSTATUS, CLRSTATUS, GETSTATE, ABORT = 1, 2, 3, 4, 5, 6
PARA_RADIO, DO_RADIO = 0x21, 0xA1
dfuIDLE, dfuDNLOAD_IDLE, dfuUPLOAD_IDLE, dfuERROR, appIDLE = 2, 5, 9, 10, 0


class ErroUSB(Exception):
    pass


def nome_do_rádio(ident):
    """Nome comercial a partir da identificação que o rádio devolve."""
    i = (ident or "").upper()
    if "1701" in i:
        return f"Baofeng DM-1701 ({ident})"
    if "UV380" in i or "UV390" in i:
        return f"Retevis RT3S GPS / TYT {ident}"
    return ident or "desconhecido"


# --------------------------------------------------------------------- diagnóstico do Windows
def _dispositivos_windows():
    """Lista os dispositivos 0483:DF11 presentes, com o driver (serviço) de cada um."""
    if sys.platform != "win32":
        return []
    import ctypes
    from ctypes import wintypes
    sa = ctypes.WinDLL("setupapi", use_last_error=True)

    class SP_DEVINFO_DATA(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("ClassGuid", ctypes.c_byte * 16),
                    ("DevInst", wintypes.DWORD), ("Reserved", ctypes.c_void_p)]

    sa.SetupDiGetClassDevsW.restype = ctypes.c_void_p
    sa.SetupDiGetClassDevsW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD]
    sa.SetupDiEnumDeviceInfo.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(SP_DEVINFO_DATA)]
    sa.SetupDiGetDeviceRegistryPropertyW.argtypes = [ctypes.c_void_p, ctypes.POINTER(SP_DEVINFO_DATA),
                                                     wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                                                     ctypes.c_void_p, wintypes.DWORD,
                                                     ctypes.POINTER(wintypes.DWORD)]
    sa.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]
    DIGCF_PRESENT, DIGCF_ALLCLASSES = 0x2, 0x4
    h = sa.SetupDiGetClassDevsW(None, None, None, DIGCF_PRESENT | DIGCF_ALLCLASSES)
    if not h or h == ctypes.c_void_p(-1).value:
        return []
    out = []
    try:
        i = 0
        while True:
            d = SP_DEVINFO_DATA()
            d.cbSize = ctypes.sizeof(SP_DEVINFO_DATA)
            if not sa.SetupDiEnumDeviceInfo(h, i, ctypes.byref(d)):
                break
            i += 1

            def prop(n):
                buf = ctypes.create_unicode_buffer(2048)
                if sa.SetupDiGetDeviceRegistryPropertyW(h, ctypes.byref(d), n, None, buf,
                                                        ctypes.sizeof(buf), None):
                    return buf.value
                return ""
            hw = prop(1).upper()                         # SPDRP_HARDWAREID (só o primeiro da lista)
            if f"VID_{VID:04X}&PID_{PID:04X}" not in hw:
                continue
            out.append({"nome": prop(0xC) or prop(0), "servico": prop(4), "fabricante": prop(0xB),
                        "classe": prop(7)})
    finally:
        sa.SetupDiDestroyDeviceInfoList(h)
    return out


def _arquivos_windows():
    if sys.platform != "win32":
        return {}
    win = os.environ.get("SystemRoot", r"C:\Windows")
    return {"libusb0.dll (64 bits)": os.path.exists(os.path.join(win, "System32", "libusb0.dll")),
            "libusb0.sys": os.path.exists(os.path.join(win, "System32", "drivers", "libusb0.sys")),
            "STTub30.sys (driver da ST)": os.path.exists(os.path.join(win, "System32", "drivers", "STTub30.sys"))}


# --------------------------------------------------------------------- driver da ST (o que o CPS instala)
# O driver STTub30 não fala com a libusb. O PYProg conversa com ele direto, pelo mesmo pedido que a
# biblioteca da ST (STTubeDevice30.dll) usa: DeviceIoControl 0x222014 com uma estrutura de 20 bytes
# (função, direção, pedido, valor, índice, tamanho), seguida dos dados quando o envio é para o rádio.
GUID_DFU_ST = "{3FE809AB-FB91-4CB5-A643-69670D52366E}"
IOCTL_ST_CONTROLE = 0x222014
IOCTL_ST_CONFIGURACAO = 0x222010
FUNCAO_CLASSE_INTERFACE = 0x1B


def _caminhos_st():
    """Caminhos dos rádios que usam o driver da ST (interface DFU da ST, 0483:DF11)."""
    if sys.platform != "win32":
        return []
    import ctypes
    import uuid
    from ctypes import wintypes
    sa = ctypes.WinDLL("setupapi", use_last_error=True)

    class GUID(ctypes.Structure):
        _fields_ = [("d1", wintypes.DWORD), ("d2", wintypes.WORD), ("d3", wintypes.WORD), ("d4", ctypes.c_ubyte * 8)]

    class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("InterfaceClassGuid", GUID), ("Flags", wintypes.DWORD),
                    ("Reserved", ctypes.c_void_p)]
    g = GUID.from_buffer_copy(uuid.UUID(GUID_DFU_ST).bytes_le)
    sa.SetupDiGetClassDevsW.restype = ctypes.c_void_p
    sa.SetupDiGetClassDevsW.argtypes = [ctypes.POINTER(GUID), wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD]
    sa.SetupDiEnumDeviceInterfaces.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(GUID),
                                               wintypes.DWORD, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA)]
    sa.SetupDiGetDeviceInterfaceDetailW.argtypes = [ctypes.c_void_p, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
                                                    ctypes.c_void_p, wintypes.DWORD,
                                                    ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    sa.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]
    h = sa.SetupDiGetClassDevsW(ctypes.byref(g), None, None, 0x2 | 0x10)   # PRESENT | DEVICEINTERFACE
    if not h or h == ctypes.c_void_p(-1).value:
        return []
    out = []
    try:
        i = 0
        while True:
            d = SP_DEVICE_INTERFACE_DATA()
            d.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)
            if not sa.SetupDiEnumDeviceInterfaces(h, None, ctypes.byref(g), i, ctypes.byref(d)):
                break
            i += 1
            precisa = wintypes.DWORD(0)
            sa.SetupDiGetDeviceInterfaceDetailW(h, ctypes.byref(d), None, 0, ctypes.byref(precisa), None)
            buf = ctypes.create_string_buffer(precisa.value + 8)
            ctypes.c_uint32.from_buffer(buf).value = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
            if sa.SetupDiGetDeviceInterfaceDetailW(h, ctypes.byref(d), buf, len(buf), None, None):
                caminho = ctypes.wstring_at(ctypes.addressof(buf) + 4)
                if f"vid_{VID:04x}&pid_{PID:04x}" in caminho.lower():
                    out.append(caminho)
    finally:
        sa.SetupDiDestroyDeviceInfoList(h)
    return out


class DispositivoST:
    """Imita o ctrl_transfer do pyusb usando o driver da ST."""

    def __init__(self, caminho):
        import ctypes
        from ctypes import wintypes
        self._k = ctypes.WinDLL("kernel32", use_last_error=True)
        self._k.CreateFileW.restype = wintypes.HANDLE
        self._k.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        self._k.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                                            ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                                            ctypes.c_void_p]
        self._k.CloseHandle.argtypes = [wintypes.HANDLE]
        self.h = self._k.CreateFileW(caminho, 0xC0000000, 0, None, 3, 0, None)
        if not self.h or self.h == wintypes.HANDLE(-1).value:
            raise ErroUSB(f"O driver da ST não abriu o rádio (erro {ctypes.get_last_error()}).")
        try:                                   # configuração 0, interface 0, alternativa 0 (como o CPS)
            self._ioctl(IOCTL_ST_CONFIGURACAO, bytes(3), 0)
        except ErroUSB:
            pass

    def _ioctl(self, codigo, entrada, tam_saida):
        import ctypes
        from ctypes import wintypes
        ent = ctypes.create_string_buffer(bytes(entrada), len(entrada))
        sai = ctypes.create_string_buffer(max(tam_saida, 1))
        ret = wintypes.DWORD(0)
        ok = self._k.DeviceIoControl(self.h, codigo, ent, len(entrada), sai if tam_saida else None, tam_saida,
                                     ctypes.byref(ret), None)
        if not ok:
            raise ErroUSB(f"O rádio não respondeu pelo driver da ST (erro {ctypes.get_last_error()}).")
        return sai.raw[:ret.value]

    def ctrl_transfer(self, tipo, pedido, valor, indice, dados_ou_tam=None, timeout=None):
        import struct
        entrada = bool(tipo & 0x80)
        if entrada:
            n = int(dados_ou_tam or 0)
            rq = struct.pack("<H2xIBxHH2xI", FUNCAO_CLASSE_INTERFACE, 1, pedido, valor, indice, n)
            return self._ioctl(IOCTL_ST_CONTROLE, rq, n)
        dados = bytes(dados_ou_tam or b"")
        rq = struct.pack("<H2xIBxHH2xI", FUNCAO_CLASSE_INTERFACE, 0, pedido, valor, indice, len(dados))
        self._ioctl(IOCTL_ST_CONTROLE, rq + dados, 0)
        return len(dados)

    def fecha(self):
        if self.h:
            self._k.CloseHandle(self.h)
            self.h = None


# --------------------------------------------------------------------- acesso USB
def _backends():
    """Bibliotecas USB que o pyusb pode usar, na ordem de preferência."""
    out = []
    try:
        import usb.backend.libusb0 as b0
        b = b0.get_backend()
        if b:
            out.append(("libusb0 (libusb-win32)", b))
    except Exception:
        pass
    try:
        import usb.backend.libusb1 as b1
        b = None
        try:
            import libusb_package
            b = b1.get_backend(find_library=libusb_package.find_library)
        except Exception:
            b = b1.get_backend()
        if b:
            out.append(("libusb-1.0 (WinUSB)", b))
    except Exception:
        pass
    return out


class Radio:
    def __init__(self, dev, log):
        self.dev, self.log = dev, log

    # ---- DFU básico
    def _status(self):
        s = bytes(self.dev.ctrl_transfer(DO_RADIO, GETSTATUS, 0, 0, 6, timeout=3000))
        espera = s[1] | s[2] << 8 | s[3] << 16
        if espera:
            time.sleep(min(espera, 2000) / 1000)
        return s[4]

    def _estado(self):
        return bytes(self.dev.ctrl_transfer(DO_RADIO, GETSTATE, 0, 0, 1, timeout=3000))[0]

    def _ocioso(self, tentativas=50):
        for _ in range(tentativas):
            e = self._estado()
            if e == dfuIDLE:
                return
            if e == dfuERROR:
                self.dev.ctrl_transfer(PARA_RADIO, CLRSTATUS, 0, 0, None, timeout=3000)
            elif e in (dfuDNLOAD_IDLE, dfuUPLOAD_IDLE):
                self.dev.ctrl_transfer(PARA_RADIO, ABORT, 0, 0, None, timeout=3000)
            elif e == appIDLE:
                raise ErroUSB("O rádio não está em modo de programação. Desligue-o, conecte o cabo e ligue de novo.")
            else:
                self._status()
            time.sleep(0.02)
        raise ErroUSB(f"O rádio não respondeu como esperado (estado DFU {self._estado()}).")

    def _comando(self, dados):
        self.dev.ctrl_transfer(PARA_RADIO, DNLOAD, 0, 0, bytes(dados), timeout=3000)
        self._status()
        self._ocioso()

    def _endereco(self, a):
        self._comando([0x21, a & 0xFF, a >> 8 & 0xFF, a >> 16 & 0xFF, a >> 24 & 0xFF])

    def _upload(self, n, bloco=2, exato=True):
        d = bytes(self.dev.ctrl_transfer(DO_RADIO, UPLOAD, bloco, 0, n, timeout=5000))
        self._status()
        self._ocioso()
        if exato and len(d) != n:
            raise ErroUSB(f"O rádio mandou {len(d)} bytes; o esperado era {n}.")
        return d

    # ---- funções do rádio
    def entra(self):
        self._ocioso()
        self._comando([0x91, 0x01])            # modo de programação
        time.sleep(0.1)

    def identifica(self):
        self._comando([0xA2, 0x01])
        d = self._upload(64, 0, exato=False)    # o RT3S responde com 32 bytes
        return d.split(b"\x00")[0].split(b"\xff")[0].decode("ascii", "replace").strip()

    # Tamanho da resposta de cada comando de informação (o driver da ST devolve sempre o tamanho pedido,
    # completando com zeros; por isso o pedido já vai com o tamanho certo)
    TAM_INFO = {1: 32, 2: 4, 3: 24, 4: 8, 7: 16}

    def info(self, sub):
        """Comando de leitura de informações do rádio (0xA2, sub). Só leitura."""
        self._comando([0xA2, sub])
        n = self.TAM_INFO.get(sub, 64)
        return self._upload(n, 0, exato=False)[:n]

    def bloco_info(self):
        """Bloco de 256 bytes com os dados do rádio (modelo, faixas, data, série) que o CPS grava no
        cabeçalho do .rdt: respostas de A2 01 + 03 + 04 + 02 + 07, completadas com FF."""
        partes = [self.info(s) for s in (1, 3, 4, 2, 7)]
        d = b"".join(partes)
        if not d.startswith(b"MD-") and not d[:8].strip(b"\xff\x00"):
            return None
        return (d + b"\xff" * 256)[:256]

    def le_bloco(self, n):
        b = n + DESLOCA if n >= ATE_BURACO else n
        self._endereco(b * BLOCO)
        return self._upload(BLOCO)

    # ---- gravação (apaga setores de 64 KB e grava blocos de 1 KB, como o CPS e o dmrconfig)
    AREAS = ((0x000000, 0x040000), (0x110000, 0x1A0000))     # as duas áreas da programação no rádio

    def apaga_setor(self, endereco):
        a = endereco
        self.dev.ctrl_transfer(PARA_RADIO, DNLOAD, 0, 0,
                               bytes([0x41, a & 0xFF, a >> 8 & 0xFF, a >> 16 & 0xFF, a >> 24 & 0xFF]), timeout=10000)
        self._status()
        self._ocioso(tentativas=500)

    def grava_bloco(self, n, dados):
        if len(dados) != BLOCO:
            raise ErroUSB("Bloco com tamanho errado.")
        b = n + DESLOCA if n >= ATE_BURACO else n
        self._endereco(b * BLOCO)
        self.dev.ctrl_transfer(PARA_RADIO, DNLOAD, 2, 0, bytes(dados), timeout=10000)
        self._status()
        self._ocioso(tentativas=200)

    def grava_tudo(self, mem, progresso=None):
        if len(mem) != MEMSZ:
            raise ErroUSB("A programação não tem o tamanho esperado.")
        setores = [a for ini, fim in self.AREAS for a in range(ini, fim, 0x10000)]
        total = len(setores) + MEMSZ // BLOCO
        feito = 0
        for a in setores:
            self.apaga_setor(a)
            feito += 1
            if progresso:
                progresso(feito, total, "Apagando")
        for n in range(MEMSZ // BLOCO):
            self.grava_bloco(n, mem[n * BLOCO:(n + 1) * BLOCO])
            feito += 1
            if progresso:
                progresso(feito, total, "Gravando")

    def reinicia(self):
        """Faz o rádio sair do modo de programação e reiniciar (comando 0x91 0x05)."""
        try:
            self._ocioso()
            self.dev.ctrl_transfer(PARA_RADIO, DNLOAD, 0, 0, bytes([0x91, 0x05]), timeout=3000)
            self._status()
        except Exception:
            pass        # o rádio reinicia e a conexão cai: é o esperado

    def le_tudo(self, progresso=None, para=lambda: False):
        mem = bytearray()
        total = MEMSZ // BLOCO
        for n in range(total):
            if para():
                raise ErroUSB("Leitura cancelada.")
            mem += self.le_bloco(n)
            if progresso:
                progresso(n + 1, total)
        return bytes(mem)


def conecta(log=print):
    """Abre o rádio em modo DFU. Devolve (Radio, nome do caminho usado)."""
    tentativas = []
    try:
        import usb.core
        import usb.util
        backends = _backends()
    except ImportError:
        backends = []
        tentativas.append("biblioteca USB (pyusb) não encontrada")
    for nome, b in backends:
        try:
            dev = usb.core.find(idVendor=VID, idProduct=PID, backend=b)
        except Exception as e:
            tentativas.append(f"{nome}: {e}")
            continue
        if dev is None:
            tentativas.append(f"{nome}: rádio não encontrado por este caminho")
            continue
        try:
            try:
                dev.set_configuration()
            except Exception as e:                 # alguns drivers já deixam configurado
                log(f"  ({nome}) set_configuration: {e}")
            usb.util.claim_interface(dev, 0)
            return Radio(dev, log), nome
        except Exception as e:
            tentativas.append(f"{nome}: {e}")
    # Driver da ST, instalado pelo CPS: não precisa trocar o driver com o Zadig
    for caminho in _caminhos_st():
        try:
            return Radio(DispositivoST(caminho), log), "driver da ST"
        except Exception as e:
            tentativas.append(f"driver da ST: {e}")
    if not tentativas:
        tentativas.append("nenhuma biblioteca USB (libusb0 ou libusb-1.0) pôde ser carregada")
    raise ErroUSB("O rádio não foi encontrado no USB. Confira se o cabo está conectado e o rádio ligado, e "
                  "feche outros programas que estejam usando o rádio.\n\nDetalhes:\n"
                  + "\n".join("  - " + t for t in tentativas))


def solta(radio):
    if isinstance(radio.dev, DispositivoST):
        radio.dev.fecha()
        return
    try:
        import usb.util
        usb.util.release_interface(radio.dev, 0)
        usb.util.dispose_resources(radio.dev)
    except Exception:
        pass


def diagnostico(log=print, ler_um_bloco=True):
    """Relatório do teste de conexão. Devolve True se conseguiu ler o rádio."""
    log(f"Sistema: {sys.platform}, Python {sys.version.split()[0]} "
        f"({'64' if sys.maxsize > 2**32 else '32'} bits)")
    devs = _dispositivos_windows()
    if sys.platform == "win32":
        if devs:
            for d in devs:
                log(f"Rádio no Windows: {d['nome']} | driver: {d['servico'] or '(nenhum)'} | "
                    f"fornecedor: {d['fabricante']} | classe: {d['classe']}")
        else:
            log("O Windows não mostra nenhum aparelho USB 0483:DF11 conectado agora.")
        for k, v in _arquivos_windows().items():
            log(f"{k}: {'presente' if v else 'ausente'}")
    if sys.platform == "win32":
        log(f"Rádios pelo driver da ST: {len(_caminhos_st())}")
    bks = _backends()
    log("Bibliotecas USB carregadas: " + (", ".join(n for n, _ in bks) or "nenhuma"))
    try:
        r, caminho = conecta(log)
    except ErroUSB as e:
        log(str(e))
        return False
    log(f"Rádio aberto por: {caminho}")
    entrou = False
    try:
        r.entra()
        entrou = True
        ident = r.identifica()
        log(f"Identificação do rádio: {ident!r}: {nome_do_rádio(ident)}")
        # Respostas dos comandos de informação (para montar o cabeçalho do .rdt igual ao do CPS)
        for sub in (1, 2, 3, 4, 7):
            try:
                d = r.info(sub)
                log(f"Info A2 {sub:02X} ({len(d)} bytes): {d.hex()}")
            except Exception as e:
                log(f"Info A2 {sub:02X}: falhou ({type(e).__name__}: {e})")
                try:
                    r._ocioso()
                except Exception:
                    pass
        if ler_um_bloco:
            b = r.le_bloco(8)                                    # 0x2000: início dos ajustes gerais
            log(f"Leitura de teste (1 KB): OK, {sum(1 for x in b if x not in (0, 0xFF))} bytes com dados.")
        return True
    except Exception as e:
        log(f"Falha na comunicação: {type(e).__name__}: {e}")
        return False
    finally:
        if entrou:
            r.reinicia()         # tira o rádio da tela de programação
        solta(r)

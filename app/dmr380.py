# -*- coding: utf-8 -*-
"""
Retevis RT3S (TYT MD-UV380/UV390) e Baofeng DM-1701 (Retevis RT84): arquivo .rdt do
programa oficial (CPS), para ver e reorganizar canais e zonas.

O mapa de memória segue o dmrconfig, de Serge Vakulenko (licença Apache 2.0), arquivo
uv380.c: os dois rádios usam o mesmo mapa. A leitura e a gravação no rádio continuam
pelo CPS: o PYProg só organiza o arquivo.

Nestes rádios, as zonas e as listas de varredura guardam o NÚMERO de cada canal. Por isso,
ao mudar a ordem dos canais, todas essas referências são atualizadas junto, e cada zona
continua com os mesmos canais.
"""
from __future__ import annotations

import os
import struct
import tempfile

MEMSZ = 0xD0000
CAB_RDT = 0x225          # cabeçalho DfuSe do arquivo .rdt
RODAPE_MEIO = 0x10       # 16 bytes entre as duas partes da memória no .rdt
TAM_RDT = MEMSZ + CAB_RDT + RODAPE_MEIO
TOTAL_CANAIS = 3000
TOTAL_ZONAS = 250
TOTAL_VARREDURAS = 250
TOTAL_CONTATOS = 10000
OFF_CANAIS = 0x40000
OFF_ZONAS = 0x149E0
OFF_ZONAS_EXT = 0x31000
OFF_VARREDURA = 0x18860
OFF_CONTATOS = 0x70000
TAM_CANAL = 64
MEMBROS_ZONA = 64        # 16 na zona + 48 na extensão (lado A); lado B com 64


class ErroDMR(Exception):
    pass


def _txt(b):
    s = b.decode("utf-16-le", "replace")
    return s.split("\x00")[0].replace("￿", "")


def _valido(b):
    v = struct.unpack_from("<H", b, 0)[0]
    return v not in (0, 0xFFFF)


def _bcd(v):
    try:
        return int(f"{v:08x}") * 10
    except ValueError:
        return 0


def _tom(v):
    if v in (0xFFFF, 0):
        return ""
    tag = v >> 14
    a, b, c, d = (v >> 12) & 3, (v >> 8) & 15, (v >> 4) & 15, v & 15
    if tag == 2:
        return f"D{b}{c}{d}N"
    if tag == 3:
        return f"D{b}{c}{d}I"
    return f"{a}{b}{c}.{d}" if a else f"{b}{c}.{d}"


def mhz(hz):
    if not hz:
        return ""
    t = f"{hz / 1e6:.5f}".rstrip("0")
    inteiro, dec = t.split(".")
    return f"{inteiro}.{dec.ljust(4, '0')}"


class Codeplug:
    def __init__(self, mem: bytes, cab=b"", meio=b"", formato="img"):
        if len(mem) != MEMSZ:
            raise ErroDMR("Arquivo com tamanho inesperado para este rádio.")
        self.mem = bytearray(mem)
        self.cab, self.meio, self.formato = cab, meio, formato

    # ------------------------------------------------------------- arquivo
    @classmethod
    def abre(cls, caminho):
        with open(caminho, "rb") as f:
            d = f.read()
        if len(d) == TAM_RDT and d.startswith(b"DfuSe"):
            mem = d[CAB_RDT:CAB_RDT + 0x40000] + d[CAB_RDT + 0x40000 + RODAPE_MEIO:]
            return cls(mem, d[:CAB_RDT], d[CAB_RDT + 0x40000:CAB_RDT + 0x40000 + RODAPE_MEIO], "rdt")
        if len(d) == MEMSZ:
            return cls(d, formato="img")
        raise ErroDMR("Este arquivo não é um .rdt do RT3S/MD-UV380 (tamanho "
                      f"{len(d)} bytes; o esperado é {TAM_RDT}).")

    def bytes_arquivo(self):
        m = bytes(self.mem)
        if self.formato == "rdt":
            return self.cab + m[:0x40000] + self.meio + m[0x40000:]
        return m

    def salva(self, caminho):
        pasta = os.path.dirname(os.path.abspath(caminho))
        fd, tmp = tempfile.mkstemp(prefix=".pyprog_", dir=pasta)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(self.bytes_arquivo())
            os.replace(tmp, caminho)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def imagem(self):
        return bytes(self.mem)

    # -------------------------------------------------------------- canais
    def _canal(self, n):                 # n de 1 a 3000
        o = OFF_CANAIS + (n - 1) * TAM_CANAL
        return self.mem[o:o + TAM_CANAL]

    def usado(self, n):
        return _valido(self._canal(n)[32:])

    def usados(self):
        return [n for n in range(1, TOTAL_CANAIS + 1) if self.usado(n)]

    def contato(self, i):
        if not 1 <= i <= TOTAL_CONTATOS:
            return ""
        o = OFF_CONTATOS + (i - 1) * 36
        return _txt(self.mem[o + 4:o + 36])

    def canal(self, n):
        c = self._canal(n)
        if not _valido(c[32:]):
            return None
        rx, tx = struct.unpack_from("<II", c, 16)
        modo = c[0] & 3
        digital = modo == 2
        pot = {3: "Alta", 2: "Média", 0: "Baixa"}.get(c[30] & 3, "")
        return {
            "numero": n, "nome": _txt(c[32:]), "rx": _bcd(rx), "tx": _bcd(tx),
            "modo": "Digital" if digital else "Analógico",
            "cc": str((c[1] >> 4) & 15) if digital else "",
            "slot": str((c[1] >> 2) & 3) if digital else "",
            "contato": self.contato(struct.unpack_from("<H", c, 6)[0]) if digital else "",
            "tom_rx": "" if digital else _tom(struct.unpack_from("<H", c, 24)[0]),
            "tom_tx": "" if digital else _tom(struct.unpack_from("<H", c, 26)[0]),
            "potencia": pot,
            "so_rx": bool(c[1] & 0x02),
            "varredura": self.nome_varredura(c[11]),
        }

    # --------------------------------------------------------------- zonas
    def _zona_off(self, z):
        return OFF_ZONAS + z * 64

    def zona_usada(self, z):
        return _valido(self.mem[self._zona_off(z):self._zona_off(z) + 2])

    def nome_zona(self, z):
        o = self._zona_off(z)
        return _txt(self.mem[o:o + 32])

    def zonas(self):
        return [z for z in range(TOTAL_ZONAS) if self.zona_usada(z)]

    def membros(self, z, lado="A"):
        """Canais da zona na ordem do rádio (números de 1 a 3000)."""
        if lado == "A":
            o = self._zona_off(z) + 32
            v = list(struct.unpack_from("<16H", self.mem, o))
            v += list(struct.unpack_from("<48H", self.mem, OFF_ZONAS_EXT + z * 224))
        else:
            v = list(struct.unpack_from("<64H", self.mem, OFF_ZONAS_EXT + z * 224 + 96))
        out = []
        for x in v:
            if x in (0, 0xFFFF):
                break
            out.append(x)
        return out

    def _grava_membros(self, z, lado, lista):
        lista = list(lista)[:MEMBROS_ZONA]
        v = lista + [0] * (MEMBROS_ZONA - len(lista))
        if lado == "A":
            struct.pack_into("<16H", self.mem, self._zona_off(z) + 32, *v[:16])
            struct.pack_into("<48H", self.mem, OFF_ZONAS_EXT + z * 224, *v[16:])
        else:
            struct.pack_into("<64H", self.mem, OFF_ZONAS_EXT + z * 224 + 96, *v)

    def reordena_zona(self, z, nova, lado="A"):
        """Nova ordem dos canais de um lado da zona (os mesmos canais). Os lados A e B são
        independentes, como no CPS."""
        if sorted(nova) != sorted(self.membros(z, lado)):
            raise ErroDMR("A nova ordem da zona precisa ter os mesmos canais.")
        self._grava_membros(z, lado, nova)

    def copia_lado(self, z, de="A", para="B"):
        self._grava_membros(z, para, self.membros(z, de))

    # ------------------------------------------------------ listas de varredura
    def nome_varredura(self, i):
        if not 1 <= i <= TOTAL_VARREDURAS:
            return ""
        o = OFF_VARREDURA + (i - 1) * 104
        return _txt(self.mem[o:o + 32]) if _valido(self.mem[o:o + 2]) else ""

    # ---------------------------------------------------------- reorganizar
    def aplica_ordem(self, ordem):
        """ordem[k] = número antigo do canal que vai para a posição k+1 (None = vazio).
        Os 64 bytes de cada canal vão inteiros, e as zonas (lados A e B) e as listas de
        varredura passam a apontar para os números novos. Retorna {antigo: novo}."""
        antigos = {n: bytes(self._canal(n)) for n in range(1, TOTAL_CANAIS + 1) if self.usado(n)}
        vazio = b"\xff" * TAM_CANAL
        mapa = {}
        for k in range(TOTAL_CANAIS):
            velho = ordem[k] if k < len(ordem) else None
            o = OFF_CANAIS + k * TAM_CANAL
            if velho is not None and velho in antigos:
                self.mem[o:o + TAM_CANAL] = antigos[velho]
                mapa[velho] = k + 1
            elif (k + 1) in antigos or _valido(self.mem[o + 32:o + 34]):
                self.mem[o:o + TAM_CANAL] = vazio
        self._remapeia(mapa)
        return mapa

    def _novo(self, mapa, v):
        if v in (0, 0xFFFF):
            return v
        return mapa.get(v, v)

    def _remapeia(self, mapa):
        if all(a == b for a, b in mapa.items()):
            return
        for z in range(TOTAL_ZONAS):
            if not self.zona_usada(z):
                continue
            for lado in ("A", "B"):
                m = self.membros(z, lado)
                if m:
                    self._grava_membros(z, lado, [self._novo(mapa, x) for x in m])
        for i in range(TOTAL_VARREDURAS):
            o = OFF_VARREDURA + i * 104
            if not _valido(self.mem[o:o + 2]):
                continue
            p1, p2, txd = struct.unpack_from("<3H", self.mem, o + 32)
            struct.pack_into("<3H", self.mem, o + 32, self._novo(mapa, p1), self._novo(mapa, p2),
                             self._novo(mapa, txd))
            mem = struct.unpack_from("<31H", self.mem, o + 42)
            struct.pack_into("<31H", self.mem, o + 42, *[self._novo(mapa, x) for x in mem])

    def ordena(self, por="nome", por_modo=False):
        """por: "nome" ou "frequencia"; por_modo: analógicos primeiro, depois digitais, cada grupo na ordem pedida."""
        canais = [self.canal(n) for n in self.usados()]

        def modo(c):
            return (c["modo"] == "Digital",) if por_modo else ()
        if por == "nome":
            canais.sort(key=lambda c: modo(c) + (c["nome"].casefold() == "", c["nome"].casefold(), c["rx"],
                                                 c["numero"]))
        else:
            canais.sort(key=lambda c: modo(c) + (c["rx"], c["nome"].casefold(), c["numero"]))
        ordem = [c["numero"] for c in canais]
        if ordem == list(range(1, len(ordem) + 1)):
            return {n: n for n in ordem}
        return self.aplica_ordem(ordem)

    def move(self, numeros, destino, depois=False):
        import arrastar
        ordem = list(range(1, TOTAL_CANAIS + 1))
        nova = arrastar.move_bloco(ordem, numeros, destino, depois)
        if nova == ordem:
            return {}
        return self.aplica_ordem(nova)

    def ordena_zona(self, z, por="nome", por_modo=False, lado="A"):
        m = self.membros(z, lado)
        cs = {n: self.canal(n) or {} for n in m}

        def modo(n):
            return (cs[n].get("modo") == "Digital",) if por_modo else ()
        if por == "nome":
            nova = sorted(m, key=lambda n: modo(n) + (cs[n].get("nome", "").casefold(), cs[n].get("rx", 0)))
        else:
            nova = sorted(m, key=lambda n: modo(n) + (cs[n].get("rx", 0), cs[n].get("nome", "").casefold()))
        self.reordena_zona(z, nova, lado)


# =============================================================================== edição
OFF_GRUPOS = 0x0EC20
OFF_MENSAGENS = 0x02180
TOTAL_GRUPOS = 250
TOTAL_MENSAGENS = 50
TAM_MENSAGEM = 144

POTENCIAS = {"Baixa": 0, "Média": 2, "Alta": 3}
LARGURAS = {"12,5 kHz": 0, "20 kHz": 1, "25 kHz": 2}
ADMISSAO = ["Sempre", "Canal livre", "Tom correto", "Color code"]
PRIVACIDADE = ["Nenhuma", "Básica", "Avançada"]
TIPOS_CONTATO = {"Grupo": 1, "Privada": 2, "Todos": 3}
FAIXAS = [(136.0, 174.0), (400.0, 480.0)]

# Canal novo: valores do dmrconfig (erase_channel), com os bits fixos que o CPS grava
# ao importar canais (byte 3 bits 4 e 2, byte 4 bit 3, byte 5 bits 3 e 2)
_MODELO_CANAL = (bytes([0x61, 0x14, 0x00, 0xF4, 0x2C, 0xCC, 0, 0, 60 // 15, 0, 0, 0, 0, 0, 0, 1])
                 + struct.pack("<IIHH", 0x40000000, 0x40000000, 0xFFFF, 0xFFFF)
                 + bytes([0, 0, 0xFF, 0xFF]) + b"\x00" * 32)


def _poe_txt(buf, off, texto, n):
    b = texto.encode("utf-16-le")[:2 * n]
    buf[off:off + 2 * n] = b + b"\x00" * (2 * n - len(b))


def hz_bcd(hz):
    d = int(round(hz / 10))
    if not 0 <= d <= 99999999:
        raise ErroDMR("Frequência inválida.")
    return int(f"{d:08d}", 16)


def le_hz(txt):
    t = str(txt).strip().replace(",", ".")
    if not t:
        raise ErroDMR("Informe a frequência.")
    try:
        v = float(t)
    except ValueError as e:
        raise ErroDMR(f"Frequência inválida: {txt}") from e
    hz = int(round(v * 1e6))
    if not any(a * 1e6 <= hz <= b * 1e6 for a, b in FAIXAS):
        raise ErroDMR(f"{t} MHz está fora das faixas do rádio (136 a 174 e 400 a 480 MHz).")
    return hz


def tom_bin(txt):
    """'' -> desligado; '88.5' -> CTCSS; 'D023N' / 'D023I' -> DCS."""
    t = str(txt or "").strip().upper().replace(",", ".")
    if t in ("", "-", "NENHUM", "DESLIGADO"):
        return 0xFFFF
    if t.startswith("D"):
        inv = t.endswith("I")
        num = t[1:].rstrip("NI")
        if not num.isdigit() or len(num) > 3:
            raise ErroDMR(f"Código DCS inválido: {txt}")
        n = int(num)
        return (3 if inv else 2) << 14 | (n // 100) << 8 | (n // 10 % 10) << 4 | (n % 10)
    try:
        v = int(round(float(t) * 10))
    except ValueError as e:
        raise ErroDMR(f"Tom inválido: {txt}") from e
    if not 600 <= v <= 2600:
        raise ErroDMR(f"Tom CTCSS inválido: {txt}")
    return (v // 1000) << 12 | (v // 100 % 10) << 8 | (v // 10 % 10) << 4 | (v % 10)


# Demais campos do canal, mapeados com arquivos salvos e importados pelo CPS.
# chave: (rótulo, quadro, byte, bit, largura, opções {valor: rótulo} | "inv" | None | ("num", máx))
_REF = {0: "Baixa", 1: "Média", 2: "Alta"}
_SINAL = {0: "Desligado", 1: "DTMF-1", 2: "DTMF-2", 3: "DTMF-3", 4: "DTMF-4"}
EXTRAS_CANAL = {
    "ref_rx": ("Referência de RX", "mais", 3, 0, 2, _REF),
    "ref_tx": ("Referência de TX", "mais", 4, 0, 2, _REF),
    "rekey": ("Espera após o TOT (s)", "mais", 9, 0, 8, ("num", 255)),
    "lone_worker": ("Lone worker", "mais", 0, 7, 1, None),
    "talkaround": ("Permitir talkaround", "mais", 1, 0, 1, None),
    "envia_gps": ("Enviar dados do GPS", "mais", 31, 0, 1, "inv"),
    "recebe_gps": ("Receber dados do GPS", "mais", 31, 1, 1, "inv"),
    "em_chamada": ("Durante a chamada", "dig", 5, 4, 2, {0: "Sempre", 1: "Seguir a admissão", 2: "Interromper TX"}),
    "emergencia": ("Sistema de emergência", "dig", 10, 0, 8, ("num", 32)),
    "gps": ("Sistema de GPS", "dig", 13, 0, 8, ("num", 16)),
    "priv_confirma": ("Confirmar chamada privada", "dig", 2, 6, 1, None),
    "dados_confirma": ("Confirmar chamada de dados", "dig", 2, 7, 1, None),
    "alarme_ack": ("Confirmar alarme de emergência", "dig", 3, 3, 1, None),
    "interrupcao": ("Permitir interrupção", "dig", 31, 2, 1, "inv"),
    "dcdm": ("DCDM", "dig", 31, 3, 1, "inv"),
    "sinal_rx": ("Sinalização de RX", "ana", 28, 0, 8, _SINAL),
    "sinal_tx": ("Sinalização de TX", "ana", 29, 0, 8, _SINAL),
    "qt_reverso": ("QT reverso", "ana", 5, 0, 2, {0: "180°", 1: "120°"}),
    "nao_qt": ("Frequência de corte sem QT", "ana", 5, 6, 2, {0: "259,2 Hz", 1: "55,2 Hz", 3: "Nenhuma"}),
    "ptt_id": ("Mostrar o PTT ID", "ana", 3, 7, 1, "inv"),
    "reverse_burst": ("Reverse burst / código de corte", "ana", 4, 2, 1, None),
}
for _i in range(8):
    EXTRAS_CANAL[f"decode{_i + 1}"] = (f"Decode {_i + 1}", "decode", 14, _i, 1, None)


def _le_extra(c, k):
    _, _, b, pos, larg, op = EXTRAS_CANAL[k]
    v = c[b] >> pos & ((1 << larg) - 1)
    if op is None:
        return bool(v)
    if op == "inv":
        return not v
    if isinstance(op, tuple):
        return v
    return op.get(v, f"Valor {v}")


def _grava_extra(c, k, valor):
    rot, _, b, pos, larg, op = EXTRAS_CANAL[k]
    if valor == _le_extra(c, k):
        return
    if op is None:
        v = int(bool(valor))
    elif op == "inv":
        v = int(not valor)
    elif isinstance(op, tuple):
        try:
            v = int(valor)
        except (TypeError, ValueError) as e:
            raise ErroDMR(f"{rot}: informe um número.") from e
        if not 0 <= v <= op[1]:
            raise ErroDMR(f"{rot}: de 0 a {op[1]}.")
    else:
        v = next((x for x, t in op.items() if t == valor), None)
        if v is None:
            raise ErroDMR(f"{rot}: opção inválida.")
    c[b] = _bits(c[b], pos, larg, v)


def _campos_canal(c):
    rx, tx = struct.unpack_from("<II", c, 16)
    return {k: _le_extra(c, k) for k in EXTRAS_CANAL} | {
        "nome": _txt(c[32:]), "modo": "Digital" if c[0] & 3 == 2 else "Analógico",
        "rx": _bcd(rx), "tx": _bcd(tx),
        "largura": {v: k for k, v in LARGURAS.items()}.get((c[0] >> 2) & 3, "12,5 kHz"),
        "autoscan": bool(c[0] & 0x10), "so_rx": bool(c[1] & 0x02),
        "slot": (c[1] >> 2) & 3 or 1, "cc": (c[1] >> 4) & 15,
        "privacidade": PRIVACIDADE[min(2, (c[2] >> 4) & 3)], "privacidade_n": (c[2] & 15) + 1,
        "vox": bool(c[4] & 0x10), "admissao": ADMISSAO[(c[4] >> 6) & 3],
        "contato": struct.unpack_from("<H", c, 6)[0], "tot": (c[8] & 0x3F) * 15,
        "varredura": c[11], "grupo": c[12], "squelch": c[15],
        "tom_rx": _tom(struct.unpack_from("<H", c, 24)[0]), "tom_tx": _tom(struct.unpack_from("<H", c, 26)[0]),
        "potencia": {v: k for k, v in POTENCIAS.items()}.get(c[30] & 3, "Alta"),
    }


def _bits(v, pos, larg, x):
    m = ((1 << larg) - 1) << pos
    return (v & ~m) | ((int(x) << pos) & m)


class _Edicao:
    """Métodos de edição misturados no Codeplug (canais, zonas, varreduras, contatos, grupos, mensagens)."""

    # ------------------------------------------------------------------- canais
    def campos_canal(self, n):
        return _campos_canal(self._canal(n)) if self.usado(n) else None

    def canal_livre(self, depois=0):
        for n in list(range(depois + 1, TOTAL_CANAIS + 1)) + list(range(1, depois + 1)):
            if not self.usado(n):
                return n
        raise ErroDMR("Não há posição livre: o rádio aceita 3000 canais.")

    def campos_vfo(self, lado):
        o = OFF_VFO[lado]
        return _campos_canal(bytes(self.mem[o:o + TAM_CANAL])) | {"nome": f"VFO {lado}"}

    def grava_vfo(self, lado, f):
        self.grava_canal(0, f, vfo=lado)

    def grava_canal(self, n, f, vfo=None):
        """f: dicionário como o de campos_canal. Bits que o PYProg não mostra são mantidos."""
        o = OFF_VFO[vfo] if vfo else OFF_CANAIS + (n - 1) * TAM_CANAL
        c = bytearray(self.mem[o:o + TAM_CANAL]) if (vfo or self.usado(n)) else bytearray(_MODELO_CANAL)
        nome = str(f["nome"])
        if not vfo and not nome.strip():
            raise ErroDMR("Dê um nome ao canal.")
        if len(nome) > 16:
            raise ErroDMR("O nome pode ter no máximo 16 letras.")
        digital = f["modo"] == "Digital"
        c[0] = _bits(c[0], 0, 2, 2 if digital else 1)
        c[0] = _bits(c[0], 2, 2, LARGURAS.get(f.get("largura"), 0))
        c[0] = _bits(c[0], 4, 1, f.get("autoscan", False))
        c[1] = _bits(c[1], 1, 1, f.get("so_rx", False))
        c[1] = _bits(c[1], 2, 2, int(f.get("slot", 1)) if int(f.get("slot", 1)) in (1, 2) else 1)
        cc = int(f.get("cc", 1))
        if not 0 <= cc <= 15:
            raise ErroDMR("Color code vai de 0 a 15.")
        c[1] = _bits(c[1], 4, 4, cc)
        priv = PRIVACIDADE.index(f.get("privacidade", "Nenhuma"))
        c[2] = _bits(c[2], 4, 2, priv)
        c[2] = _bits(c[2], 0, 4, max(1, min(16, int(f.get("privacidade_n", 1)))) - 1)
        c[4] = _bits(c[4], 4, 1, f.get("vox", False))
        c[4] = _bits(c[4], 6, 2, ADMISSAO.index(f.get("admissao", "Sempre")))
        struct.pack_into("<H", c, 6, int(f.get("contato", 0)) if digital else int(f.get("contato", 0)))
        tot = int(f.get("tot", 60))
        c[8] = _bits(c[8], 0, 6, max(0, min(37, tot // 15)))
        c[11] = max(0, min(TOTAL_VARREDURAS, int(f.get("varredura", 0))))
        c[12] = max(0, min(TOTAL_GRUPOS, int(f.get("grupo", 0))))
        c[15] = max(0, min(9, int(f.get("squelch", 1))))
        rx = int(f["rx"])
        tx = int(f.get("tx") or rx)
        struct.pack_into("<II", c, 16, hz_bcd(rx), hz_bcd(tx))
        struct.pack_into("<HH", c, 24, tom_bin(f.get("tom_rx", "")), tom_bin(f.get("tom_tx", "")))
        c[30] = _bits(c[30], 0, 2, POTENCIAS.get(f.get("potencia", "Alta"), 3))
        for k in EXTRAS_CANAL:
            if k in f:
                _grava_extra(c, k, f[k])
        if not vfo:
            _poe_txt(c, 32, nome, 16)
        self.mem[o:o + TAM_CANAL] = c

    def copia_canal(self, de, para):
        o1, o2 = OFF_CANAIS + (de - 1) * TAM_CANAL, OFF_CANAIS + (para - 1) * TAM_CANAL
        self.mem[o2:o2 + TAM_CANAL] = self.mem[o1:o1 + TAM_CANAL]

    def bruto_canal(self, n):
        return bytes(self._canal(n))

    def poe_bruto_canal(self, n, b):
        o = OFF_CANAIS + (n - 1) * TAM_CANAL
        self.mem[o:o + TAM_CANAL] = b

    def zonas_do_canal(self, n):
        return [z for z in self.zonas() if n in self.membros(z, "A") or n in self.membros(z, "B")]

    def apaga_canal(self, n):
        """Apaga um canal e reorganiza os demais (ver apaga_canais)."""
        return self.apaga_canais([n])

    def apaga_canais(self, nums):
        """Apaga os canais, tira-os das zonas e das listas de varredura (como o CPS faz) e
        renumera os que sobraram, para não deixar buraco na sequência. Zonas e varreduras
        passam a apontar para os números novos. Retorna {antigo: novo} dos canais mantidos."""
        nums = {n for n in nums if self.usado(n)}
        if not nums:
            return {}
        vazio = b"\xff" * TAM_CANAL
        for n in nums:
            o = OFF_CANAIS + (n - 1) * TAM_CANAL
            self.mem[o:o + TAM_CANAL] = vazio
        for z in self.zonas():
            for lado in ("A", "B"):
                m = self.membros(z, lado)
                if any(x in nums for x in m):
                    self._grava_membros(z, lado, [x for x in m if x not in nums])
        for i in self.varreduras():
            d = self.varredura(i)
            if any(x in nums for x in d["membros"]) or any(d[k] in nums for k in ("prio1", "prio2", "tx")):
                d["membros"] = [x for x in d["membros"] if x not in nums]
                for k in ("prio1", "prio2", "tx"):
                    if d[k] in nums:
                        d[k] = 0xFFFF
                self.grava_varredura(i, d)
        # Renumera: os canais restantes sobem para a sequência 1, 2, 3... sem buracos
        return self.aplica_ordem(sorted(self.usados()))

    # -------------------------------------------------------------------- zonas
    def zona_livre(self):
        for z in range(TOTAL_ZONAS):
            if not self.zona_usada(z):
                return z
        raise ErroDMR("Não há zona livre: o rádio aceita 250 zonas.")

    def cria_zona(self, nome):
        z = self.zona_livre()
        self.mem[self._zona_off(z):self._zona_off(z) + 64] = b"\x00" * 64
        self.mem[OFF_ZONAS_EXT + z * 224:OFF_ZONAS_EXT + (z + 1) * 224] = b"\x00" * 224
        self.renomeia_zona(z, nome)
        return z

    def renomeia_zona(self, z, nome):
        nome = nome
        if not nome.strip():
            raise ErroDMR("Dê um nome à zona.")
        _poe_txt(self.mem, self._zona_off(z), nome[:16], 16)

    def apaga_zona(self, z):
        self.mem[self._zona_off(z):self._zona_off(z) + 64] = b"\x00" * 64
        self.mem[OFF_ZONAS_EXT + z * 224:OFF_ZONAS_EXT + (z + 1) * 224] = b"\x00" * 224

    def define_membros_zona(self, z, lista, lado="A"):
        """Grava os canais de um lado da zona (A ou B, independentes como no CPS)."""
        lista = [n for n in lista if self.usado(n)]
        if len(lista) > MEMBROS_ZONA:
            raise ErroDMR(f"A zona aceita no máximo {MEMBROS_ZONA} canais por lado.")
        self._grava_membros(z, lado, lista)

    # ----------------------------------------------------------- listas de varredura
    def _var_off(self, i):
        return OFF_VARREDURA + (i - 1) * 104

    def varreduras(self):
        return [i for i in range(1, TOTAL_VARREDURAS + 1)
                if _valido(self.mem[self._var_off(i):self._var_off(i) + 2])]

    def varredura(self, i):
        o = self._var_off(i)
        p1, p2, txd = struct.unpack_from("<3H", self.mem, o + 32)
        mem = []
        for x in struct.unpack_from("<31H", self.mem, o + 42):
            if x in (0, 0xFFFF):
                break
            mem.append(x)
        return {"nome": _txt(self.mem[o:o + 32]), "prio1": p1, "prio2": p2, "tx": txd, "membros": mem}

    def grava_varredura(self, i, d):
        o = self._var_off(i)
        nome = str(d["nome"])
        if not nome.strip():
            raise ErroDMR("Dê um nome à lista de varredura.")
        if not _valido(self.mem[o:o + 2]):
            self.mem[o:o + 104] = b"\x00" * 104
            self.mem[o + 32:o + 42] = bytes.fromhex("fffffffffffff11408ff")
        _poe_txt(self.mem, o, nome[:16], 16)
        membros = [n for n in d["membros"] if self.usado(n)][:31]
        struct.pack_into("<3H", self.mem, o + 32, d["prio1"], d["prio2"], d["tx"])
        struct.pack_into("<31H", self.mem, o + 42, *(membros + [0] * (31 - len(membros))))

    def varredura_livre(self):
        for i in range(1, TOTAL_VARREDURAS + 1):
            if not _valido(self.mem[self._var_off(i):self._var_off(i) + 2]):
                return i
        raise ErroDMR("Não há lista de varredura livre.")

    def apaga_varredura(self, i):
        o = self._var_off(i)
        self.mem[o:o + 104] = b"\x00" * 104
        self.mem[o + 32:o + 42] = bytes.fromhex("fffffffffffff11408ff")
        # canais que usavam esta lista ficam sem lista; as de número maior não mudam de número
        for n in self.usados():
            oc = OFF_CANAIS + (n - 1) * TAM_CANAL
            if self.mem[oc + 11] == i:
                self.mem[oc + 11] = 0

    # ----------------------------------------------------------------- contatos
    def _cont_off(self, i):
        return OFF_CONTATOS + (i - 1) * 36

    def contato_usado(self, i):
        o = self._cont_off(i)
        return (self.mem[o + 3] & 0x1F) != 0 and _valido(self.mem[o + 4:o + 6])

    def contatos(self):
        out = []
        for i in range(1, TOTAL_CONTATOS + 1):
            o = self._cont_off(i)
            if (self.mem[o + 3] & 0x1F) == 0 or not _valido(self.mem[o + 4:o + 6]):
                continue
            c = self.mem[o:o + 36]
            # tipo nos 2 bits de baixo; outros bits (ex.: 0x08 em alguns privados) são mantidos ao gravar
            tipo = {v: k for k, v in TIPOS_CONTATO.items()}.get(c[3] & 0x03, "Grupo")
            out.append({"numero": i, "nome": _txt(c[4:36]), "id": c[0] | c[1] << 8 | c[2] << 16,
                        "tipo": tipo, "tom": bool(c[3] & 0x20)})
        return out

    def contato_livre(self):
        for i in range(1, TOTAL_CONTATOS + 1):
            if not self.contato_usado(i):
                return i
        raise ErroDMR("Não há contato livre.")

    def grava_contato(self, i, nome, ident, tipo, tom=False):
        nome = str(nome)
        if not nome.strip():
            raise ErroDMR("Dê um nome ao contato.")
        ident = int(ident)
        if not 1 <= ident <= 16776415:
            raise ErroDMR("O ID vai de 1 a 16776415.")
        o = self._cont_off(i)
        antes = self.mem[o + 3] if self.contato_usado(i) else 0xC0
        c = bytearray(36)
        c[0], c[1], c[2] = ident & 0xFF, ident >> 8 & 0xFF, ident >> 16 & 0xFF
        c[3] = (antes & 0xDC) | TIPOS_CONTATO[tipo] | (0x20 if tom else 0)
        _poe_txt(c, 4, nome[:16], 16)
        self.mem[o:o + 36] = c

    def apaga_contato(self, i):
        o = self._cont_off(i)
        self.mem[o:o + 36] = bytes.fromhex("ffffffc0") + b"\x00" * 32
        for n in self.usados():
            oc = OFF_CANAIS + (n - 1) * TAM_CANAL
            if struct.unpack_from("<H", self.mem, oc + 6)[0] == i:
                struct.pack_into("<H", self.mem, oc + 6, 0)
        for g in self.grupos():
            d = self.grupo(g)
            if i in d["membros"]:
                self.grava_grupo(g, d["nome"], [x for x in d["membros"] if x != i])

    # ------------------------------------------------------------- grupos de RX
    def _grupo_off(self, g):
        return OFF_GRUPOS + (g - 1) * 96

    def grupos(self):
        return [g for g in range(1, TOTAL_GRUPOS + 1)
                if _valido(self.mem[self._grupo_off(g):self._grupo_off(g) + 2])]

    def grupo(self, g):
        o = self._grupo_off(g)
        mem = []
        for x in struct.unpack_from("<32H", self.mem, o + 32):
            if x in (0, 0xFFFF):
                break
            mem.append(x)
        return {"nome": _txt(self.mem[o:o + 32]), "membros": mem}

    def nome_grupo(self, g):
        if not 1 <= g <= TOTAL_GRUPOS:
            return ""
        o = self._grupo_off(g)
        return _txt(self.mem[o:o + 32]) if _valido(self.mem[o:o + 2]) else ""

    def grupo_livre(self):
        for g in range(1, TOTAL_GRUPOS + 1):
            if not _valido(self.mem[self._grupo_off(g):self._grupo_off(g) + 2]):
                return g
        raise ErroDMR("Não há grupo de RX livre.")

    def grava_grupo(self, g, nome, membros):
        nome = str(nome)
        if not nome.strip():
            raise ErroDMR("Dê um nome ao grupo de RX.")
        membros = [m for m in membros if self.contato_usado(m)]
        if len(membros) > 32:
            raise ErroDMR("O grupo de RX aceita no máximo 32 contatos.")
        o = self._grupo_off(g)
        _poe_txt(self.mem, o, nome[:16], 16)
        struct.pack_into("<32H", self.mem, o + 32, *(membros + [0] * (32 - len(membros))))

    def apaga_grupo(self, g):
        o = self._grupo_off(g)
        self.mem[o:o + 96] = b"\x00" * 96
        for n in self.usados():
            oc = OFF_CANAIS + (n - 1) * TAM_CANAL
            if self.mem[oc + 12] == g:
                self.mem[oc + 12] = 0

    # ---------------------------------------------------------------- mensagens
    def mensagem(self, i):
        o = OFF_MENSAGENS + (i - 1) * 288
        return _txt(self.mem[o:o + 288])

    def grava_mensagem(self, i, texto):
        texto = str(texto)
        if len(texto) > TAM_MENSAGEM:
            raise ErroDMR(f"A mensagem pode ter no máximo {TAM_MENSAGEM} caracteres.")
        _poe_txt(self.mem, OFF_MENSAGENS + (i - 1) * 288, texto, TAM_MENSAGEM)


for _nome, _f in list(vars(_Edicao).items()):
    if callable(_f) and not _nome.startswith("__"):
        setattr(Codeplug, _nome, _f)


# ------------------------------------------------------------------ ajustes gerais
# Tela "General Setting" do CPS. Mapeada comparando arquivos salvos pelo CPS do RT3S
# (cada ajuste mudado sozinho); não segue o dmrconfig, que tem posições erradas aqui.
OFF_GERAL = 0x2040

# chave: (rótulo, grupo, tipo, posição, extra)
#   tipo "op":   posição (deslocamento, bit, largura); extra {valor: rótulo}
#   tipo "bool": posição (deslocamento, bit); extra True se gravado invertido (1 = desmarcado)
#   tipo "num":  posição (deslocamento,); extra (multiplicador, mínimo, máximo, unidade)
#   tipo "txt":  posição (deslocamento, letras)
#   tipo "id":   posição (deslocamento, bytes)
AJUSTES_GERAIS = {
    "nome_radio": ("Nome do rádio", "Rádio", "txt", (112, 16), None),
    "id_radio": ("ID do rádio (DMR)", "Rádio", "id", (68, 3), None),
    "id1": ("Radio ID 1", "Rádio", "id", (0x94, 4), None),
    "id2": ("Radio ID 2", "Rádio", "id", (0x98, 4), None),
    "id3": ("Radio ID 3", "Rádio", "id", (0x9C, 4), None),
    "edita_id": ("Permitir editar o ID no rádio", "Rádio", "bool", (0xA0, 6), True),
    "abertura": ("Tela de abertura", "Rádio", "op", (66, 4, 1), {0: "Texto", 1: "Imagem"}),
    "linha1": ("Linha 1 da abertura", "Rádio", "txt", (0, 10), None),
    "linha2": ("Linha 2 da abertura", "Rádio", "txt", (20, 10), None),
    "fuso": ("Fuso horário", "Rádio", "op", (107, 3, 5),
             {i + 12: f"UTC {'+' if i >= 0 else '-'}{abs(i)}:00" for i in range(-12, 13)}),

    "modo_tx": ("Canal de transmissão", "Operação", "op", (64, 6, 2),
                {0: "Último canal de chamada", 1: "Último de chamada + manual",
                 2: "Canal designado", 3: "Canal designado + manual"}),
    "freq_canal": ("Modo de exibição", "Operação", "op", (87, 0, 8), {0xFF: "Canal", 0: "Frequência"}),
    "monitor": ("Tipo de monitor", "Operação", "op", (64, 4, 1), {0: "Silencioso", 1: "Squelch aberto"}),
    "vox": ("Sensibilidade do VOX", "Operação", "op", (75, 0, 8), {i: str(i) for i in range(1, 11)}),
    "mic": ("Ganho do microfone", "Operação", "op", (0xA0, 3, 3), {i: str(i + 1) for i in range(6)}),
    "zona_publica": ("Zona pública", "Operação", "bool", (0x92, 2), False),
    "match_grupo": ("Group Call Match", "Operação", "bool", (107, 0), False),
    "match_privada": ("Private Call Match", "Operação", "bool", (107, 1), False),

    "sem_tons": ("Desligar todos os tons", "Tons e luzes", "bool", (65, 2), True),
    "tom_livre": ("Tom de canal livre", "Tons e luzes", "bool", (65, 4), True),
    "tom_permissao": ("Tom de permissão para falar", "Tons e luzes", "op", (65, 6, 2),
                      {0: "Nenhum", 1: "Digital", 2: "Analógico", 3: "Analógico e digital"}),
    "sem_leds": ("Desligar todos os LEDs", "Tons e luzes", "bool", (64, 2), True),
    "luz": ("Luz do visor", "Tons e luzes", "op", (85, 0, 2), {0: "Sempre acesa", 1: "5 s", 2: "10 s", 3: "15 s"}),
    "teclado": ("Bloqueio do teclado", "Tons e luzes", "op", (86, 0, 8),
                {0xFF: "Manual", 1: "5 s", 2: "10 s", 3: "15 s"}),

    "preambulo": ("Preâmbulo de TX", "Tempos", "num", (72,), (60, 0, 8640, "ms")),
    "espera_grupo": ("Espera após chamada de grupo", "Tempos", "num", (73,), (100, 0, 7000, "ms")),
    "espera_privada": ("Espera após chamada privada", "Tempos", "num", (74,), (100, 0, 7000, "ms")),
    "bateria": ("Aviso de bateria baixa a cada", "Tempos", "num", (78,), (5, 5, 635, "s")),
    "var_digital": ("Espera da varredura digital", "Tempos", "num", (83,), (100, 0, 10000, "ms")),
    "var_analogica": ("Espera da varredura analógica", "Tempos", "num", (84,), (100, 0, 10000, "ms")),
    "lone_resposta": ("Lone worker: resposta", "Tempos", "num", (80,), (1, 1, 255, "min")),
    "lone_lembrete": ("Lone worker: lembrete", "Tempos", "num", (81,), (1, 1, 255, "s")),
}
GRUPOS_GERAIS = ["Rádio", "Operação", "Tons e luzes", "Tempos", "Senhas"]
AJUSTES_GERAIS["salva_preambulo"] = ("Economia: preâmbulo (Save Preamble)", "Operação", "bool", (65, 0), False)
AJUSTES_GERAIS["salva_recepcao"] = ("Economia na recepção (Save Mode Receive)", "Operação", "bool", (65, 1), False)
AJUSTES_GERAIS["senha_liga_ativa"] = ("Pedir senha ao ligar o rádio", "Senhas", "bool", (65, 5), True)
AJUSTES_GERAIS["trava_frontal"] = ("Travar o teclado frontal", "Operação", "bool", (0xA2, 2), True)
AJUSTES_GERAIS["gps_formato"] = ("Formato do relatório de GPS", "Operação", "op", (0xA0, 7, 1),
                                 {0: "Mensagem", 1: "Normal"})
AJUSTES_GERAIS["voz_liga"] = ("Voz ao ligar o rádio", "Tons e luzes", "bool", (0xA2, 5), False)
AJUSTES_GERAIS["anuncia_canal"] = ("Anunciar o canal por voz", "Tons e luzes", "bool", (66, 1), False)
AJUSTES_GERAIS["senha_pc"] = ("Senha para ler/gravar pelo computador", "Senhas", "senha_txt", (0x60, 8), None)
AJUSTES_GERAIS["senha_radio"] = ("Senha para programar pelo rádio", "Senhas", "senha_bcd", (0x5C, 4), True)
AJUSTES_GERAIS["senha_liga"] = ("Senha ao ligar o rádio", "Senhas", "senha_bcd", (0x58, 4), False)

# Botões (tela Buttons Definitions). O valor gravado é a posição na lista de funções do CPS;
# só aparecem as funções que o CPS oferece para os botões laterais do RT3S.
FUNCOES_BOTAO = {
    0: "Nenhuma", 1: "Liga/desliga todos os tons", 2: "Emergência: ligar", 3: "Emergência: desligar",
    4: "Potência", 5: "Monitor", 7: "Acesso rápido 1", 8: "Acesso rápido 2", 9: "Acesso rápido 3",
    10: "Acesso rápido 4", 11: "Acesso rápido 5", 12: "Acesso rápido 6", 13: "Repetidora/talkaround",
    14: "Liga/desliga varredura", 21: "Nível de squelch", 22: "Liga/desliga privacidade", 23: "Liga/desliga VOX",
    24: "Zona +", 26: "Indicador de bateria", 31: "Liga/desliga lone worker", 34: "Liga/desliga gravação",
    35: "Ouvir gravação", 36: "Apagar gravações", 38: "Tom de 1750 Hz", 47: "Alternar tela",
    48: "Tecla direita", 49: "Tecla esquerda", 55: "Zona -",
}
GRUPOS_BOTOES = ["Botões laterais", "Teclas numéricas (contato rápido)"]
for _i, (_b, _t) in enumerate([("b1_curto", "Botão lateral 1, toque curto"), ("b1_longo", "Botão lateral 1, toque longo"),
                               ("b2_curto", "Botão lateral 2, toque curto"), ("b2_longo", "Botão lateral 2, toque longo")]):
    AJUSTES_GERAIS[_b] = (_t, "Botões laterais", "op", (0xC2 + _i, 0, 8), FUNCOES_BOTAO)
AJUSTES_GERAIS["toque_longo"] = ("Duração do toque longo", "Botões laterais", "num", (0xD1,), (250, 250, 3750, "ms"))
for _i in range(10):
    AJUSTES_GERAIS[f"tecla{_i}"] = (f"Tecla {_i}", "Teclas numéricas (contato rápido)", "cont", (0xEC + 2 * _i,), None)

# Acesso rápido (One Touch Access): 6 linhas de 4 bytes
_TIPOS_OTA = {0: "Chamada", 1: "Mensagem de texto", 2: "Alerta de chamada", 3: "Duplex",
              4: "DTMF-1", 5: "DTMF-2", 6: "DTMF-3", 7: "DTMF-4"}
GRUPOS_BOTOES.append("Acesso rápido (One Touch Access)")
for _i in range(6):
    _o = 0xD4 + 4 * _i
    _g = "Acesso rápido (One Touch Access)"
    AJUSTES_GERAIS[f"ota{_i + 1}_modo"] = (f"{_i + 1}: modo", _g, "op", (_o, 4, 2),
                                           {0: "Nenhum", 1: "Digital", 2: "Analógico"})
    AJUSTES_GERAIS[f"ota{_i + 1}_contato"] = (f"{_i + 1}: contato", _g, "cont", (_o + 2,), None)
    AJUSTES_GERAIS[f"ota{_i + 1}_tipo"] = (f"{_i + 1}: tipo", _g, "op", (_o, 0, 4), _TIPOS_OTA)
    AJUSTES_GERAIS[f"ota{_i + 1}_msg"] = (f"{_i + 1}: mensagem", _g, "msg", (_o + 1,), None)

# Chaves de privacidade (tela Privacy Setting): gravadas com os bytes em ordem invertida
GRUPOS_PRIVACIDADE = ["Chaves básicas (Basic)", "Chaves avançadas (Enhanced)"]
for _i in range(16):
    AJUSTES_GERAIS[f"chave_b{_i + 1}"] = (f"Chave {_i + 1}", "Chaves básicas (Basic)", "hex", (0x3A10 + 2 * _i, 2), None)
for _i in range(8):
    AJUSTES_GERAIS[f"chave_a{_i + 1}"] = (f"Chave {_i + 1}", "Chaves avançadas (Enhanced)", "hex",
                                          (0x3980 + 16 * _i, 16), None)

# Emergência digital (tela Digit Emergency System): ajustes gerais em 0x5A70 e até 32 sistemas de 40 bytes
GRUPOS_EMERGENCIA = ["Decodificação", "Tempos e limites"]
_GE = "Decodificação"
AJUSTES_GERAIS["em_desabilita"] = ("Aceitar comando de desabilitar o rádio", _GE, "bool", (0x3A30, 0), False)
AJUSTES_GERAIS["em_monitor"] = ("Aceitar monitor remoto", _GE, "bool", (0x3A30, 1), False)
AJUSTES_GERAIS["em_monitor_emerg"] = ("Aceitar monitor remoto em emergência", _GE, "bool", (0x3A30, 2), False)
AJUSTES_GERAIS["em_monitor_dur"] = ("Duração do monitor remoto", "Tempos e limites", "num", (0x3A31,), (1, 1, 255, "s"))
AJUSTES_GERAIS["em_wakeup_tot"] = ("Tempo de sincronismo (wakeup)", "Tempos e limites", "num", (0x3A32,), (25, 25, 6375, "ms"))
AJUSTES_GERAIS["em_wakeup_lim"] = ("Limite de mensagens de wakeup", "Tempos e limites", "op", (0x3A33, 0, 8),
                                   {i: str(i) for i in range(1, 5)})
OFF_SISTEMAS = 0x5A80
TAM_SISTEMA = 40
TOTAL_SISTEMAS = 32
TIPOS_ALARME = {0: "Desativado", 1: "Normal", 2: "Silencioso", 3: "Silencioso com voz"}
MODOS_ALARME = {0: "Alarme", 1: "Alarme com chamada", 2: "Alarme com voz em seguida"}

# DTMF (tela DTMF Signaling, aba System): 4 sistemas de 48 bytes em 0x30000
GRUPOS_DTMF = [f"Sistema DTMF {i}" for i in range(1, 5)]
for _i in range(4):
    _o, _g, _p = 0x2DFC0 + 0x30 * _i, f"Sistema DTMF {_i + 1}", f"d{_i + 1}_"
    AJUSTES_GERAIS[_p + "tom_lateral"] = ("Ouvir os tons DTMF (side tone)", _g, "bool", (_o + 8, 0), False)
    AJUSTES_GERAIS[_p + "ptt_id"] = ("PTT ID", _g, "op", (_o + 8, 2, 2),
                                     {0: "Nenhum", 1: "Só no início", 2: "Só no fim", 3: "No início e no fim"})
    AJUSTES_GERAIS[_p + "grupo"] = ("Código de grupo", _g, "op", (_o + 8, 4, 3),
                                    {0: "Nenhum", 1: "A", 2: "B", 3: "C", 4: "D", 5: "*", 6: "#"})
    AJUSTES_GERAIS[_p + "inicio"] = ("Código ao apertar o PTT", _g, "dtmf", (_o + 0x10, 16), None)
    AJUSTES_GERAIS[_p + "fim"] = ("Código ao soltar o PTT", _g, "dtmf", (_o + 0x20, 16), None)
    AJUSTES_GERAIS[_p + "sequencia"] = ("Próxima sequência", _g, "op", (_o + 6, 0, 8),
                                        {i: f"{i / 10:.1f} s".replace(".", ",") for i in range(5, 101, 5)})
    AJUSTES_GERAIS[_p + "reset"] = ("Reinício automático", _g, "num", (_o + 7,), (1, 1, 60, "s"))
    for _k, _t, _d in (("atraso", "Atraso do 1º dígito", 0), ("primeiro", "Duração do 1º dígito", 1),
                       ("digito", "Duração de cada dígito", 2), ("intervalo", "Intervalo entre dígitos", 3),
                       ("asterisco", "Duração de * e #", 4)):
        AJUSTES_GERAIS[_p + _k] = (_t, _g, "num", (_o + _d,), (10, 10, 2550, "ms"))
    AJUSTES_GERAIS[_p + "tecla_d"] = ("Tecla D", _g, "op", (_o + 5, 0, 8),
                                      {0: "Tecla D", **{i: f"{i * 10} ms" for i in range(1, 101)}})
GRUPOS_DTMF.append("Códigos para enviar (Encode)")
for _i in range(32):
    AJUSTES_GERAIS[f"dtmf_cod{_i + 1}"] = (f"Código {_i + 1}", "Códigos para enviar (Encode)", "dtmf",
                                          (0x2E080 + 16 * _i, 16), None)
_DIG_DTMF = "0123456789ABCD*#"
GRUPOS_DTMF.append("Decodificação (Decode)")
for _i in range(8):
    _o = 0x302C0 - 0x2040 + 24 * _i
    _g = "Decodificação (Decode)"
    AJUSTES_GERAIS[f"dec{_i + 1}_resp"] = (f"{_i + 1}: resposta", _g, "op", (_o + 16, 0, 8),
                                           {0: "Geral", 1: "Desabilitar (Kill)", 2: "Atordoar (Stun)", 3: "Ativar",
                                            4: "Reativar (Un Stun)"})
    AJUSTES_GERAIS[f"dec{_i + 1}_tipo"] = (f"{_i + 1}: tipo", _g, "op", (_o + 17, 0, 8),
                                           {0: "Nenhum", 1: "Chamada seletiva"})
    AJUSTES_GERAIS[f"dec{_i + 1}_ack"] = (f"{_i + 1}: confirmação", _g, "op", (_o + 18, 0, 8),
                                          {0: "Nenhuma", **{j: f"Código {j}" for j in range(1, 33)}})
    AJUSTES_GERAIS[f"dec{_i + 1}_id"] = (f"{_i + 1}: código", _g, "dtmf", (_o, 16), None)
    AJUSTES_GERAIS[f"dec{_i + 1}_atraso"] = (f"{_i + 1}: atraso da confirmação", _g, "op", (_o + 19, 0, 8),
                                             {0: "Desligado", **{j: f"{j * 50} ms" for j in range(1, 61)}})

# VFO A e B (tela VFO Mode): registros no formato de canal; no lugar do nome fica o passo
OFF_VFO = {"A": 0x2EF00, "B": 0x2EF40}
PASSOS_VFO = {0: "2,5 kHz", 1: "5 kHz", 2: "6,25 kHz", 3: "8,33 kHz", 4: "10 kHz", 5: "12,5 kHz",
              6: "20 kHz", 7: "25 kHz", 8: "30 kHz", 9: "50 kHz"}
GRUPOS_VFO = ["VFO A", "VFO B"]

# Sistemas de GPS (tela GPS System): 16 registros de 16 bytes em 0x3EC40
GRUPOS_GPS = ["Sistemas de GPS"]
INTERVALOS_GPS = {0: "Desligado", **{i: f"{i * 30} s" for i in range(1, 256)}}
for _i in range(16):
    _o = 0x3EC40 - OFF_GERAL + 16 * _i
    AJUSTES_GERAIS[f"gps{_i + 1}_canal"] = (f"{_i + 1}: canal de retorno", "Sistemas de GPS", "canal", (_o,), None)
    AJUSTES_GERAIS[f"gps{_i + 1}_intervalo"] = (f"{_i + 1}: intervalo", "Sistemas de GPS", "op", (_o + 2, 0, 8),
                                                INTERVALOS_GPS)
    AJUSTES_GERAIS[f"gps{_i + 1}_destino"] = (f"{_i + 1}: destino", "Sistemas de GPS", "cont", (_o + 4,), None)
AJUSTES_GERAIS["vfo_a_passo"] = ("Passo de frequência", "VFO A", "op", (OFF_VFO["A"] - OFF_GERAL + 32, 0, 8), PASSOS_VFO)
AJUSTES_GERAIS["vfo_b_passo"] = ("Passo de frequência", "VFO B", "op", (OFF_VFO["B"] - OFF_GERAL + 32, 0, 8), PASSOS_VFO)

# Itens do menu do rádio (tela Menu Item): um bit por item, 1 = aparece no menu (salvo os invertidos)
GRUPOS_MENU = ["Menu: contatos e mensagens", "Menu: registro de chamadas", "Menu: zona e varredura",
               "Menu: utilidades"]
AJUSTES_GERAIS["menu_tempo"] = ("Tempo do menu aberto", "Menu: utilidades", "op", (0xB0, 0, 8),
                                {0: "Sem limite", **{i: f"{i} s" for i in range(1, 31)}})
for _k, _t, _g, _o, _b, _inv in [
    ("m_texto", "Mensagens de texto", 0, 0xB1, 0, False), ("m_alerta", "Alerta de chamada", 0, 0xB1, 1, False),
    ("m_edita_cont", "Editar contato", 0, 0xB1, 2, False), ("m_discagem", "Discagem manual", 0, 0xB1, 3, False),
    ("m_verifica", "Verificar rádio", 0, 0xB1, 4, False), ("m_monitor_rem", "Monitor remoto", 0, 0xB1, 5, False),
    ("m_habilita", "Habilitar rádio", 0, 0xB1, 6, False), ("m_desabilita", "Desabilitar rádio", 0, 0xB1, 7, False),
    ("m_chave", "Programar chave", 0, 0xB2, 0, False),
    ("m_perdidas", "Perdidas", 1, 0xB2, 3, False), ("m_atendidas", "Atendidas", 1, 0xB2, 4, False),
    ("m_efetuadas", "Efetuadas", 1, 0xB2, 5, False),
    ("m_zona", "Zona", 2, 0xB5, 6, False), ("m_edita_zona", "Editar zona", 2, 0xB6, 0, False),
    ("m_nova_zona", "Nova lista de zonas", 2, 0xB5, 7, False), ("m_varredura", "Varredura", 2, 0xB2, 1, False),
    ("m_edita_lista", "Editar lista de varredura", 2, 0xB2, 2, False),
    ("m_nova_lista", "Nova lista de varredura", 2, 0xB6, 1, False),
    ("m_talkaround", "Talkaround", 3, 0xB2, 6, False), ("m_tom", "Tom ou alerta", 3, 0xB2, 7, False),
    ("m_potencia", "Potência", 3, 0xB3, 0, False), ("m_luz", "Luz do visor", 3, 0xB3, 1, False),
    ("m_abertura", "Tela de abertura", 3, 0xB3, 2, False), ("m_teclado", "Bloqueio do teclado", 3, 0xB3, 3, False),
    ("m_led", "Indicador LED", 3, 0xB3, 4, False), ("m_squelch", "Squelch", 3, 0xB3, 5, False),
    ("m_vox", "VOX", 3, 0xB3, 7, False), ("m_senha", "Senha e bloqueio", 3, 0xB4, 0, False),
    ("m_exibicao", "Modo de exibição", 3, 0xB4, 1, False), ("m_programa", "Programar o rádio", 3, 0xB4, 2, True),
    ("m_gps", "GPS", 3, 0xB4, 3, True), ("m_gravacao", "Gravação", 3, 0xB4, 5, False),
    ("m_match_grupo", "Group Call Match", 3, 0xB5, 2, False), ("m_match_priv", "Private Call Match", 3, 0xB5, 3, False),
    ("m_tempo_menu", "Tempo do menu", 3, 0xB5, 4, False), ("m_modo_tx", "Modo de TX", 3, 0xB5, 5, False),
    ("m_monitor", "Monitor", 3, 0xB6, 3, False),
    ("m_novo_cont", "Novo contato", 0, 0xB7, 6, True), ("m_chamada_grupo", "Chamada de grupo", 0, 0xB7, 7, True),
    ("m_apaga_reg", "Apagar todos os registros", 1, 0xB7, 3, False),
    ("m_sel_id", "Escolher o Radio ID", 3, 0xB7, 2, False), ("m_voz_liga", "Voz ao ligar", 3, 0xB7, 4, False),
]:
    AJUSTES_GERAIS[_k] = (_t, GRUPOS_MENU[_g], "bool", (_o, _b), _inv)
MAX_ID = 16776415


class _Gerais:
    def ajuste(self, chave):
        """Valor para exibir: texto, número, bool ou rótulo da opção (ou "Valor N" se desconhecido)."""
        _, _, tipo, pos, extra = AJUSTES_GERAIS[chave]
        o = OFF_GERAL + pos[0]
        if tipo == "txt":
            return _txt(self.mem[o:o + 2 * pos[1]])
        if tipo == "id":
            return int.from_bytes(self.mem[o:o + pos[1]], "little")
        if tipo in ("cont", "canal"):
            return int.from_bytes(self.mem[o:o + 2], "little")
        if tipo == "msg":
            return self.mem[o]
        if tipo == "senha_txt":
            b = bytes(self.mem[o:o + pos[1]])
            return "" if b == b"\xff" * pos[1] else b.split(b"\xff")[0].decode("ascii", "replace")
        if tipo == "senha_bcd":
            b = bytes(self.mem[o:o + pos[1]])
            return "" if b == b"\xff" * pos[1] else b.hex().upper()
        if tipo == "hex":
            return bytes(self.mem[o:o + pos[1]][::-1]).hex().upper()
        if tipo == "dtmf":
            n = self.mem[o]
            if not 0 < n <= 2 * (pos[1] - 1):
                return ""
            dig = []
            for b in self.mem[o + 1:o + 1 + (n + 1) // 2]:
                dig += [b & 15, b >> 4]
            return "".join(_DIG_DTMF[x] for x in dig[:n])
        if tipo == "num":
            return self.mem[o] * extra[0]
        if tipo == "bool":
            b = bool(self.mem[o] >> pos[1] & 1)
            return not b if extra else b
        v = self.mem[o] >> pos[1] & ((1 << pos[2]) - 1)
        return extra.get(v, f"Valor {v}")

    def ajustes_gerais(self):
        return {k: self.ajuste(k) for k in AJUSTES_GERAIS}

    def grava_ajuste(self, chave, valor):
        rot, _, tipo, pos, extra = AJUSTES_GERAIS[chave]
        if valor == self.ajuste(chave):
            return False
        o = OFF_GERAL + pos[0]
        if tipo == "txt":
            if len(str(valor)) > pos[1]:
                raise ErroDMR(f"{rot}: no máximo {pos[1]} letras.")
            _poe_txt(self.mem, o, str(valor), pos[1])
        elif tipo == "id":
            try:
                v = int(str(valor).strip())
            except ValueError as e:
                raise ErroDMR(f"{rot}: informe um número.") from e
            if not 1 <= v <= (MAX_ID if pos[1] == 3 else 0xFFFFFFFF):
                raise ErroDMR(f"{rot}: número fora do permitido.")
            self.mem[o:o + pos[1]] = v.to_bytes(pos[1], "little")
        elif tipo == "senha_txt":
            t = str(valor).strip()
            if t and (len(t) != pos[1] or not t.isdigit()):
                raise ErroDMR(f"{rot}: deixe vazio ou use {pos[1]} números.")
            self.mem[o:o + pos[1]] = t.encode("ascii") if t else b"\xff" * pos[1]
        elif tipo == "senha_bcd":
            t = str(valor).strip()
            if (t or not extra) and (len(t) != 2 * pos[1] or not t.isdigit()):
                raise ErroDMR(f"{rot}: use {2 * pos[1]} números" + (" ou deixe vazio." if extra else "."))
            self.mem[o:o + pos[1]] = bytes.fromhex(t) if t else b"\xff" * pos[1]
        elif tipo == "dtmf":
            t = str(valor).strip().upper().replace(" ", "")
            if len(t) > 16 or any(ch not in _DIG_DTMF for ch in t):
                raise ErroDMR(f"{rot}: até 16 dígitos (0 a 9, A a D, * e #).")
            v = [_DIG_DTMF.index(ch) for ch in t]
            buf = bytearray([len(t)]) + bytearray(b"\xff" * (pos[1] - 1))
            for j, x in enumerate(v):
                b = buf[1 + j // 2]
                buf[1 + j // 2] = (b & 0xF0) | x if j % 2 == 0 else (b & 0x0F) | (x << 4)
            self.mem[o:o + pos[1]] = buf
        elif tipo == "hex":
            t = str(valor).strip().upper().replace(" ", "")
            if len(t) != 2 * pos[1] or any(ch not in "0123456789ABCDEF" for ch in t):
                raise ErroDMR(f"{rot}: use {2 * pos[1]} dígitos de 0 a 9 e de A a F.")
            self.mem[o:o + pos[1]] = bytes.fromhex(t)[::-1]
        elif tipo == "msg":
            v = int(valor)
            if not 0 <= v <= TOTAL_MENSAGENS:
                raise ErroDMR(f"{rot}: mensagem inválida.")
            self.mem[o] = v
        elif tipo == "canal":
            v = int(valor)
            if not 0 <= v <= TOTAL_CANAIS:
                raise ErroDMR(f"{rot}: canal inválido.")
            self.mem[o:o + 2] = v.to_bytes(2, "little")
        elif tipo == "cont":
            v = int(valor)
            if not 0 <= v <= TOTAL_CONTATOS:
                raise ErroDMR(f"{rot}: contato inválido.")
            self.mem[o:o + 2] = v.to_bytes(2, "little")
        elif tipo == "num":
            mult, mn, mx, un = extra
            try:
                v = int(str(valor).strip())
            except ValueError as e:
                raise ErroDMR(f"{rot}: informe um número.") from e
            if not mn <= v <= mx or v % mult:
                raise ErroDMR(f"{rot}: use de {mn} a {mx} {un}" + (f", de {mult} em {mult}." if mult > 1 else "."))
            self.mem[o] = v // mult
        elif tipo == "bool":
            b = bool(valor)
            self.mem[o] = _bits(self.mem[o], pos[1], 1, (not b) if extra else b)
        else:
            v = next((k for k, t in extra.items() if t == valor), None)
            if v is None:
                raise ErroDMR(f"{rot}: opção inválida.")
            self.mem[o] = _bits(self.mem[o], pos[1], pos[2], v)
        return True


class _Emergencia:
    def _sis_off(self, i):
        return OFF_SISTEMAS + (i - 1) * TAM_SISTEMA

    def sistemas(self):
        out = []
        for i in range(1, TOTAL_SISTEMAS + 1):
            o = self._sis_off(i)
            if _valido(self.mem[o:o + 32]) and self.mem[o + 32:o + 40] != b"\xff" * 8:
                out.append(i)
            else:
                break
        return out

    def sistema(self, i):
        o = self._sis_off(i)
        b = self.mem[o + 32:o + 40]
        return {"nome": _txt(self.mem[o:o + 32]), "tipo": TIPOS_ALARME.get(b[0] & 3, "Normal"),
                "modo": MODOS_ALARME.get((b[0] >> 4) & 3, f"Valor {(b[0] >> 4) & 3}"),
                "impolido": b[1], "polido": b[2], "microfone": b[3],
                "canal": int.from_bytes(b[4:6], "little")}

    def grava_sistema(self, i, d):
        nome = str(d["nome"])
        if not nome.strip():
            raise ErroDMR("Dê um nome ao sistema.")
        if len(nome) > 16:
            raise ErroDMR("O nome pode ter no máximo 16 letras.")
        for k, rot, mx in (("impolido", "Tentativas impolidas", 15), ("polido", "Tentativas polidas", 15),
                           ("microfone", "Microfone aberto", 120)):
            if not 0 <= int(d[k]) <= mx:
                raise ErroDMR(f"{rot}: de 0 a {mx}.")
        o = self._sis_off(i)
        b = bytearray(self.mem[o + 32:o + 40])
        if b == b"\xff" * 8:                      # sistema novo: valores do CPS
            b = bytearray([0x4D, 15, 5, 10, 0, 0, 0xFF, 0xFF])
        tipo = next(k for k, t in TIPOS_ALARME.items() if t == d["tipo"])
        b[0] = _bits(b[0], 0, 2, tipo)
        modo = next((k for k, t in MODOS_ALARME.items() if t == d["modo"]), None)
        if modo is not None:
            b[0] = _bits(b[0], 4, 2, modo)
        b[1], b[2], b[3] = int(d["impolido"]), int(d["polido"]), int(d["microfone"])
        b[4:6] = int(d["canal"]).to_bytes(2, "little")
        _poe_txt(self.mem, o, nome, 16)
        self.mem[o + 32:o + 40] = b

    def sistema_livre(self):
        n = len(self.sistemas()) + 1
        if n > TOTAL_SISTEMAS:
            raise ErroDMR(f"O rádio aceita no máximo {TOTAL_SISTEMAS} sistemas de emergência.")
        return n

    def apaga_sistema(self, i):
        """Apaga e puxa os seguintes uma posição para cima, como o CPS; os canais acompanham."""
        lista = self.sistemas()
        ult = len(lista)
        for j in range(i, ult):
            a, b = self._sis_off(j), self._sis_off(j + 1)
            self.mem[a:a + TAM_SISTEMA] = self.mem[b:b + TAM_SISTEMA]
        o = self._sis_off(ult)
        self.mem[o:o + TAM_SISTEMA] = b"\x00" * 32 + b"\xff" * 8
        for n in self.usados():
            oc = OFF_CANAIS + (n - 1) * TAM_CANAL + 10
            v = self.mem[oc]
            if v == i:
                self.mem[oc] = 0
            elif v > i:
                self.mem[oc] = v - 1


for _nome, _f in list(vars(_Emergencia).items()) + list(vars(_Gerais).items()):
    if callable(_f) and not _nome.startswith("__"):
        setattr(Codeplug, _nome, _f)


# ------------------------------------------------------------------ planilha do CPS (Export/Import de canais)
# Colunas na ordem do CPS; cada uma: (byte, bit, largura, conversão) com o valor numérico que o CPS grava.
_POT_CSV = {0: 0, 1: 2, 2: 3}            # CSV -> bits do byte 30
_NAOQT_CSV = {0: 0, 1: 1, 2: 3}
_CSV_BITS = {
    "Band Width": (0, 2, 2), "Scan List": (11, 0, 8), "Squelch": (15, 0, 8), "RX Ref Frequency": (3, 0, 2),
    "TX Ref Frequency": (4, 0, 2), "TOT[s]": (8, 0, 6), "TOT Rekey Delay[s]": (9, 0, 8),
    "Admit Criteria": (4, 6, 2), "Auto Scan": (0, 4, 1), "Rx Only": (1, 1, 1), "Lone Worker": (0, 7, 1),
    "VOX": (4, 4, 1), "Allow Talkaround": (1, 0, 1), "Private Call Confirmed": (2, 6, 1),
    "Emergency Alarm Ack": (3, 3, 1), "Data Call Confirmed": (2, 7, 1), "Emergency System": (10, 0, 8),
    "Group List": (12, 0, 8), "Color Code": (1, 4, 4), "In Call Criteria": (5, 4, 2), "Privacy": (2, 4, 2),
    "Privacy No.": (2, 0, 4), "GPS System": (13, 0, 8), "Rx Signaling System": (28, 0, 8),
    "Tx Signaling System": (29, 0, 8), "QT Reverse": (5, 0, 2), "Display PTT ID": (3, 7, 1),
    "Reverse Burst/Turn-off Code": (4, 2, 1),
}
_CSV_INV = {"Send GPS Info": (31, 0), "Receive GPS Info": (31, 1), "Allow Interrupt": (31, 2), "DCDM Switch": (31, 3)}
COLUNAS_CSV_CPS = [
    "Channel Mode", "Channel Name", "RX Frequency(MHz)", "TX Frequency(MHz)", "Band Width", "Scan List", "Squelch",
    "RX Ref Frequency", "TX Ref Frequency", "TOT[s]", "TOT Rekey Delay[s]", "Power", "Admit Criteria", "Auto Scan",
    "Rx Only", "Lone Worker", "VOX", "Allow Talkaround", "Send GPS Info", "Receive GPS Info",
    "Private Call Confirmed", "Emergency Alarm Ack", "Data Call Confirmed", "Allow Interrupt", "DCDM Switch",
    "Leader/MS", "Emergency System", "Contact Name", "Group List", "Color Code", "Repeater Slot",
    "In Call Criteria", "Privacy", "Privacy No.", "GPS System", "CTCSS/DCS Dec", "CTCSS/DCS Enc",
    "Rx Signaling System", "Tx Signaling System", "QT Reverse", "Non-QT/DQT Turn-off Freq", "Display PTT ID",
    "Reverse Burst/Turn-off Code"] + [f"Decode {i}" for i in range(1, 9)]


def _linha_csv(c):
    rx, tx = struct.unpack_from("<II", c, 16)
    v = {"Channel Mode": c[0] & 3, "Channel Name": _txt(c[32:]), "RX Frequency(MHz)": f"{_bcd(rx) / 1e6:.5f}",
         "TX Frequency(MHz)": f"{_bcd(tx) / 1e6:.5f}",
         "Power": {b: a for a, b in _POT_CSV.items()}.get(c[30] & 3, 2),
         "Leader/MS": (c[4] >> 2) & 1,
         "Contact Name": struct.unpack_from("<H", c, 6)[0], "Repeater Slot": max(0, ((c[1] >> 2) & 3) - 1),
         "CTCSS/DCS Dec": _tom(struct.unpack_from("<H", c, 24)[0]) or "None",
         "CTCSS/DCS Enc": _tom(struct.unpack_from("<H", c, 26)[0]) or "None",
         "Non-QT/DQT Turn-off Freq": {b: a for a, b in _NAOQT_CSV.items()}.get(c[5] >> 6, 2)}
    for k, (b, p, n) in _CSV_BITS.items():
        v[k] = c[b] >> p & ((1 << n) - 1)
    for k, (b, p) in _CSV_INV.items():
        v[k] = 0 if c[b] >> p & 1 else 1
    for i in range(8):
        v[f"Decode {i + 1}"] = c[14] >> i & 1
    return [str(v[k]) for k in COLUNAS_CSV_CPS]


COLUNAS_CSV_CONTATOS = ["Contact Name", "Call Type", "Call ID", "Call Receive Tone"]
_TIPO_CSV_CONTATO = {1: "Grupo", 2: "Privada", 3: "Todos"}


def exporta_csv_contatos(cp, caminho):
    """Grava a lista de contatos no mesmo formato da planilha de contatos do CPS (Export)."""
    linhas = [",".join(COLUNAS_CSV_CONTATOS)]
    for c in cp.contatos():
        nome = c["nome"].replace(",", " ")
        linhas.append(f"{nome},{TIPOS_CONTATO[c['tipo']]},{c['id']},{1 if c['tom'] else 0}")
    with open(caminho, "wb") as f:
        f.write(("\r\n".join(linhas) + "\r\n").encode("latin-1", "replace"))
    return len(linhas) - 1


def importa_csv_contatos(cp, caminho):
    """Lê a planilha de contatos do CPS (Export) e grava os contatos 1, 2, 3... na ordem das linhas.
    Os contatos que sobrarem depois da última linha são apagados, como no CPS."""
    import csv
    with open(caminho, encoding="latin-1", newline="") as f:
        linhas = list(csv.reader(f))
    if not linhas or [x.strip() for x in linhas[0][:3]] != COLUNAS_CSV_CONTATOS[:3]:
        raise ErroDMR("Este arquivo não é uma planilha de contatos.")
    cab = [x.strip() for x in linhas[0]]
    dados = [dict(zip(cab, r)) for r in linhas[1:] if r and any(x.strip() for x in r)]
    if len(dados) > TOTAL_CONTATOS:
        raise ErroDMR(f"A planilha tem mais de {TOTAL_CONTATOS} contatos.")
    prontos = []
    for i, d in enumerate(dados, start=1):
        try:
            nome = d["Contact Name"].strip()
            if len(nome) > 16:
                raise ErroDMR(f"Linha {i + 1}: nome com mais de 16 letras.")
            tipo = _TIPO_CSV_CONTATO[int(d["Call Type"])]
            ident = int(d["Call ID"])
            tom = bool(int(d.get("Call Receive Tone", 0) or 0))
        except (KeyError, ValueError) as e:
            raise ErroDMR(f"Linha {i + 1} da planilha com valor inválido ({e}).") from e
        prontos.append((nome, ident, tipo, tom))
    for i, (nome, ident, tipo, tom) in enumerate(prontos, start=1):
        cp.grava_contato(i, nome, ident, tipo, tom)
    for i in range(len(prontos) + 1, TOTAL_CONTATOS + 1):
        if cp.contato_usado(i):
            cp.apaga_contato(i)
    return len(prontos)


def exporta_csv_cps(cp, caminho):
    linhas = [",".join(COLUNAS_CSV_CPS)]
    for n in cp.usados():
        linhas.append(",".join(_linha_csv(bytes(cp.bruto_canal(n)))))
    with open(caminho, "wb") as f:
        f.write(("\r\n".join(linhas) + "\r\n").encode("latin-1", "replace"))
    return len(linhas) - 1


def importa_csv_cps(cp, caminho):
    """Lê a planilha de canais do CPS (Export) e grava os canais 1, 2, 3... na ordem das linhas.
    Os canais que sobrarem depois da última linha são apagados, como no CPS."""
    import csv
    with open(caminho, encoding="latin-1", newline="") as f:
        linhas = list(csv.reader(f))
    if not linhas or linhas[0][:2] != COLUNAS_CSV_CPS[:2]:
        raise ErroDMR("Este arquivo não é uma planilha de canais.")
    cab = linhas[0]
    dados = [dict(zip(cab, r)) for r in linhas[1:] if r and any(x.strip() for x in r)]
    if len(dados) > TOTAL_CANAIS:
        raise ErroDMR(f"A planilha tem mais de {TOTAL_CANAIS} canais.")
    novos = []
    for i, d in enumerate(dados, start=1):
        c = bytearray(cp.bruto_canal(i)) if cp.usado(i) else bytearray(_MODELO_CANAL)
        try:
            c[0] = _bits(c[0], 0, 2, int(d["Channel Mode"]))
            nome = d["Channel Name"]
            if len(nome) > 16:
                raise ErroDMR(f"Linha {i + 1}: nome com mais de 16 letras.")
            struct.pack_into("<II", c, 16, hz_bcd(le_hz(d["RX Frequency(MHz)"])), hz_bcd(le_hz(d["TX Frequency(MHz)"])))
            c[30] = _bits(c[30], 0, 2, _POT_CSV.get(int(d.get("Power", 2)), 3))
            struct.pack_into("<H", c, 6, int(d.get("Contact Name", 0)))
            c[1] = _bits(c[1], 2, 2, int(d.get("Repeater Slot", 0)) + 1)
            struct.pack_into("<HH", c, 24, tom_bin("" if d.get("CTCSS/DCS Dec", "None") == "None" else d["CTCSS/DCS Dec"]),
                             tom_bin("" if d.get("CTCSS/DCS Enc", "None") == "None" else d["CTCSS/DCS Enc"]))
            c[5] = _bits(c[5], 6, 2, _NAOQT_CSV.get(int(d.get("Non-QT/DQT Turn-off Freq", 2)), 3))
            for k, (b, p, n) in _CSV_BITS.items():
                if k in d:
                    c[b] = _bits(c[b], p, n, int(d[k]))
            for k, (b, p) in _CSV_INV.items():
                if k in d:
                    c[b] = _bits(c[b], p, 1, 0 if int(d[k]) else 1)
            for j in range(8):
                if f"Decode {j + 1}" in d:
                    c[14] = _bits(c[14], j, 1, int(d[f"Decode {j + 1}"]))
        except (KeyError, ValueError) as e:
            raise ErroDMR(f"Linha {i + 1} da planilha com valor inválido ({e}).") from e
        c[3] |= 0x34          # bits fixos que o CPS grava ao importar
        c[4] |= 0x08
        c[5] |= 0x0C
        _poe_txt(c, 32, nome, 16)
        novos.append(bytes(c))
    for i, c in enumerate(novos, start=1):
        cp.poe_bruto_canal(i, c)
    sobra = [n for n in cp.usados() if n > len(novos)]
    if sobra:
        cp.apaga_canais(sobra)
    return len(novos)


# ------------------------------------------------------------------ organizar listas
# Reorganiza contatos, grupos de RX, listas de varredura e zonas e atualiza todas as referências
# a eles (como as fórmulas de uma planilha). As posições ocupadas continuam as mesmas; só muda
# o que fica em cada uma. Referências a posições vazias não são tocadas.
class _Organiza:
    def _permuta(self, slots, ordem, off, tam, base=1, vazio=None):
        """slots: posições ocupadas; ordem: as mesmas na nova ordem. Os itens passam a ocupar as
        posições base, base+1, ... sem buracos (como o CPS numera). Devolve {antiga: nova}."""
        if sorted(ordem) != sorted(slots):
            raise ErroDMR("A nova ordem precisa ter os mesmos itens.")
        dados = {s: bytes(self.mem[off(s):off(s) + tam]) for s in slots}
        novos = list(range(base, base + len(ordem)))
        for s in slots:
            if s not in novos:
                self.mem[off(s):off(s) + tam] = vazio if vazio is not None else b"\x00" * tam
        mapa = {}
        for novo, antigo in zip(novos, ordem):
            self.mem[off(novo):off(novo) + tam] = dados[antigo]
            mapa[antigo] = novo
        return mapa

    def reordena_contatos(self, ordem):
        slots = [c["numero"] for c in self.contatos()]
        mapa = self._permuta(slots, ordem, self._cont_off, 36,
                             vazio=bytes.fromhex("ffffffc0") + b"\x00" * 32)
        for n in self.usados():
            oc = OFF_CANAIS + (n - 1) * TAM_CANAL + 6
            v = struct.unpack_from("<H", self.mem, oc)[0]
            if v in mapa:
                struct.pack_into("<H", self.mem, oc, mapa[v])
        for g in self.grupos():
            o = self._grupo_off(g) + 32
            v = list(struct.unpack_from("<32H", self.mem, o))
            struct.pack_into("<32H", self.mem, o, *[mapa.get(x, x) for x in v])
        for k, (_, _, tipo, pos, _) in AJUSTES_GERAIS.items():     # teclas, acesso rápido, GPS
            if tipo == "cont":
                o = OFF_GERAL + pos[0]
                v = struct.unpack_from("<H", self.mem, o)[0]
                if v in mapa:
                    struct.pack_into("<H", self.mem, o, mapa[v])
        return mapa

    def _remapeia_byte_canal(self, byte, mapa):
        for n in self.usados():
            oc = OFF_CANAIS + (n - 1) * TAM_CANAL + byte
            if self.mem[oc] in mapa:
                self.mem[oc] = mapa[self.mem[oc]]

    def reordena_grupos(self, ordem):
        mapa = self._permuta(self.grupos(), ordem, self._grupo_off, 96)
        self._remapeia_byte_canal(12, mapa)
        return mapa

    def reordena_varreduras(self, ordem):
        vazio = bytearray(104)
        vazio[32:42] = bytes.fromhex("fffffffffffff11408ff")
        mapa = self._permuta(self.varreduras(), ordem, self._var_off, 104, vazio=bytes(vazio))
        self._remapeia_byte_canal(11, mapa)
        return mapa

    def reordena_zonas(self, ordem):
        slots = self.zonas()
        ext = {z: bytes(self.mem[OFF_ZONAS_EXT + z * 224:OFF_ZONAS_EXT + z * 224 + 224]) for z in slots}
        mapa = self._permuta(slots, ordem, self._zona_off, 64, base=0)
        for z in slots:
            if z >= len(slots):
                self.mem[OFF_ZONAS_EXT + z * 224:OFF_ZONAS_EXT + z * 224 + 224] = b"\x00" * 224
        for antigo, novo in mapa.items():
            self.mem[OFF_ZONAS_EXT + novo * 224:OFF_ZONAS_EXT + novo * 224 + 224] = ext[antigo]
        return mapa


for _nome, _f in list(vars(_Organiza).items()):
    if callable(_f) and not _nome.startswith("__"):
        setattr(Codeplug, _nome, _f)


# Cabeçalho .rdt (0x225 bytes) + marcador do meio (0x10) usados quando o código é lido pelo USB
# e não há um arquivo do CPS aberto para servir de base.
_MODELO_RDT = {
    "RT3S": "eNpzSSsNTmVUZWRhYAxJLEpPLWFkZGBgCA7wVHDLSSzOULBS8DUyDTA0Y8AFzg5DwMEADA64D1kYfF10Q8OMLQ0Y/kOAMhNDEIMDg0eCsIP4/5v//xsZGFgaGcNkIYCBmQEuEMA4gW1po7W2JoMRA6O7pZGFgbnB/yEEGJgE7zezSDGGurkICBWm9gEAb7iLiA==",
    "DM1701": "eNpzSSsNTmVUZWRhYAxJLEpPLWFkZGBgCA7wVHDLSSzOULBS8DUyDTA0Y8AFzg5DwMEADA64D1kYXHx1Dc0NDBn+Q4ESE0M4gwODR4Kwg/j/EQAYmATvN7NIMYa6uQgIFab2AQDwbqWR",
}


def codeplug_do_radio(mem, modelo="RT3S", base=None, info=None):
    """Monta um Codeplug .rdt a partir da memória lida pelo USB. info: os 256 bytes de dados do rádio
    (modelo, faixas, data, série) lidos dele, que vão no cabeçalho como faz o CPS."""
    if base is not None and base.formato == "rdt":
        cab, meio = base.cab, base.meio
    else:
        import base64
        import zlib
        d = zlib.decompress(base64.b64decode(_MODELO_RDT.get(modelo, _MODELO_RDT["RT3S"])))
        cab, meio = d[:CAB_RDT], d[CAB_RDT:]
    if info is not None and len(info) == 0x100:
        cab = cab[:CAB_RDT - 0x100] + bytes(info)
    return Codeplug(mem, cab, meio, "rdt")

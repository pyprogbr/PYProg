# -*- coding: utf-8 -*-
"""
Icom IC-2730A: arquivo .icf (o mesmo do programa CS-2730), leitura e gravação
pelo cabo e ordenação dos canais.

A memória, os canais, os bancos e os ajustes usam o driver ic2730 do CHIRP
(pasta chirp/, licença GPL-3.0), sem alterações. Este módulo só acrescenta:
  - gravação do .icf no formato do CS-2730 (endereço de 4 dígitos e linha #CD);
  - ordenação dos canais por nome ou frequência, com renumeração;
  - funções simples para a interface.
"""
from __future__ import annotations

import binascii
import hashlib
import os
import tempfile
import time

from chirp import chirp_common, errors, memmap
from chirp.drivers import ic2730, icf

CHAVE = "IC2730A"
NOME = "IC-2730A"
EXTENSAO = ".icf"
TIPO_ARQUIVO = ("Arquivo do CS-2730 (.icf)", "*.icf")
PROGRAMA = "CS-2730"
TEM_NOME = True
TEM_SPLIT = True
BANCO_COM_NOME = True
TEM_AJUSTES = True
TOTAL_CANAIS = 1000
ESPERA_ENTRE_SESSOES = 2.0
TAM_NOME = 6
NOMES_BANCO = "ABCDEFGHIJ"

# Linha #CD do CS-2730: MD5 de uma chave fixa do programa seguida das linhas de dados
# em binário (endereço de 4 dígitos, tamanho e dados). Conferido com um arquivo salvo
# pelo próprio CS-2730.
_CHAVE_CD = binascii.unhexlify("335599993599")
# Valores do cabeçalho do IC-2730A (vêm de um arquivo salvo pelo CS-2730). Ao abrir um
# .icf, os valores do próprio arquivo são mantidos.
CABECALHO_PADRAO = {"MapRev": 1, "EtcData": 0x040014, "Comment": ""}


class ErroIcom(Exception):
    pass


def classe_radio():
    return ic2730.IC2730Radio


# ---------------------------------------------------------------------------- arquivo .icf
def abre_icf(caminho):
    """Abre um .icf do IC-2730A. Retorna o objeto do rádio (driver do CHIRP)."""
    try:
        dados, mm = icf.read_file(caminho)
    except Exception as e:
        raise ErroIcom(f"Não foi possível ler o arquivo: {e}") from e
    modelo = dados.get("model", b"")
    if modelo != ic2730.IC2730Radio._model.encode("latin-1"):
        raise ErroIcom("Este arquivo .icf não é de um IC-2730A (o modelo gravado no arquivo é outro).")
    if len(mm) != ic2730.IC2730Radio._memsize:
        raise ErroIcom("Arquivo .icf com tamanho inesperado para o IC-2730A.")
    r = ic2730.IC2730Radio(mm)
    r._icf_data = {**CABECALHO_PADRAO, **{k: v for k, v in dados.items() if k != "model"}}
    return r


def radio_de_bytes(dados: bytes, cabecalho=None):
    if len(dados) != ic2730.IC2730Radio._memsize:
        raise ErroIcom("Imagem com tamanho inesperado para o IC-2730A.")
    r = ic2730.IC2730Radio(memmap.MemoryMapBytes(bytes(dados)))
    r._icf_data = dict(cabecalho or CABECALHO_PADRAO)
    return r


def texto_icf(radio, comentario=None) -> str:
    """Conteúdo do .icf no formato do CS-2730 (linhas terminadas em CRLF)."""
    dados = radio._mmap.get_packed()
    cab = {**CABECALHO_PADRAO, **getattr(radio, "_icf_data", {})}
    if comentario is not None:
        cab["Comment"] = comentario
    modelo = radio._model
    linhas = ["%02X%02X%02X%02X" % tuple(ord(c) for c in modelo),
              "#Comment=%s" % cab.get("Comment", ""),
              "#MapRev=%i" % int(cab.get("MapRev", 1)),
              "#EtcData=%06X" % int(cab.get("EtcData", 0))]
    h = hashlib.md5(_CHAVE_CD)
    tam = 32
    for end in range(0, len(dados), tam):
        bloco = dados[end:end + tam]
        linha = "%04X%02X%s" % (end, len(bloco), binascii.hexlify(bloco).decode().upper())
        h.update(binascii.unhexlify(linha))
        linhas.append(linha)
    linhas.append("#CD=%s" % h.hexdigest().upper())
    return "".join(l + "\r\n" for l in linhas)


def confere_cd(caminho) -> bool | None:
    """True se a linha #CD do arquivo confere; None se o arquivo não tem #CD."""
    with open(caminho, "rb") as f:
        texto = f.read().decode("ascii", "replace")
    linhas = [l.strip() for l in texto.splitlines() if l.strip()]
    cd = [l[4:] for l in linhas if l.startswith("#CD=")]
    if not cd:
        return None
    h = hashlib.md5(_CHAVE_CD)
    for l in linhas[1:]:
        if not l.startswith("#"):
            h.update(binascii.unhexlify(l))
    return h.hexdigest().upper() == cd[0].upper()


def salva_icf(radio, caminho, comentario=None):
    texto = texto_icf(radio, comentario)
    pasta = os.path.dirname(os.path.abspath(caminho))
    fd, tmp = tempfile.mkstemp(prefix=".pyprog_", suffix=".icf", dir=pasta)
    try:
        with os.fdopen(fd, "w", encoding="ascii", newline="") as f:
            f.write(texto)
        os.replace(tmp, caminho)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ------------------------------------------------------------------------- cabo (clone)
class _Status:
    def __init__(self, progresso, rotulo, faixa):
        self.progresso, self.rotulo, self.faixa = progresso, rotulo, faixa

    def __call__(self, s):
        if not s.max:
            return
        a, b = self.faixa
        pct = a + (b - a) * min(s.cur, s.max) // s.max
        self.progresso(pct, f"{self.rotulo}... {pct}%")


def _abre_porta(porta, classe=None):
    try:
        import serial  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise ErroIcom("Biblioteca 'pyserial' não instalada.") from e
    rc = classe or ic2730.IC2730Radio
    try:
        s = serial.Serial(port=porta, baudrate=rc.BAUD_RATE, rtscts=rc.HARDWARE_FLOW, timeout=0.25,
                          write_timeout=3)
        s.rts = rc.WANTS_RTS
        s.dtr = rc.WANTS_DTR
        return s
    except Exception as e:
        raise ErroIcom(f"Não foi possível abrir a porta {porta}: {e}") from e


def _executa(fn):
    try:
        return fn()
    except errors.RadioNoResponse as e:
        raise ErroIcom("O rádio não respondeu. Confira:\n- se a porta COM escolhida é a do cabo de "
                       "programação;\n- se o cabo está bem encaixado no rádio e no computador;\n"
                       "- se o rádio está ligado.\n\nFeche outros programas que estejam usando essa porta.") from e
    except errors.RadioError as e:
        raise ErroIcom(f"O rádio não respondeu como esperado: {e}\n\nConfira o cabo, a porta COM e se "
                       "o rádio está ligado.") from e
    except Exception as e:
        if type(e).__name__ in ("SerialTimeoutException", "SerialException"):
            raise ErroIcom("A porta COM não respondeu. Confira se ela é a do cabo de programação e se o "
                           "cabo está bem encaixado.") from e
        raise


def _envia_ao_radio(r):
    """Grava a imagem no rádio (pipe já aberto). Mesmos passos do clone_to_radio do CHIRP, mas
    confere a resposta final do rádio: o CHIRP recebe o "Clone OK" e não olha o código que vem
    nele, então uma gravação recusada pelo rádio passava como concluída."""
    r.pipe.baudrate = r.BAUD_RATE
    mdata = icf._id_query_payload(r)
    stream = icf.RadioStream(r.pipe)
    md = icf.get_model_data(r, mdata=mdata, stream=stream)
    if r._double_ident:
        md = icf.get_model_data(r, mdata=mdata, stream=stream)
    if md[0:4] != r.get_model():
        raise ErroIcom("O rádio conectado não é do modelo escolhido no PYProg.")
    try:
        rev_radio = icf.decode_model(md)
    except Exception:
        rev_radio = None
    rev_imagem = r._icf_data.get("MapRev", 1)
    if rev_radio is not None and rev_radio != rev_imagem:
        raise ErroIcom(f"A versão da memória do rádio ({rev_radio}) é diferente da do arquivo ({rev_imagem}).")
    if r.is_hispeed():
        icf.start_hispeed_clone(r, icf.CMD_CLONE_IN)
    else:
        icf.send_clone_frame(r, icf.CMD_CLONE_IN, r.get_model(), raw=True)
    for ini, fim, bs in r.get_ranges():
        icf.send_mem_chunk(r, stream, ini, fim, bs)
    icf.send_clone_frame(r, icf.CMD_CLONE_END, r.get_endframe(), raw=True)
    quadros = []
    for _ in range(10):
        quadros += stream.get_frames(True)
        if quadros:
            break
        time.sleep(0.5)
    if r.ignore_clone_result():
        return
    if not quadros:
        raise errors.RadioNoResponse()
    fim = quadros[-1]
    icf.LOG.info("Resposta final do rádio: comando %02X, dados %s", fim.cmd, bytes(fim.payload).hex())
    if fim.cmd != icf.CMD_CLONE_OK:
        raise ErroIcom("O rádio recusou a gravação.")
    if bytes(fim.payload[:1]) != b"\x00":
        raise ErroIcom(f"O rádio informou erro ao receber a gravação (código {bytes(fim.payload).hex()}). "
                       "A programação do rádio pode não ter sido alterada.")


class _Registro:
    """Guarda num arquivo de texto a conversa com o rádio (para diagnóstico)."""
    def __init__(self, caminho):
        self.caminho, self.h = caminho, None

    def __enter__(self):
        if self.caminho:
            import logging
            self.h = logging.FileHandler(self.caminho, encoding="utf-8")
            self.h.setLevel(logging.DEBUG)
            self.h.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
            lg = logging.getLogger("chirp")
            self.nivel = lg.level
            lg.setLevel(logging.DEBUG)
            lg.addHandler(self.h)
        return self

    def __exit__(self, *a):
        if self.h:
            import logging
            lg = logging.getLogger("chirp")
            lg.removeHandler(self.h)
            lg.setLevel(self.nivel)
            self.h.close()
        return False


def le(porta, progresso=None, cabecalho=None, classe=None):
    """Lê o rádio pelo cabo. Retorna o objeto do rádio."""
    classe = classe or ic2730.IC2730Radio
    progresso = progresso or (lambda p, t: None)
    s = _abre_porta(porta, classe)
    try:
        r = classe(s)
        r.status_fn = _Status(progresso, "Lendo o rádio", (0, 100))
        progresso(0, "Conectando ao rádio...")
        _executa(r.sync_in)
    finally:
        s.close()
    r._icf_data = dict(cabecalho or (CABECALHO_PADRAO if classe is ic2730.IC2730Radio else {}))
    return r


def le_e_grava(porta, radio, progresso=None, apos_leitura=None, classe=None, registro=None):
    """Lê o rádio (cópia de segurança) e grava a programação nova, com a porta aberta uma vez.
    apos_leitura(radio_lido) é chamada antes de gravar; se ela falhar, nada é gravado."""
    classe = classe or ic2730.IC2730Radio
    progresso = progresso or (lambda p, t: None)
    s = _abre_porta(porta, classe)
    try:
        atual = classe(s)
        atual.status_fn = _Status(progresso, "Lendo cópia de segurança", (0, 50))
        progresso(0, "Conectando ao rádio...")
        _executa(atual.sync_in)
    finally:
        s.close()
    atual._icf_data = dict(getattr(radio, "_icf_data", CABECALHO_PADRAO))
    if apos_leitura:
        apos_leitura(atual)
    # A leitura em alta velocidade deixa a porta em 38400; a gravação começa de novo em 9600,
    # depois de o rádio sair do modo de clonagem.
    time.sleep(ESPERA_ENTRE_SESSOES)
    s = _abre_porta(porta, classe)
    try:
        novo = classe(memmap.MemoryMapBytes(radio._mmap.get_packed()))
        novo._icf_data = dict(atual._icf_data)
        novo.pipe = s
        novo.status_fn = _Status(progresso, "Gravando no rádio", (50, 100))
        with _Registro(registro):
            _executa(lambda: _envia_ao_radio(novo))
        return atual
    finally:
        s.close()


def grava(porta, radio, progresso=None, classe=None, registro=None):
    """Grava a programação sem ler o rádio antes (sem cópia de segurança)."""
    classe = classe or ic2730.IC2730Radio
    progresso = progresso or (lambda p, t: None)
    s = _abre_porta(porta, classe)
    try:
        novo = classe(memmap.MemoryMapBytes(radio._mmap.get_packed()))
        novo._icf_data = dict(getattr(radio, "_icf_data", None) or CABECALHO_PADRAO)
        novo.pipe = s
        novo.status_fn = _Status(progresso, "Gravando no rádio", (0, 100))
        progresso(0, "Conectando ao rádio...")
        with _Registro(registro):
            _executa(lambda: _envia_ao_radio(novo))
    finally:
        s.close()


# ------------------------------------------------------------------------------ canais
def imagem(radio) -> bytes:
    return bytes(radio._mmap.get_packed())


def banco_de(radio, numero):
    """Letra do banco (A a J) e posição dentro dele, ou (None, None)."""
    b = radio._get_bank(numero)
    if b is None or int(b) >= len(NOMES_BANCO):
        return None, None
    return NOMES_BANCO[int(b)], int(radio._get_bank_index(numero))


def define_banco(radio, numero, letra, posicao=None):
    if not letra:
        radio._set_bank(numero, None)
        return
    b = NOMES_BANCO.index(letra)
    if posicao is None:
        usadas = {int(radio._get_bank_index(n)) for n in range(TOTAL_CANAIS)
                  if n != numero and radio._get_bank(n) is not None and int(radio._get_bank(n)) == b}
        posicao = next(i for i in range(100) if i not in usadas)
    radio._set_bank(numero, b)
    radio._set_bank_index(numero, posicao)


def nomes_bancos(radio):
    return [str(radio._memobj.bank_names[i].name).rstrip() for i in range(len(NOMES_BANCO))]


def define_nome_banco(radio, i, nome):
    radio._memobj.bank_names[i].name = nome.upper()[:6].ljust(6)


def usados(radio):
    return [n for n in range(TOTAL_CANAIS) if not radio.get_memory(n).empty]


def _chave_nome(m):
    return (m.name.strip().casefold() == "", m.name.strip().casefold(), m.freq, m.number)


def _chave_freq(m):
    return (m.freq, m.name.strip().casefold(), m.number)


def _bit(arr, n):
    return bool(int(arr[n // 8]) & (1 << (n % 8)))


def _poe_bit(arr, n, valor):
    b = int(arr[n // 8])
    arr[n // 8] = (b | (1 << (n % 8))) if valor else (b & ~(1 << (n % 8)) & 0xFF)


def aplica_ordem(radio, ordem):
    """Regrava os canais na ordem dada: ordem[k] é o número antigo do canal que vai para a
    posição k (None = vazio). Os bytes de cada canal vão inteiros (inclusive campos que o
    CHIRP não decodifica), com as marcas de varredura e o banco. Retorna {antigo: novo}."""
    mo = radio._memobj
    salvo, vazio_banco = {}, None
    for n in range(TOTAL_CANAIS):
        if _bit(mo.used_flags, n):            # bit ligado = vazio
            if vazio_banco is None:
                vazio_banco = bytes(mo.bank_info[n].get_raw())
            continue
        salvo[n] = (bytes(mo.memory[n].get_raw()), _bit(mo.skip_flags, n), _bit(mo.pskip_flags, n),
                    bytes(mo.bank_info[n].get_raw()))
    tam = len(bytes(mo.memory[0].get_raw()))
    mapa = {}
    for k in range(TOTAL_CANAIS):
        velho = ordem[k] if k < len(ordem) else None
        if velho is not None and velho in salvo:
            bruto, pula, prio, banco = salvo[velho]
            mo.memory[k].set_raw(bruto)
            _poe_bit(mo.used_flags, k, False)
            _poe_bit(mo.skip_flags, k, pula)
            _poe_bit(mo.pskip_flags, k, prio)
            mo.bank_info[k].set_raw(banco)
            mapa[velho] = k
        elif not _bit(mo.used_flags, k) or (k in salvo):
            mo.memory[k].set_raw(b"\xFF" * tam)
            _poe_bit(mo.used_flags, k, True)
            _poe_bit(mo.skip_flags, k, False)
            _poe_bit(mo.pskip_flags, k, False)
            mo.bank_info[k].set_raw(vazio_banco or b"\x1F\xFF")
    return mapa


def ordena(radio, por="nome"):
    """Ordena os canais em uso por nome (A a Z) ou por frequência e renumera a partir do 000.
    Canais vazios vão para o fim. Retorna o mapa {número antigo: número novo}."""
    if por not in ("nome", "frequencia"):
        raise ValueError(por)
    canais = [radio.get_memory(n) for n in range(TOTAL_CANAIS)]
    canais = [m for m in canais if not m.empty]
    canais.sort(key=_chave_nome if por == "nome" else _chave_freq)
    ordem = [m.number for m in canais]
    if ordem == list(range(len(ordem))):
        return {n: n for n in ordem}
    return aplica_ordem(radio, ordem)


def move(radio, numeros, destino, depois=False):
    """Arrastar: põe os canais 'numeros' antes (ou depois) de 'destino'; os do meio se deslocam."""
    import arrastar
    ordem = list(range(TOTAL_CANAIS))
    nova = arrastar.move_bloco(ordem, numeros, destino, depois)
    if nova == ordem:
        return {}
    return aplica_ordem(radio, nova)


# Rótulos em português para as listas do CHIRP
DUPLEX = {"": "Simplex", "+": "+", "-": "-", "split": "TX separado", "off": "Sem TX"}
TOM = {"": "Nenhum", "Tone": "Tom TX", "TSQL": "Tom TX e RX", "DTCS": "DCS", "TSQL-R": "Tom RX (reverso)",
       "DTCS-R": "DCS (reverso)", "Cross": "Cruzado"}
# Opções de tom como no CS-2730: (modo do CHIRP, modo cruzado) -> texto
OPCOES_TOM = [(("", None), "Nenhum"), (("Tone", None), "Tom TX"), (("TSQL", None), "Tom TX e RX"),
              (("DTCS", None), "DCS"), (("TSQL-R", None), "Tom RX (reverso)"), (("DTCS-R", None), "DCS (reverso)"),
              (("Cross", "DTCS->"), "DCS só no TX"), (("Cross", "Tone->DTCS"), "Tom no TX, DCS no RX"),
              (("Cross", "DTCS->Tone"), "DCS no TX, tom no RX"), (("Cross", "Tone->Tone"), "Tom no TX, outro tom no RX")]
# campos usados por cada opção
CAMPOS_TOM = {("Tone", None): ("rtone",), ("TSQL", None): ("rtone",), ("TSQL-R", None): ("rtone",),
              ("DTCS", None): ("dtcs", "pol"), ("DTCS-R", None): ("dtcs", "pol"),
              ("Cross", "DTCS->"): ("dtcs", "pol"), ("Cross", "Tone->DTCS"): ("rtone", "dtcs", "pol"),
              ("Cross", "DTCS->Tone"): ("dtcs", "pol", "ctone"), ("Cross", "Tone->Tone"): ("rtone", "ctone")}


def opcao_tom(m):
    return (m.tmode, m.cross_mode if m.tmode == "Cross" else None)


PULAR = {"": "Sim", "S": "Não", "P": "Prioritário"}


def descreve_tom(m):
    if m.tmode == "Tone":
        return f"TX {m.rtone:.1f}"
    if m.tmode == "TSQL":
        return f"{m.ctone:.1f}"
    if m.tmode == "DTCS":
        return f"D{m.dtcs:03d}{m.dtcs_polarity[0]}"
    if m.tmode == "TSQL-R":
        return f"RX {m.ctone:.1f}"
    if m.tmode == "DTCS-R":
        return f"D{m.dtcs:03d} rev."
    if m.tmode == "Cross":
        d = f"D{m.dtcs:03d}{m.dtcs_polarity[0]}"
        return {"DTCS->": f"{d} TX", "Tone->DTCS": f"TX {m.rtone:.1f}/{d}",
                "DTCS->Tone": f"{d}/RX {m.ctone:.1f}", "Tone->Tone": f"TX {m.rtone:.1f}/RX {m.ctone:.1f}"
                }.get(m.cross_mode, m.cross_mode)
    return ""


def valida(radio, m):
    msgs = radio.validate_memory(m)
    erros = [str(x) for x in msgs if isinstance(x, chirp_common.ValidationError)]
    if erros:
        raise ErroIcom("\n".join(erros))
    return [str(x) for x in msgs]


# Nomes comuns aos dois Icom (a interface usa estes)
abre_arquivo = abre_icf
salva_arquivo = salva_icf

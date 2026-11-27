# -*- coding: utf-8 -*-
"""
Programação completa do UV-17 Pro GPS / UV-17 Pro (e, com menos recursos, do UV-5R):
canais, zonas e ajustes.

Trabalha sobre a imagem de memória lida do rádio (configuracao_radio.py),
seguindo o mapa de memória do driver baofeng_uv17Pro do CHIRP:
  - 1000 canais de 32 bytes a partir do endereço 0;
  - 10 zonas fixas de 100 canais, com nomes em 0x8280 (16 bytes cada);
  - ajustes (64 bytes) na posição 0x8040 da imagem.
Bytes desconhecidos são sempre preservados.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import uv5r

TOTAL_CANAIS = 1000
CANAIS_POR_ZONA = 100
TOTAL_ZONAS = 10
POS_AJUSTES = 0x8040
POS_ZONAS = 0x8280
# DTMF (só UV-17 Pro GPS, conferido com o mapa do rádio): Radio ID e 20 entradas de 16 bytes.
# Cada código é guardado como o índice do símbolo na sequência abaixo, com 0xFF nas sobras;
# o nome vem em ASCII logo depois do código, também com 0xFF no final.
POS_RADIO_ID = 0x8080
POS_DTMF = 0x80A0
TOTAL_DTMF = 20
DTMF_SIMBOLOS = "0123456789ABCD*#"

TONS_CTCSS = (
    67.0, 69.3, 71.9, 74.4, 77.0, 79.7, 82.5, 85.4, 88.5, 91.5, 94.8, 97.4, 100.0, 103.5,
    107.2, 110.9, 114.8, 118.8, 123.0, 127.3, 131.8, 136.5, 141.3, 146.2, 151.4, 156.7,
    159.8, 162.2, 165.5, 167.9, 171.3, 173.8, 177.3, 179.9, 183.5, 186.2, 189.9, 192.8,
    196.6, 199.5, 203.5, 206.5, 210.7, 218.1, 225.7, 229.1, 233.6, 241.8, 250.3, 254.1,
)
CODIGOS_DCS = tuple(sorted((
    23, 25, 26, 31, 32, 36, 43, 47, 51, 53, 54, 65, 71, 72, 73, 74, 114, 115, 116, 122, 125,
    131, 132, 134, 143, 145, 152, 155, 156, 162, 165, 172, 174, 205, 212, 223, 225, 226, 243,
    244, 245, 246, 251, 252, 255, 261, 263, 265, 266, 271, 274, 306, 311, 315, 325, 331, 332,
    343, 346, 351, 356, 364, 365, 371, 411, 412, 413, 423, 431, 432, 445, 446, 452, 454, 455,
    462, 464, 465, 466, 503, 506, 516, 523, 526, 532, 546, 565, 606, 612, 624, 627, 631, 632,
    654, 662, 664, 703, 712, 723, 731, 732, 734, 743, 754, 645)))

SEM_TOM = "Desligado"
OPCOES_TOM = ([SEM_TOM] + [f"{t:.1f}" for t in TONS_CTCSS]
              + [f"D{c:03d}N" for c in CODIGOS_DCS] + [f"D{c:03d}I" for c in CODIGOS_DCS])
POTENCIAS = ["Alta", "Baixa"]
LARGURAS = ["Larga (FM)", "Estreita (NFM)"]
PTTID = ["Desligado", "Início (BOT)", "Fim (EOT)", "Ambos"]
SCODES = [str(i) for i in range(1, 21)]
DUPLEX = ["Simplex", "+", "-", "TX separado", "Sem TX"]

FAIXAS_TX = [(136.0, 174.0), (200.0, 260.0), (350.0, 390.0), (400.0, 520.0)]
FAIXA_AM = (108.0, 136.0)


class ErroProgramacao(Exception):
    pass


# ---------------------------------------------------------------- utilidades

def _bcd_le(dados: bytes) -> int:
    v = 0
    for b in reversed(dados):
        v = v * 100 + (b >> 4) * 10 + (b & 15)
    return v


def _para_bcd_le(valor: int, n=4) -> bytes:
    out = bytearray()
    for _ in range(n):
        dois = valor % 100
        out.append(((dois // 10) << 4) | (dois % 10))
        valor //= 100
    return bytes(out)


def decodifica_tom(v: int) -> str:
    if v in (0, 0xFFFF):
        return SEM_TOM
    if v >= 0x0258:
        return f"{v / 10.0:.1f}"
    if v > 0x69:
        i, pol = v - 0x6A, "I"
    else:
        i, pol = v - 1, "N"
    if 0 <= i < len(CODIGOS_DCS):
        return f"D{CODIGOS_DCS[i]:03d}{pol}"
    return SEM_TOM


def codifica_tom(txt: str) -> int:
    txt = (txt or "").strip().upper()
    if not txt or txt in (SEM_TOM.upper(), "OFF", "DESLIGADO"):
        return 0
    if txt.startswith("D"):
        pol = txt[-1] if txt[-1] in "NI" else "N"
        cod = int(txt[1:4] if txt[-1] in "NI" else txt[1:])
        if cod not in CODIGOS_DCS:
            raise ErroProgramacao(f"Código DCS inválido: {txt}")
        i = CODIGOS_DCS.index(cod) + 1
        return i + 0x69 if pol == "I" else i
    try:
        f = float(txt.replace(",", "."))
    except ValueError:
        raise ErroProgramacao(f"Tom inválido: {txt}")
    if round(f, 1) not in TONS_CTCSS:
        raise ErroProgramacao(f"Tom CTCSS inválido: {txt}")
    return int(round(f * 10))


def mhz(hz: int) -> str:
    """MHz com pelo menos 3 casas decimais (145.500, 0.600); mais casas só quando
    a frequência precisa (462.5625, 145.00625)."""
    if not hz:
        return ""
    inteiro, dec = f"{hz / 1e6:.6f}".split(".")
    dec = dec.rstrip("0").ljust(3, "0")
    return f"{inteiro}.{dec}"


def le_mhz(txt: str) -> int:
    t = (txt or "").strip().replace(",", ".")
    if not t:
        raise ErroProgramacao("Frequência vazia.")
    try:
        v = float(t)
    except ValueError:
        raise ErroProgramacao(f"Frequência inválida: {txt}")
    if v > 10000:          # digitada em kHz ou Hz
        v = v / 1000 if v < 1e7 else v / 1e6
    hz = int(round(v * 1e6 / 10)) * 10
    return hz


def faixa_valida_rx(hz):
    f = hz / 1e6
    return FAIXA_AM[0] <= f <= FAIXA_AM[1] or any(a <= f <= b for a, b in FAIXAS_TX)


def faixa_valida_tx(hz):
    f = hz / 1e6
    return any(a <= f <= b for a, b in FAIXAS_TX)


# --------------------------------------------------------------------- canal

@dataclass
class Canal:
    numero: int
    vazio: bool = True
    nome: str = ""
    rx: int = 0            # Hz
    duplex: str = "Simplex"
    offset: int = 0        # Hz (para + e -) ou frequência de TX (TX separado)
    tom_tx: str = SEM_TOM
    tom_rx: str = SEM_TOM
    potencia: str = "Alta"
    largura: str = "Larga (FM)"
    varredura: bool = True
    bcl: bool = False
    pttid: str = "Desligado"
    scode: str = "1"
    bruto: bytes = field(default=b"\xff" * 32, repr=False)
    perfil: object = field(default=None, repr=False, compare=False)   # None = UV-17

    @property
    def p(self):
        return self.perfil or PERFIL_UV17

    @property
    def zona(self):
        return (self.numero - 1) // self.p.canais_por_zona + 1

    @property
    def rotulo(self):
        """Número como aparece no rádio (o UV-5R começa em 000)."""
        return self.p.rotulo(self.numero)

    @property
    def tx(self):
        if self.duplex == "Sem TX":
            return None
        if self.duplex == "+":
            return self.rx + self.offset
        if self.duplex == "-":
            return self.rx - self.offset
        if self.duplex == "TX separado":
            return self.offset
        return self.rx

    @property
    def modo(self):
        if self.p.am and FAIXA_AM[0] <= self.rx / 1e6 < FAIXA_AM[1]:
            return "AM"
        return "FM" if self.largura.startswith("Larga") else "NFM"

    def valida(self):
        if self.vazio:
            return
        p = self.p
        if not p.rx_valido(self.rx):
            raise ErroProgramacao(f"Canal {self.rotulo}: RX {mhz(self.rx)} MHz fora das faixas do rádio.")
        tx = self.tx
        if tx is not None and self.modo != "AM" and not p.tx_valido(tx):
            raise ErroProgramacao(f"Canal {self.rotulo}: TX {mhz(tx)} MHz fora das faixas de transmissão.")
        codifica_tom(self.tom_tx)
        codifica_tom(self.tom_rx)
        try:
            self.nome.encode("ascii")
        except UnicodeEncodeError:
            raise ErroProgramacao(f"Canal {self.rotulo}: o nome só aceita letras sem acento.")
        if len(self.nome) > p.nome_max:
            raise ErroProgramacao(f"Canal {self.rotulo}: o nome aceita no máximo {p.nome_max} letras.")
        if p.caracteres:
            ruins = sorted({ch for ch in self.nome.upper() if ch not in p.caracteres})
            if ruins:
                raise ErroProgramacao(f"Canal {self.rotulo}: o visor deste rádio não mostra: {' '.join(ruins)}")
        if self.scode not in p.scodes:
            raise ErroProgramacao(f"Canal {self.rotulo}: código S-Code inválido para este rádio.")


def decodifica_canal(numero: int, b: bytes) -> Canal:
    c = Canal(numero=numero, bruto=bytes(b))
    if b[0] == 0xFF:
        return c
    c.vazio = False
    c.rx = _bcd_le(b[0:4]) * 10
    if b[4:8] == b"\xff\xff\xff\xff":
        c.duplex, c.offset = "Sem TX", 0
    else:
        tx = _bcd_le(b[4:8]) * 10
        dif = tx - c.rx
        if dif == 0:
            c.duplex = "Simplex"
        elif abs(dif) > 70_000_000:
            c.duplex, c.offset = "TX separado", tx
        elif dif > 0:
            c.duplex, c.offset = "+", dif
        else:
            c.duplex, c.offset = "-", -dif
    c.tom_rx = decodifica_tom(b[8] | (b[9] << 8))
    c.tom_tx = decodifica_tom(b[10] | (b[11] << 8))
    c.scode = SCODES[b[12] % len(SCODES)]
    c.pttid = PTTID[b[13]] if b[13] < len(PTTID) else PTTID[0]
    pot = b[14] & 0x03
    c.potencia = POTENCIAS[pot] if pot < len(POTENCIAS) else POTENCIAS[0]
    c.largura = LARGURAS[1] if b[15] & 0x40 else LARGURAS[0]
    c.bcl = bool(b[15] & 0x08)
    c.varredura = bool(b[15] & 0x04)
    nome = bytes(b[20:32]).split(b"\xff")[0].replace(b"\x00", b" ")
    c.nome = nome.decode("ascii", "replace").rstrip()
    return c


def codifica_canal(c: Canal) -> bytes:
    if c.vazio:
        return b"\xff" * 32
    c.valida()
    b = bytearray(c.bruto)
    if b[0] == 0xFF:                        # canal novo: padrão do CHIRP
        b = bytearray(b"\x00" * 16 + b"\xff" * 16)
    b[0:4] = _para_bcd_le(c.rx // 10)
    tx = c.tx
    b[4:8] = b"\xff\xff\xff\xff" if tx is None else _para_bcd_le(tx // 10)
    v = codifica_tom(c.tom_rx)
    b[8], b[9] = v & 0xFF, v >> 8
    v = codifica_tom(c.tom_tx)
    b[10], b[11] = v & 0xFF, v >> 8
    b[12] = SCODES.index(c.scode) if c.scode in SCODES else 0
    b[13] = PTTID.index(c.pttid) if c.pttid in PTTID else 0
    b[14] = (b[14] & 0xFC) | POTENCIAS.index(c.potencia)
    b[15] = (b[15] & ~(0x40 | 0x08 | 0x04)) & 0xFF
    if c.largura != LARGURAS[0]:
        b[15] |= 0x40
    if c.bcl:
        b[15] |= 0x08
    if c.varredura:
        b[15] |= 0x04
    nome = c.nome.encode("ascii")[:12]
    b[20:32] = nome + b"\xff" * (12 - len(nome))
    return bytes(b)


# -------------------------------------------------------------------- ajustes

def _lista(*itens):
    return list(itens)


TIMEOUT = ["Desligado"] + [f"{s} s" for s in range(15, 195, 15)]
TECLA2 = [("FM", 0x07), ("Varredura", 0x1C), ("Busca", 0x1D), ("VOX", 0x2D)]

# (chave, posição no bloco de ajustes, rótulo, opções | "bool", grupo, [máscara, deslocamento])
AJUSTES = [
    ("squelch", 0, "Squelch (silenciador)", ["Desligado", "1", "2", "3", "4", "5"], "Geral"),
    ("tot", 5, "Tempo limite de transmissão (TOT)", TIMEOUT, "Geral"),
    ("totalarm", 40, "Alarme antes do TOT", ["Desligado"] + [f"{s} s" for s in range(1, 11)], "Geral"),
    ("savemode", 1, "Economia de bateria", ["Desligada", "Ligada"], "Geral"),
    ("dualstandby", 4, "Dupla escuta", ["Desligada", "Ligada"], "Geral"),
    ("chaworkmode", 26, "Modo de trabalho A", ["Frequência", "Canal"], "Geral", 0x0F, 0),
    ("chbworkmode", 26, "Modo de trabalho B", ["Frequência", "Canal"], "Geral", 0xF0, 4),
    ("chadistype", 13, "Exibição do canal A", ["Nome", "Frequência", "Número do canal"], "Visor"),
    ("chbdistype", 14, "Exibição do canal B", ["Nome", "Frequência", "Número do canal"], "Visor"),
    ("powerondistype", 28, "Tela ao ligar", ["Logotipo", "Tensão da bateria"], "Visor"),
    ("backlight", 3, "Luz de fundo", ["Sempre acesa"] + [f"{s} s" for s in range(5, 25, 5)], "Visor"),
    ("menuquittime", 33, "Saída automática do menu", [f"{s} s" for s in range(5, 55, 5)] + ["60 s"], "Visor"),
    ("voicesw", 7, "Aviso de voz ligado", "bool", "Som e voz"),
    ("voice", 8, "Idioma da voz", ["Inglês (vozes editáveis)", "Chinês"], "Som e voz"),
    ("beep", 6, "Bipe das teclas", ["Desligado", "Bipe", "Voz", "Ambos"], "Som e voz"),
    ("roger", 23, "Bipe de fim de transmissão (Roger)", "bool", "Som e voz"),
    ("tailclear", 20, "Eliminação de cauda", "bool", "Som e voz"),
    ("sidetone", 9, "Tom lateral", ["Desligado", "Teclado", "ANI", "Teclado + ANI"], "Som e voz"),
    ("tone", 29, "Tom piloto (1750 Hz etc.)", ["1000 Hz", "1450 Hz", "1750 Hz", "2100 Hz"], "Som e voz"),
    ("fmenable", 25, "Desabilitar rádio FM", "bool", "Som e voz"),
    ("voxsw", 58, "VOX ligado", "bool", "VOX"),
    ("vox", 2, "Nível do VOX", [str(i) for i in range(1, 10)], "VOX"),
    ("voxdlytime", 32, "Atraso do VOX", [f"{s} ms" for s in range(500, 2100, 100)], "VOX"),
    ("scanmode", 10, "Modo de varredura", ["Por tempo", "Por portadora", "Busca"], "Varredura"),
    ("ctsdcsscantype", 43, "Salvar tom encontrado (QT)", ["RX e TX", "Só RX", "Só TX"], "Varredura"),
    ("rpttailclear", 21, "Eliminação de cauda da repetidora", [f"{s} ms" for s in range(0, 1100, 100)], "Repetidora"),
    ("rpttaildet", 22, "Detecção de cauda da repetidora", [f"{s} ms" for s in range(0, 1100, 100)], "Repetidora"),
    ("autolock", 16, "Bloqueio automático do teclado", "bool", "Teclas"),
    ("keylock", 27, "Teclado bloqueado", "bool", "Teclas"),
    ("key2short", 52, "Tecla lateral 2 (toque curto)", [n for n, _ in TECLA2], "Teclas"),
    ("rstmenu", 55, "Permitir reset pelo menu", "bool", "Teclas"),
    ("alarmmode", 17, "Modo do alarme", ["Local", "Enviar tom", "Enviar código"], "Alarme"),
    ("alarmtone", 18, "Som do alarme", "bool", "Alarme"),
    ("pttdly", 12, "Atraso do envio de ID", [f"{s} ms" for s in range(100, 3100, 100)], "Alarme"),
    ("gpsw", 48, "GPS ligado", "bool", "GPS"),
    ("gpsmode", 49, "Sistema", ["GPS", "Beidou", "GPS + Beidou"], "GPS"),
    ("gpstimezone", 59, "Fuso horário", [f"{h:+d}" if h else "0" for h in range(-12, 13)], "GPS"),
]
SO_GPS = {"voxsw", "tone", "pttdly", "key2short", "gpsw", "gpsmode", "gpstimezone"}
PREFIXO_DESCONHECIDO = "Valor atual do rádio: "


def ajustes_do_modelo(chave_modelo):
    """Lista de ajustes válida para o modelo (o UV-17 Pro não tem GPS, chave VOX etc.)."""
    if chave_modelo == "UV5R":
        return uv5r.AJUSTES
    if chave_modelo in ("UV17ProGPS", "UV21ProGPS"):
        return AJUSTES
    out = []
    for a in AJUSTES:
        if a[0] in SO_GPS:
            continue
        if a[0] == "vox":
            a = ("vox", 2, "Nível do VOX", ["Desligado"] + [str(i) for i in range(1, 10)], "VOX")
        out.append(a)
    return out


def _desc(a):
    chave, pos, rotulo, opcoes, grupo = a[:5]
    mask, shift = (a[5], a[6]) if len(a) > 5 else (0xFF, 0)
    return chave, pos, rotulo, opcoes, grupo, mask, shift


def le_ajuste(img: bytes, chave: str, defs=None, base=POS_AJUSTES):
    """Retorna o texto da opção atual (ou bool, ou texto livre)."""
    for a in (defs or AJUSTES):
        k, pos, _, opcoes, _, mask, shift = _desc(a)
        if k != chave:
            continue
        if isinstance(opcoes, tuple) and opcoes[0] == "texto":
            return uv5r.le_texto(img, base + pos, opcoes[1])
        v = (img[base + pos] & mask) >> shift
        if opcoes == "bool":
            return bool(v)
        if k == "key2short":
            for nome, cod in TECLA2:
                if cod == v:
                    return nome
            return TECLA2[0][0]
        return opcoes[v] if v < len(opcoes) else f"{PREFIXO_DESCONHECIDO}{v}"
    raise KeyError(chave)


def grava_ajuste(img: bytearray, chave: str, valor, defs=None, base=POS_AJUSTES):
    for a in (defs or AJUSTES):
        k, pos, _, opcoes, _, mask, shift = _desc(a)
        if k != chave:
            continue
        if isinstance(opcoes, tuple) and opcoes[0] == "texto":
            try:
                uv5r.grava_texto(img, base + pos, opcoes[1], valor)
            except uv5r.ErroUV5R as e:
                raise ErroProgramacao(str(e))
            return
        if isinstance(valor, str) and valor.startswith(PREFIXO_DESCONHECIDO):
            return
        if opcoes == "bool":
            v = 1 if valor else 0
        elif k == "key2short":
            v = dict(TECLA2)[valor]
        else:
            v = opcoes.index(valor)
        atual = img[base + pos]
        img[base + pos] = (atual & ~mask & 0xFF) | ((v << shift) & mask)
        return
    raise KeyError(chave)


# --------------------------------------------------------------------- zonas

def le_nome_zona(img: bytes, i: int) -> str:
    # Nome termina em 0xFF ou 0x00; bytes de controle que sobram não são letras e saem do nome
    b = bytes(img[POS_ZONAS + i * 16: POS_ZONAS + (i + 1) * 16]).split(b"\xff")[0].split(b"\x00")[0]
    try:
        texto = b.decode("gb2312")
    except UnicodeDecodeError:
        texto = b.decode("latin-1")
    return "".join(ch for ch in texto if ch.isprintable()).strip()


def grava_nome_zona(img: bytearray, i: int, nome: str):
    try:
        b = nome.encode("ascii")[:16]
    except UnicodeEncodeError:
        raise ErroProgramacao("O nome da zona só aceita letras sem acento.")
    img[POS_ZONAS + i * 16: POS_ZONAS + (i + 1) * 16] = b + b"\xff" * (16 - len(b))


# ------------------------------------------------------------------- DTMF

def _le_codigo(b: bytes):
    """Lê os índices de símbolos do começo do bloco; devolve (texto, posição depois do código)."""
    txt, i = "", 0
    while i < len(b) and b[i] < len(DTMF_SIMBOLOS):
        txt += DTMF_SIMBOLOS[b[i]]
        i += 1
    return txt, i


def le_radio_id(img) -> str:
    return _le_codigo(bytes(img[POS_RADIO_ID:POS_RADIO_ID + 16]))[0]


def grava_radio_id(img, txt: str):
    if not txt.isdigit() or len(txt) > 16:
        raise ErroProgramacao("O Radio ID aceita só números, de 1 a 16 dígitos.")
    for k, c in enumerate(txt):
        img[POS_RADIO_ID + k] = DTMF_SIMBOLOS.index(c)
    # as sobras até a posição 6 ficam em 0xFF, como no mapa original; a partir daí o rádio guarda outros bytes
    for k in range(len(txt), 7):
        img[POS_RADIO_ID + k] = 0xFF


def le_dtmf(img, n: int):
    """(código, nome) da entrada n (1 a 20)."""
    slot = POS_DTMF + (n - 1) * 16
    cod, i = _le_codigo(bytes(img[slot:slot + 16]))
    nome = bytes(img[slot + i:slot + 16]).split(b"\xff")[0].decode("ascii", "replace").strip()
    return cod, nome


def grava_dtmf(img, n: int, codigo: str, nome: str = ""):
    """Grava a entrada n. Código vazio apaga a entrada."""
    slot = POS_DTMF + (n - 1) * 16
    if not codigo:
        img[slot:slot + 16] = b"\xff" * 16
        return
    if len(codigo) > 16 or any(c not in DTMF_SIMBOLOS for c in codigo):
        raise ErroProgramacao("O código DTMF aceita de 1 a 16 caracteres: 0-9, A-D, * e #.")
    try:
        b_nome = nome.upper().encode("ascii")
    except UnicodeEncodeError:
        raise ErroProgramacao("O nome DTMF só aceita letras sem acento.")
    if len(codigo) + len(b_nome) > 16:
        raise ErroProgramacao(f"Código e nome juntos passam de 16 caracteres. "
                              f"Com este código, o nome aceita até {16 - len(codigo)} caracteres.")
    cod = bytes(DTMF_SIMBOLOS.index(c) for c in codigo)
    img[slot:slot + 16] = cod + b_nome + b"\xff" * (16 - len(cod) - len(b_nome))


# -------------------------------------------------------------- programação

class Programacao:
    def __init__(self, imagem: bytes, chave: str = "UV17ProGPS"):
        self.perfil = perfil_de(chave, imagem)
        if len(imagem) not in self.perfil.tamanhos:
            raise ErroProgramacao("Imagem de tamanho inesperado.")
        self.chave = chave
        self.img = bytearray(imagem)
        p = self.perfil
        self.canais = [p.decodifica(i + 1, p.bruto(self.img, i)) for i in range(p.total_canais)]
        self.tx_bloqueados = {}   # nº -> TX original de canais bloqueados pelo programa

    def canal(self, numero) -> Canal:
        return self.canais[numero - 1]

    def decodifica(self, numero, bruto) -> Canal:
        return self.perfil.decodifica(numero, bruto)

    def define_canal(self, c: Canal):
        p = self.perfil
        c.perfil = p
        b = p.codifica(c)
        p.grava_bruto(self.img, c.numero - 1, b)
        self.canais[c.numero - 1] = p.decodifica(c.numero, b)

    def apaga(self, numero):
        self.define_canal(Canal(numero=numero, perfil=self.perfil))

    def imagem(self) -> bytes:
        return bytes(self.img)

    def reordena(self, inicio, ordem):
        """Põe os canais de 'ordem' (números antigos) nas posições inicio, inicio+1, ...
        Os bytes de cada canal vão inteiros; o TX guardado dos canais bloqueados acompanha.
        Retorna {número antigo: número novo}."""
        p = self.perfil
        brutos = [bytes(p.bruto(self.img, n - 1)) for n in ordem]
        mapa = {velho: inicio + k for k, velho in enumerate(ordem)}
        for k, b in enumerate(brutos):
            n = inicio + k
            p.grava_bruto(self.img, n - 1, b)
            self.canais[n - 1] = p.decodifica(n, b)
        bloq = {}
        for n, o in self.tx_bloqueados.items():
            bloq[mapa.get(n, n)] = o
        self.tx_bloqueados = bloq
        return mapa

    def usados(self):
        return sum(1 for c in self.canais if not c.vazio)

# ------------------------------------------------------- bloqueio de TX

FAIXAS_RADIOAMADOR_BR = [
    (144.0, 148.0, "VHF 2 m (radioamador)"),
    (220.0, 225.0, "VHF 1,3 m (radioamador)"),
    (430.0, 440.0, "UHF 70 cm (radioamador)"),
    (462.0, 467.0, "FRS"),
]
FAIXAS_LIBERADAS_PADRAO = list(FAIXAS_RADIOAMADOR_BR)


def em_faixa_radioamador(hz):
    # Bordas inclusivas, com a mesma regra de dentro_das_faixas (cores e avisos da lista).
    return hz is not None and dentro_das_faixas(hz, FAIXAS_RADIOAMADOR_BR)


def candidatos_radioamador(prog, acao):
    if acao not in ("bloquear", "liberar"):
        raise ErroProgramacao("Ação de TX desconhecida.")
    numeros = []
    for c in prog.canais:
        if c.vazio:
            continue
        if acao == "bloquear":
            if c.duplex != "Sem TX" and not em_faixa_radioamador(c.tx):
                numeros.append(c.numero)
        elif c.duplex == "Sem TX":
            tx = tx_original(prog, c)
            if tx is None:
                tx = c.rx  # mesmo fallback simplex do desbloqueio individual
            if c.modo != "AM" and c.p.tx_valido(tx) and em_faixa_radioamador(tx):
                numeros.append(c.numero)
    return numeros


def dentro_das_faixas(hz, faixas):
    f = hz / 1e6
    return any(a - 1e-9 <= f <= b + 1e-9 for a, b, *_ in faixas)


def chave_excecao(c: Canal):
    return f"{c.numero}:{c.rx}"


def _tx_de(rx, duplex, offset):
    if duplex == "+":
        return rx + offset
    if duplex == "-":
        return rx - offset
    if duplex == "TX separado":
        return offset
    if duplex == "Sem TX":
        return None
    return rx


def tx_original(prog, c: Canal):
    """TX que o canal tinha antes de ser bloqueado pelo programa (ou None)."""
    o = prog.tx_bloqueados.get(c.numero)
    if c.duplex == "Sem TX" and o and o.get("rx") == c.rx:
        return _tx_de(c.rx, o["duplex"], o["offset"])
    return None


def situacao_tx(prog, c: Canal, faixas, excecoes):
    """None quando o canal está dentro das faixas; senão 'bloqueado', 'excecao' ou 'pendente'."""
    if c.vazio:
        return None
    if c.duplex == "Sem TX":
        ref = tx_original(prog, c) or c.rx
        return None if dentro_das_faixas(ref, faixas) else "bloqueado"
    if dentro_das_faixas(c.tx, faixas):
        return None
    return "excecao" if chave_excecao(c) in excecoes else "pendente"


def bloqueia_tx(prog, numero):
    c = prog.canal(numero)
    if c.vazio or c.duplex == "Sem TX":
        return False
    prog.tx_bloqueados[numero] = {"rx": c.rx, "duplex": c.duplex, "offset": c.offset}
    novo = prog.decodifica(numero, c.bruto)
    novo.duplex, novo.offset = "Sem TX", 0
    prog.define_canal(novo)
    return True


def desbloqueia_tx(prog, numero):
    c = prog.canal(numero)
    if c.vazio or c.duplex != "Sem TX":
        return
    o = prog.tx_bloqueados.get(numero)
    novo = prog.decodifica(numero, c.bruto)
    if o and o.get("rx") == c.rx:
        novo.duplex, novo.offset = o["duplex"], o["offset"]
    else:
        novo.duplex, novo.offset = "Simplex", 0
    tx = novo.tx
    if novo.modo == "AM" or tx is None or not novo.p.tx_valido(tx):
        raise ErroProgramacao(f"Canal {c.rotulo} ({mhz(c.rx)} MHz): o rádio não transmite nessa frequência; "
                              "o canal continua só para recepção.")
    prog.define_canal(novo)
    prog.tx_bloqueados.pop(numero, None)


def compara_imagens(anterior, atual, chave="UV17ProGPS"):
    """Resumo de mudanças; não regrava nem normaliza os dados recebidos."""
    a, b = Programacao(anterior, chave), Programacao(atual, chave)
    resumo = {"incluidos": 0, "alterados": 0, "apagados": 0, "zonas": 0, "ajustes": False, "outros_bytes": False}
    for x, y in zip(a.canais, b.canais):
        if x.bruto == y.bruto:
            continue
        resumo["incluidos" if x.vazio and not y.vazio else "apagados" if not x.vazio and y.vazio else "alterados"] += 1
    if a.perfil.chave == "UV5R":
        resumo["ajustes"] = any(anterior[i:i + 16] != atual[i:i + 16] for i in
                                (uv5r.POS_AJUSTES, uv5r.POS_AJUSTES + 16, uv5r.POS_AJUSTES + 32,
                                 uv5r.POS_MSG_ABERTURA))
        return resumo
    resumo["ajustes"] = anterior[POS_AJUSTES:POS_AJUSTES + 64] != atual[POS_AJUSTES:POS_AJUSTES + 64]
    for i in range(TOTAL_ZONAS):
        pos = POS_ZONAS + i * 16
        resumo["zonas"] += anterior[pos:pos + 16] != atual[pos:pos + 16]
    conhecidos = set(range(TOTAL_CANAIS * 32)) | set(range(POS_AJUSTES, POS_AJUSTES+64)) | set(range(POS_ZONAS, POS_ZONAS+TOTAL_ZONAS*16)) | set(range(POS_RADIO_ID, POS_DTMF + TOTAL_DTMF * 16))
    resumo["outros_bytes"] = any(x != y for i, (x, y) in enumerate(zip(anterior, atual)) if i not in conhecidos)
    return resumo


# -------------------------------------------------------------------- perfis

SCODES_UV5R = [str(i) for i in range(1, 16)]


def _uv5r_decodifica(numero, b, perfil):
    m, nm = b[:16], b[16:32]
    c = Canal(numero=numero, bruto=bytes(b), perfil=perfil)
    if m[0] == 0xFF:
        return c
    c.vazio = False
    c.rx = _bcd_le(m[0:4]) * 10
    if m[4:8] in (b"\xff\xff\xff\xff", b"\x00\x00\x00\x00"):
        c.duplex, c.offset = "Sem TX", 0
    else:
        tx = _bcd_le(m[4:8]) * 10
        dif = tx - c.rx
        if dif == 0:
            c.duplex = "Simplex"
        elif abs(dif) > 70_000_000:
            c.duplex, c.offset = "TX separado", tx
        elif dif > 0:
            c.duplex, c.offset = "+", dif
        else:
            c.duplex, c.offset = "-", -dif
    c.tom_rx = decodifica_tom(m[8] | (m[9] << 8))
    c.tom_tx = decodifica_tom(m[10] | (m[11] << 8))
    sc = m[12] & 0x0F
    c.scode = SCODES_UV5R[sc] if sc < len(SCODES_UV5R) else SCODES_UV5R[0]
    c.potencia = POTENCIAS[m[14] & 0x03] if (m[14] & 0x03) < len(POTENCIAS) else POTENCIAS[0]
    c.largura = LARGURAS[0] if m[15] & 0x40 else LARGURAS[1]
    c.bcl = bool(m[15] & 0x08)
    c.varredura = bool(m[15] & 0x04)
    c.pttid = PTTID[m[15] & 0x03]
    c.nome = "".join(" " if x == 0xFF else chr(x) for x in nm[:uv5r.TAM_NOME]).rstrip()
    return c


def _uv5r_codifica(c):
    """Igual ao CHIRP: o canal editado é reescrito do zero (bytes de 16 zerados) e o nome
    ocupa 7 letras completadas com 0xFF; o restante do registro do nome é preservado."""
    if c.vazio:
        return b"\xff" * 32
    c.valida()
    m = bytearray(16)
    m[0:4] = uv5r._para_bcd(c.rx // 10)
    tx = c.tx
    m[4:8] = b"\xff\xff\xff\xff" if tx is None else uv5r._para_bcd(tx // 10)
    v = codifica_tom(c.tom_rx)
    m[8], m[9] = v & 0xFF, v >> 8
    v = codifica_tom(c.tom_tx)
    m[10], m[11] = v & 0xFF, v >> 8
    m[12] = SCODES_UV5R.index(c.scode) & 0x0F
    m[14] = POTENCIAS.index(c.potencia) & 0x03
    m[15] = (0x40 if c.largura == LARGURAS[0] else 0) | (0x08 if c.bcl else 0) | \
            (0x04 if c.varredura else 0) | (PTTID.index(c.pttid) & 0x03)
    nm = bytearray(c.bruto[16:32]) if len(c.bruto) >= 32 else bytearray(b"\xff" * 16)
    nome = c.nome.upper().encode("ascii")[:uv5r.TAM_NOME]
    nm[0:uv5r.TAM_NOME] = nome + b"\xff" * (uv5r.TAM_NOME - len(nome))
    return bytes(m) + bytes(nm)


class Perfil:
    def __init__(self, **kw):
        self.__dict__.update(kw)

    def rx_valido(self, hz):
        f = hz / 1e6
        return ((self.am and FAIXA_AM[0] <= f <= FAIXA_AM[1]) or any(a <= f <= b for a, b in self.faixas)
                or any(a <= f <= b for a, b in getattr(self, "so_rx", ())))

    def tx_valido(self, hz):
        f = hz / 1e6
        return any(a <= f <= b for a, b in self.faixas)

    def rotulo(self, numero):
        return f"{numero - 1:03d}" if self.base_zero else str(numero)

    @property
    def tem_zonas(self):
        return self.total_zonas > 1


PERFIL_UV17 = Perfil(
    chave="UV17", nome="UV-17 Pro", total_canais=TOTAL_CANAIS, canais_por_zona=CANAIS_POR_ZONA,
    total_zonas=TOTAL_ZONAS, tamanhos=(0x8380,), pos_ajustes=POS_AJUSTES, nome_max=12, caracteres=None,
    scodes=SCODES, faixas=FAIXAS_TX, am=True, base_zero=False,
    bruto=lambda img, i: bytes(img[i * 32:(i + 1) * 32]),
    grava_bruto=lambda img, i, b: img.__setitem__(slice(i * 32, (i + 1) * 32), b),
    decodifica=None, codifica=None)
PERFIL_UV17.decodifica = lambda n, b: decodifica_canal(n, b)
PERFIL_UV17.codifica = lambda c: codifica_canal(c)

# UV-21 Pro V2 (classe UV21ProV2 do CHIRP): mesmo mapa do UV-17 Pro, outras faixas.
# Transmite em 136-174, 220-260 e 400-480 MHz; 350-390 e 480-520 MHz são só recepção.
PERFIL_UV21 = Perfil(**{**PERFIL_UV17.__dict__, "chave": "UV21", "nome": "UV-21 Pro V2",
                        "total_zonas": 1, "canais_por_zona": TOTAL_CANAIS,   # o manual não tem zonas
                        "faixas": [(136.0, 174.0), (220.0, 260.0), (400.0, 480.0)],
                        "so_rx": [(350.0, 390.0), (480.0, 520.0)]})


def _uv21_decodifica(perfil):
    def decodifica(n, b):
        c = decodifica_canal(n, b)
        c.perfil = perfil
        return c
    return decodifica


PERFIL_UV21.decodifica = _uv21_decodifica(PERFIL_UV21)


def _perfil_uv5r(faixas):
    p = Perfil(
        chave="UV5R", nome="UV-5R", total_canais=uv5r.TOTAL_CANAIS, canais_por_zona=uv5r.TOTAL_CANAIS,
        total_zonas=1, tamanhos=(uv5r.TAM_IMAGEM,), pos_ajustes=uv5r.POS_AJUSTES, nome_max=uv5r.TAM_NOME,
        caracteres=uv5r.CARACTERES, scodes=SCODES_UV5R, faixas=faixas, am=False, base_zero=True,
        bruto=uv5r.canal_bruto, grava_bruto=uv5r.grava_bruto, codifica=_uv5r_codifica)
    p.decodifica = lambda n, b: _uv5r_decodifica(n, b, p)
    return p


PERFIL_UV5R = _perfil_uv5r(uv5r.FAIXAS_NORMAIS)
PERFIL_UV5R_220 = _perfil_uv5r(uv5r.FAIXAS_220)


# UV-21 Pro GPS: mesmas faixas e mapa do UV-21 Pro V2, só o nome muda
# O GPS mantém as zonas do UV-17 Pro GPS, de onde vem o mapa (não confirmado pelo manual)
PERFIL_UV21_GPS = Perfil(**{**PERFIL_UV21.__dict__, "chave": "UV21GPS", "nome": "UV-21 Pro GPS",
                            "total_zonas": TOTAL_ZONAS, "canais_por_zona": CANAIS_POR_ZONA})
PERFIL_UV21_GPS.decodifica = _uv21_decodifica(PERFIL_UV21_GPS)


def perfil_de(chave, imagem=None):
    if chave == "UV5R":
        if imagem is not None and bytes(imagem[3:4]) == uv5r.VHF_220:
            return PERFIL_UV5R_220
        return PERFIL_UV5R
    if chave == "UV21Pro":
        return PERFIL_UV21
    if chave == "UV21ProGPS":
        return PERFIL_UV21_GPS
    return PERFIL_UV17

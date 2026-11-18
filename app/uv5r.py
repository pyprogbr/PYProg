# -*- coding: utf-8 -*-
"""
Baofeng UV-5R: comunicação pelo cabo e mapa de memória.

Porta fiel do driver uv5r do CHIRP (classe BaofengUV5R), que programa o UV-5R
há mais de dez anos. A sequência de bytes trocada com o rádio é a mesma do CHIRP;
os testes comparam as duas em um rádio simulado.

Imagem (igual à do CHIRP, 0x1948 bytes):
  0x0000  identificação de 8 bytes recebida do rádio
  0x0008  memória principal do rádio (0x0000 a 0x1800)
  0x1808  memória auxiliar do rádio (0x1EC0 a 0x2000): mensagem de abertura,
          versão do firmware, limites de faixa e calibração
Canais: 128 de 16 bytes a partir de 0x0008; nomes (7 letras) em 0x1008.
Ajustes: 0x0E28. Mensagem de abertura: 0x1828 (2 linhas de 7 letras).
"""
from __future__ import annotations

import struct
import time

TAM_IMAGEM = 0x1948
TAM_ANTIGO = 0x1808          # imagem sem a área auxiliar (CHIRP muito antigo)
MODELO_ARQ = b"UV-5R   "     # 8 bytes que o CHIRP acrescenta ao salvar
RCLASS = "BaofengUV5RGeneric"
MODELO_CHIRP = "UV-5R"
BAUD = 9600

TOTAL_CANAIS = 128
POS_CANAIS = 0x0008
POS_NOMES = 0x1008
POS_AJUSTES = 0x0E28
POS_MSG_ABERTURA = 0x1828
POS_VERSAO = (0x1838, 0x1846)
TAM_NOME = 7

MAGIC_291 = b"\x50\xBB\xFF\x20\x12\x07\x25"
MAGIC_ORIG = b"\x50\xBB\xFF\x01\x25\x98\x4D"
MAGICS = [MAGIC_291, MAGIC_ORIG]
VHF_220 = b"\x02"

# Letras aceitas pelo visor (as mesmas do CHIRP)
CARACTERES = "ABCDEFGHIJKLMNOPQRSTUVWXYZ 1234567890" + "!@#$%^&*()+-=[]:\";'<>?,./"

FAIXAS_NORMAIS = [(130.0, 176.0), (400.0, 520.0)]
FAIXAS_220 = [(130.0, 176.0), (220.0, 260.0)]


class ErroUV5R(Exception):
    pass


# ------------------------------------------------------------------ cabo

class Porta:
    """Porta serial com a mesma interface usada pelo CHIRP (write/read)."""

    def __init__(self, porta):
        try:
            import serial  # type: ignore
        except ImportError as e:  # pragma: no cover
            raise ErroUV5R("Biblioteca 'pyserial' não instalada (pip install pyserial).") from e
        try:
            self.s = serial.Serial(porta, BAUD, bytesize=8, parity="N", stopbits=1, timeout=1, write_timeout=3)
        except Exception as e:
            raise ErroUV5R(f"Não foi possível abrir a porta {porta}: {e}") from e

    def write(self, d):
        self.s.write(d)

    def read(self, n):
        return self.s.read(n)

    def close(self):
        try:
            self.s.close()
        except Exception:
            pass


def _sem_resposta():
    return ErroUV5R(
        "O UV-5R não respondeu.\n\n"
        "1. Confira se o conector do cabo está bem encaixado no rádio (no UV-5R ele costuma "
        "precisar de pressão até o fim).\n"
        "2. Ligue o rádio, aumente o volume e deixe-o em um canal sem sinal.\n"
        "3. Confira a porta COM escolhida.\n"
        "Se o rádio acabou de ser lido ou gravado, desligue e ligue antes de tentar de novo.")


def _ident(p, magia, segundo_ack=True):
    for b in magia:
        p.write(bytes([b]))
        time.sleep(0.01)
    ack = p.read(1)
    if ack != b"\x06":
        raise _sem_resposta()
    p.write(b"\x02")
    resp = b""
    for _ in range(1, 13):
        b = p.read(1)
        resp += b
        if b == b"\xDD":
            break
    if len(resp) == 12:
        ident = bytes([resp[0], resp[3], resp[5]]) + resp[7:]
    elif len(resp) == 8:
        ident = resp
    else:
        raise ErroUV5R(f"Resposta inesperada do rádio na identificação ({resp.hex()}).")
    if segundo_ack:
        p.write(b"\x06")
        if p.read(1) != b"\x06":
            raise ErroUV5R("O rádio recusou o modo de programação.")
    return ident


def identifica(p, espera=2.0):
    erro = None
    for magia in MAGICS:
        try:
            return _ident(p, magia)
        except ErroUV5R as e:
            erro = e
            time.sleep(espera)
    raise erro or _sem_resposta()


def _le_bloco(p, inicio, tam, primeiro=False):
    p.write(struct.pack(">BHB", ord("S"), inicio, tam))
    if not primeiro:
        if p.read(1) != b"\x06":
            raise ErroUV5R(f"O rádio recusou o envio do bloco 0x{inicio:04X}.")
    cab = p.read(4)
    if len(cab) != 4:
        raise ErroUV5R(f"O rádio não enviou o bloco 0x{inicio:04X}.")
    cmd, end, n = struct.unpack(">BHB", cab)
    if cmd != ord("X") or end != inicio or n != tam:
        raise ErroUV5R(f"Resposta desconhecida do rádio no bloco 0x{inicio:04X}.")
    dados = p.read(tam)
    if len(dados) != tam:
        raise ErroUV5R(f"Bloco 0x{inicio:04X} incompleto.")
    p.write(b"\x06")
    time.sleep(0.05)
    return dados


def _versao_radio(p):
    """(versão, perde_byte): versão do firmware e o defeito de 'byte perdido' de rádios novos."""
    _le_bloco(p, 0x1E80, 0x40, True)     # o CHIRP lê e descarta este bloco antes (rádios novos)
    b1 = _le_bloco(p, 0x1EC0, 0x40)
    b2 = _le_bloco(p, 0x1FC0, 0x40)
    return b1[48:62], b2[15:16] == b"\xFF"


def _aux_do_radio(p):
    _le_bloco(p, 0x1E80, 0x40, True)
    b1 = _le_bloco(p, 0x1EC0, 0x40)
    b2 = _le_bloco(p, 0x1F00, 0x40)
    b3 = _le_bloco(p, 0x1F40, 0x40)
    b4 = _le_bloco(p, 0x1F80, 0x40)
    b5 = _le_bloco(p, 0x1FC0, 0x40)
    return b1[48:62], b2 + b3[0:32], b3[48:64], b4[16:64], b5[15:16] == b"\xFF"


def _download(p, ident, progresso):
    """Leitura após a identificação (mesma ordem do CHIRP)."""
    versao, perde_byte = _versao_radio(p)
    dados = bytearray(ident)
    total = 0x1800 + 0x140
    for i in range(0, 0x1800, 0x40):
        dados += _le_bloco(p, i, 0x40)
        progresso(len(dados) - 8, total)
    if perde_byte:
        for i in range(0x1EC0, 0x1FC0, 0x40):
            dados += _le_bloco(p, i, 0x40)
        for i in range(0x1FC0, 0x2000, 0x10):
            dados += _le_bloco(p, i, 0x10)
    else:
        for i in range(0x1EC0, 0x2000, 0x40):
            dados += _le_bloco(p, i, 0x40)
    progresso(total, total)
    return bytes(dados), versao, perde_byte


def _envia_bloco(p, end, dados):
    p.write(struct.pack(">BHB", ord("X"), end, len(dados)) + dados)
    time.sleep(0.05)
    if p.read(1) != b"\x06":
        raise ErroUV5R(f"O rádio recusou o bloco 0x{end:04X}.")


def versao_firmware(img) -> bytes:
    return bytes(img[POS_VERSAO[0]:POS_VERSAO[1]])


def _e_original(versao: bytes) -> bool:
    """Rádios 'originais' (firmware BFB anterior a 291) têm outra área auxiliar."""
    if b"BFB" in versao:
        i = versao.index(b"BFB") + 3
        try:
            return int(versao[i:i + 3]) < 291
        except ValueError:
            raise ErroUV5R(f"Versão de firmware não reconhecida: {versao!r}")
    return False


def _upload(p, ident, img, aux_radio, progresso):
    """Gravação após a identificação, com a mesma escolha de áreas do CHIRP."""
    banda_radio, banda_img = ident[3:4], bytes(img[3:4])
    if (banda_img == VHF_220 or banda_radio == VHF_220) and banda_img != banda_radio:
        raise ErroUV5R("Este arquivo é de um UV-5R de outra versão de faixa (220 MHz). Leia o rádio conectado "
                       "e faça as alterações sobre essa leitura.")
    versao_r, r1, r2, r3, perde_byte = aux_radio
    img_orig = _e_original(versao_firmware(img)) if len(img) >= POS_VERSAO[1] else False
    if img_orig != _e_original(versao_r):
        raise ErroUV5R("Este arquivo é de um UV-5R com firmware de outra geração. Leia o rádio conectado "
                       "e faça as alterações sobre essa leitura.")
    aux_ok = (bytes(img[0x1848:0x18A8]) == r1 and bytes(img[0x18B8:0x18C8]) == r2
              and bytes(img[0x18D8:0x1908]) == r3)
    if perde_byte and not aux_ok:
        raise ErroUV5R("Este rádio só aceita gravação de um arquivo lido dele mesmo.\n\n"
                       "1. Leia o rádio.\n2. Faça as alterações.\n3. Grave de volta no mesmo rádio.")
    principal = [(0x0008, 0x0CF8), (0x0D08, 0x0DF8), (0x0E08, 0x1808)]
    if img_orig:
        aux = [(0x1EE0, 0x1EF0), (0x1FC0, 0x1FE0)]
    elif perde_byte or aux_ok:
        aux = [(0x1EC0, 0x2000)]
    else:
        aux = [(0x1EE0, 0x1EF0), (0x1F60, 0x1F70), (0x1F80, 0x1F90), (0x1FC0, 0x1FD0)]
    if len(img) == TAM_ANTIGO:
        aux = []
    total = sum(b - a for a, b in principal) + sum(b - a for a, b in aux)
    feito = 0
    for a, b in principal:
        for i in range(a, b, 0x10):
            _envia_bloco(p, i - 0x08, bytes(img[i:i + 0x10]))
            feito += 0x10
            progresso(feito, total)
    for a, b in aux:
        for i in range(a, b, 0x10):
            pos = 0x1808 + (i - 0x1EC0)
            _envia_bloco(p, i, bytes(img[pos:pos + 0x10]))
            feito += 0x10
            progresso(feito, total)


def _prog(progresso, inicio, fim, rotulo):
    def f(feito, total):
        pct = inicio + (fim - inicio) * feito // max(1, total)
        progresso(pct, f"{rotulo}... {pct}%")
    return f


def le(porta, progresso=None, abre=Porta):
    """Lê o rádio. Retorna (imagem de 0x1948 bytes, identificação)."""
    progresso = progresso or (lambda p, t: None)
    p = abre(porta)
    try:
        progresso(0, "Conectando ao UV-5R...")
        ident = identifica(p)
        dados, _, _ = _download(p, ident, _prog(progresso, 0, 100, "Lendo o UV-5R"))
        return dados, ident
    finally:
        p.close()


def grava(porta, img, progresso=None, abre=Porta):
    """Grava como o CHIRP: identificação, leitura da área auxiliar e gravação."""
    progresso = progresso or (lambda p, t: None)
    _confere_tamanho(img)
    p = abre(porta)
    try:
        progresso(0, "Conectando ao UV-5R...")
        ident = identifica(p)
        aux = _aux_do_radio(p)
        _upload(p, ident, img, aux, _prog(progresso, 0, 100, "Gravando no UV-5R"))
    finally:
        p.close()


def le_e_grava(porta, img, progresso=None, apos_leitura=None, abre=Porta):
    """Numa ÚNICA conexão: lê o rádio inteiro (cópia de segurança) e grava a programação.
    A comparação da área auxiliar usa a leitura feita nesta mesma conexão.
    apos_leitura(atual, ident) é chamada antes do primeiro bloco gravado."""
    progresso = progresso or (lambda p, t: None)
    _confere_tamanho(img)
    p = abre(porta)
    try:
        progresso(0, "Conectando ao UV-5R...")
        ident = identifica(p)
        atual, versao, perde_byte = _download(p, ident, _prog(progresso, 0, 50, "Lendo cópia de segurança"))
        if apos_leitura:
            apos_leitura(atual, ident)
        aux = (versao, atual[0x1848:0x18A8], atual[0x18B8:0x18C8], atual[0x18D8:0x1908], perde_byte)
        _upload(p, ident, img, aux, _prog(progresso, 50, 100, "Gravando no UV-5R"))
        return atual, ident
    finally:
        p.close()


def _confere_tamanho(img):
    if len(img) not in (TAM_IMAGEM, TAM_ANTIGO):
        raise ErroUV5R("Imagem com tamanho inesperado para o UV-5R.")


# Prefixos de firmware que o CHIRP reconhece como UV-5R (BASETYPE_UV5R)
FIRMWARES_UV5R = [b"BFS", b"BFB", b"N5R-2", b"N5R2", b"N5RV", b"BTS", b"D5R2", b"B5R2"]

# Rádios que o CHIRP programa com o mesmo driver e o mesmo mapa do UV-5R
COMPATIVEIS = ["Baofeng UV-5R (inclusive as versões vendidas como UV-5RA, UV-5RE e UV-5R Plus)",
               "Baofeng UV-5X", "Retevis RT5R, RT5RV e RT5", "Rugged RH5R", "Radioddity UV-5R EX",
               "Ansoko A-5R"]
NAO_COMPATIVEIS = ["BF-F8HP", "UV-82", "UV-82HP", "UV-5X3", "UV-5RX3", "UV-6", "UV-5G", "GT-5R", "F-11"]


def firmware_conhecido(img) -> bool:
    v = versao_firmware(img) if len(img) >= POS_VERSAO[1] else b""
    return any(b in v for b in FIRMWARES_UV5R)


def descreve_ident(img_ou_ident) -> str:
    v = versao_firmware(img_ou_ident) if len(img_ou_ident) >= POS_VERSAO[1] else b""
    txt = "".join(chr(b) if 32 <= b < 127 else " " for b in v).strip()
    return f"firmware {txt}" if txt else ""


# ----------------------------------------------------------------- canais

def _bcd_le(d):
    v = 0
    for b in reversed(d):
        v = v * 100 + (b >> 4) * 10 + (b & 15)
    return v


def _para_bcd(v, n=4):
    out = bytearray()
    for _ in range(n):
        dois = v % 100
        out.append(((dois // 10) << 4) | (dois % 10))
        v //= 100
    return bytes(out)


def canal_bruto(img, i):
    """32 bytes: 16 do canal + 16 do nome (índice i de 0 a 127)."""
    return bytes(img[POS_CANAIS + i * 16:POS_CANAIS + (i + 1) * 16]) + bytes(img[POS_NOMES + i * 16:POS_NOMES + (i + 1) * 16])


def grava_bruto(img, i, b):
    img[POS_CANAIS + i * 16:POS_CANAIS + (i + 1) * 16] = b[:16]
    img[POS_NOMES + i * 16:POS_NOMES + (i + 1) * 16] = b[16:32]


def faixas(img):
    return FAIXAS_220 if bytes(img[3:4]) == VHF_220 else FAIXAS_NORMAIS


# ---------------------------------------------------------------- ajustes
# (chave, posição a partir de 0x0E28, rótulo, opções | "bool" | ("texto", n), grupo[, máscara, deslocamento])

def _seg(ini, fim, passo, suf=" s"):
    return [f"{s}{suf}" for s in range(ini, fim, passo)]


AJUSTES = [
    ("u5_squelch", 0, "Squelch (silenciador)", ["0 (aberto)"] + [str(i) for i in range(1, 10)], "Geral"),
    ("u5_timeout", 9, "Tempo limite de transmissão (TOT)", _seg(15, 615, 15) + ["Desligado (se o rádio aceitar)"], "Geral"),
    ("u5_save", 3, "Economia de bateria", ["Desligada", "1:1", "1:2", "1:3", "1:4"], "Geral"),
    ("u5_tdr", 7, "Dupla escuta", "bool", "Geral"),
    ("u5_tdrab", 34, "Prioridade de TX na dupla escuta", ["Desligada", "A", "B"], "Geral"),
    ("u5_workmode", 44, "Modo ao ligar", ["Frequência (VFO)", "Canal (MR)"], "Geral"),
    ("u5_mdfa", 21, "Exibição do canal A", ["Número do canal", "Nome", "Frequência"], "Visor"),
    ("u5_mdfb", 22, "Exibição do canal B", ["Número do canal", "Nome", "Frequência"], "Visor"),
    ("u5_abr", 6, "Luz do visor", ["Desligada"] + _seg(1, 25, 1), "Visor"),
    ("u5_wtled", 29, "Cor da luz em espera", ["Desligada", "Azul", "Laranja", "Roxa"], "Visor"),
    ("u5_rxled", 30, "Cor da luz ao receber", ["Desligada", "Azul", "Laranja", "Roxa"], "Visor"),
    ("u5_txled", 31, "Cor da luz ao transmitir", ["Desligada", "Azul", "Laranja", "Roxa"], "Visor"),
    ("u5_ponmsg", 38, "Tela ao ligar", ["Teste do visor (completa)", "Mensagem"], "Visor"),
    ("u5_msg1", POS_MSG_ABERTURA - POS_AJUSTES, "Mensagem de abertura, linha 1", ("texto", 7), "Visor"),
    ("u5_msg2", POS_MSG_ABERTURA + 7 - POS_AJUSTES, "Mensagem de abertura, linha 2", ("texto", 7), "Visor"),
    ("u5_voice", 14, "Aviso de voz", ["Desligado", "Inglês", "Chinês"], "Som"),
    ("u5_beep", 8, "Bipe das teclas", "bool", "Som"),
    ("u5_roger", 39, "Bipe de fim de transmissão (Roger)", "bool", "Som"),
    ("u5_ste", 35, "Eliminação de cauda", "bool", "Som"),
    ("u5_vox", 4, "VOX", ["Desligado"] + [str(i) for i in range(1, 11)], "Som"),
    ("u5_screv", 18, "Retomada da varredura", ["Por tempo (TO)", "Por portadora (CO)", "Busca (SE)"],
     "Varredura e repetidora", 0x03, 0),
    ("u5_rpste", 36, "Eliminação de cauda da repetidora", ["Desligada"] + [str(i) for i in range(1, 11)],
     "Varredura e repetidora"),
    ("u5_rptrl", 37, "Atraso da eliminação de cauda", ["Desligado"] + _seg(100, 1100, 100, " ms"),
     "Varredura e repetidora"),
    ("u5_bcl", 23, "Bloqueio de canal ocupado (geral)", "bool", "Teclas e alarme"),
    ("u5_autolk", 24, "Bloqueio automático do teclado", "bool", "Teclas e alarme"),
    ("u5_keylock", 45, "Teclado bloqueado", "bool", "Teclas e alarme"),
    ("u5_almod", 32, "Modo do alarme", ["Local", "Enviar tom", "Enviar código"], "Teclas e alarme"),
]


def le_texto(img, pos, n):
    b = bytes(img[pos:pos + n])
    return "".join(chr(c) if chr(c) in CARACTERES else " " for c in b).rstrip()


def grava_texto(img, pos, n, txt):
    txt = (txt or "").upper()
    ruins = sorted({ch for ch in txt if ch not in CARACTERES})
    if ruins:
        raise ErroUV5R("A mensagem de abertura não aceita: " + " ".join(ruins))
    b = txt[:n].ljust(n).encode("ascii")
    img[pos:pos + n] = b

# -*- coding: utf-8 -*-
"""
Leitura e restauração das CONFIGURAÇÕES do rádio (canais, ajustes, nomes).

Protocolo de clonagem igual ao do CHIRP (driver baofeng_uv17Pro.py, de
Sander van der Wel). O arquivo gerado é uma imagem .img compatível com o
CHIRP, que pode ser aberta e enviada ao rádio também por ele.

Observação: a memória de VOZ não pode ser lida; só as configurações.
"""
from __future__ import annotations

import base64
import json
import re
import struct
import time

from arquivos import grava_atomico
import uv5r

INDICATIVO = ""   # o valor em uso vem de config.json (campo no topo da janela) ou do instalador
TAM_INDICATIVO = 16


def define_indicativo(texto: str) -> str:
    """Normaliza (maiúsculas, sem espaços nas pontas, até 16 caracteres) e passa a usar."""
    global INDICATIVO
    INDICATIVO = (texto or "").strip().upper()[:TAM_INDICATIVO]
    return INDICATIVO


def sufixo_arquivo() -> str:
    """'_PU2KEU' para nomes de arquivo; vazio se não houver indicativo."""
    limpo = re.sub(r'[\\/:*?"<>|\s]+', "-", INDICATIVO).strip("-")
    return f"_{limpo}" if limpo else ""

MAGIC_IMG = b"\x00\xffchirp\xeeimg\x00\x01"
BLOCO = 0x40
REGIOES = [(0x0000, 0x8040), (0x9000, 0x0040), (0xA000, 0x02C0), (0xD000, 0x0040)]
TAM_TOTAL = sum(t for _, t in REGIOES)  # 0x8380
_SEND = (b"\x53\x45\x4E\x44\x21\x05\x0D\x01\x01\x01\x04\x11\x08\x05\x0D\x0D"
         b"\x01\x11\x0F\x09\x12\x09\x10\x04\x00")

CLONE = {
    "UV17ProGPS": {"magic": b"PROGRAMCOLORPROU", "magics": [(b"\x46", 16), (b"\x4d", 7), (_SEND, 1)],
                   "rclass": "UV17ProGPS", "modelo_chirp": "UV-17ProGPS"},
    "UV17Pro": {"magic": b"PROGRAMBFNORMALU", "magics": [(b"\x46", 16), (b"\x4d", 15), (_SEND, 1)],
                "rclass": "UV17Pro", "modelo_chirp": "UV-17Pro"},
    # UV-21 Pro: mesmo protocolo e mapa do UV-17 Pro; muda só as faixas (classe UV21ProV2 do CHIRP)
    "UV21Pro": {"magic": b"PROGRAMBFNORMALU", "magics": [(b"\x46", 16), (b"\x4d", 15), (_SEND, 1)],
                "rclass": "UV21ProV2", "modelo_chirp": "UV-21ProV2"},
    # UV-17R Plus: protocolo e mapa do UV-17 Pro (classe UV17RPlus do CHIRP)
    "UV17RPlus": {"magic": b"PROGRAMBFNORMALU", "magics": [(b"\x46", 16), (b"\x4d", 15), (_SEND, 1)],
                  "rclass": "UV17RPlus", "modelo_chirp": "UV-17R-Plus"},
    # UV-21 Pro GPS: protocolo e mapa do UV-17 Pro GPS, faixas do UV-21 Pro (classe UV21ProGPS)
    "UV21ProGPS": {"magic": b"PROGRAMCOLORPROU", "magics": [(b"\x46", 16), (b"\x4d", 7), (_SEND, 1)],
                   "rclass": "UV21ProGPS", "modelo_chirp": "UV-21ProGPS"},
    # UV-5R: protocolo próprio, em uv5r.py
    "UV5R": {"rclass": uv5r.RCLASS, "modelo_chirp": uv5r.MODELO_CHIRP},
}


def tamanho_imagem(chave):
    return uv5r.TAM_IMAGEM if chave == "UV5R" else TAM_TOTAL


def _uv5r(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except uv5r.ErroUV5R as e:
        raise ErroConfig(str(e)) from e

_SIMBOLO = b"CO 7"


class ErroConfig(Exception):
    pass


def cripto(dados: bytes) -> bytes:
    """Cifra/decifra (a operação é simétrica), igual ao CHIRP."""
    out = bytearray(dados)
    for i, b in enumerate(dados):
        k = _SIMBOLO[i % 4]
        if k != 32 and b not in (0, 255, k, k ^ 255):
            out[i] = b ^ k
    return bytes(out)


class _Porta:
    def __init__(self, porta):
        try:
            import serial  # type: ignore
        except ImportError as e:  # pragma: no cover
            raise ErroConfig("Biblioteca 'pyserial' não instalada (pip install pyserial).") from e
        try:
            self.s = serial.Serial(porta, 115200, bytesize=8, parity="N", stopbits=1, timeout=1.5, write_timeout=3)
        except Exception as e:
            raise ErroConfig(f"Não foi possível abrir a porta {porta}: {e}") from e

    def limpa(self):
        self.s.timeout = 0.005
        self.s.read(256)
        self.s.timeout = 1.5

    def envia(self, d):
        if self.s.write(d) != len(d):
            raise ErroConfig("Escrita incompleta no cabo de programação.")

    def recebe(self, n, oque="dados"):
        limite = time.monotonic() + 2.0
        dados = bytearray()
        while len(dados) < n and time.monotonic() < limite:
            dados.extend(self.s.read(n - len(dados)))
        if len(dados) != n:
            raise ErroConfig(f"Resposta incompleta do rádio ({oque}: {len(dados)} de {n} bytes). Confira cabo e porta COM.")
        return bytes(dados)

    def fecha(self):
        try:
            self.s.close()
        except Exception:
            pass


TENTATIVAS_IDENT = 5      # como o programa oficial da Baofeng (CPS T6UV): até 5 vezes,
ESPERA_IDENT = 1.0        # uma por segundo, antes de desistir


def _identifica(p: _Porta, chave, progresso=None):
    c = CLONE[chave]
    r = b""
    for tentativa in range(1, TENTATIVAS_IDENT + 1):
        if tentativa > 1:
            if progresso:
                progresso(0, f"Conectando ao rádio... tentativa {tentativa} de {TENTATIVAS_IDENT}")
            time.sleep(ESPERA_IDENT)
        p.limpa()
        p.envia(c["magic"])
        try:
            r = p.recebe(1, "identificação")
        except ErroConfig:
            r = b""            # sem resposta: tenta de novo, como o programa oficial
        if r == b"\x06":
            break
    if r != b"\x06":
        if not r:
            raise ErroConfig("O rádio não respondeu à identificação depois de "
                             f"{TENTATIVAS_IDENT} tentativas. Confira o cabo, a porta COM e se o rádio "
                             "está ligado.\n\nSe o rádio acabou de ser lido ou gravado, desligue e ligue "
                             "e tente de novo.")
        raise ErroConfig(
            f"O rádio respondeu de forma inesperada à identificação (recebido: {r.hex()}).\n\n"
            "Isso costuma acontecer quando o rádio continua em modo de programação depois de uma "
            "leitura ou gravação anterior. Desligue e ligue o rádio e tente de novo.\n\n"
            "Se persistir, confira o modelo escolhido no topo da janela.")
    ident = b""
    for magia, n in c["magics"]:
        p.envia(magia)
        r = p.recebe(n, "identificação")
        if not ident:
            ident = r
    return ident


def descreve_ident(ident: bytes) -> str:
    txt = "".join(chr(b) if 32 <= b < 127 else " " for b in ident).strip()
    txt = " ".join(txt.split())
    letras = sum(ch.isalnum() for ch in txt)
    return txt if letras >= 4 and letras >= len(ident) * 0.5 else ""


# Cabeçalhos de resposta diferentes do esperado na última leitura (diagnóstico).
# O CHIRP descarta esses 4 bytes sem conferir; aqui a leitura continua e só registra.
AVISOS_LEITURA = []


def _le_blocos(p, progresso, faixa=(0, 100), rotulo="Lendo configurações"):
    dados = bytearray()
    total = TAM_TOTAL // BLOCO
    for ini, tam in REGIOES:
        for end in range(ini, ini + tam, BLOCO):
            p.envia(b"R" + struct.pack(">H", end) + bytes([BLOCO]))
            r = p.recebe(BLOCO + 4, f"bloco 0x{end:04X}")
            cmd, endereco, tamanho = struct.unpack(">cHB", r[:4])
            if cmd not in (b"R", b"W") or endereco != end or tamanho != BLOCO:
                AVISOS_LEITURA.append(f"0x{end:04X}: {r[:4].hex()}")
            dados += cripto(r[4:])
            pct = faixa[0] + (faixa[1] - faixa[0]) * (len(dados) // BLOCO) // total
            progresso(pct, f"{rotulo}... {pct}%")
    return bytes(dados)


def _grava_blocos(p, dados, progresso, faixa=(0, 100), rotulo="Gravando configurações"):
    pos = 0
    total = TAM_TOTAL // BLOCO
    for ini, tam in REGIOES:
        for end in range(ini, ini + tam, BLOCO):
            bloco = cripto(dados[pos:pos + BLOCO])
            pos += BLOCO
            p.envia(b"W" + struct.pack(">H", end) + bytes([BLOCO]) + bloco)
            if p.recebe(1, "confirmação") != b"\x06":
                raise ErroConfig(f"O rádio recusou o bloco 0x{end:04X}.")
            pct = faixa[0] + (faixa[1] - faixa[0]) * (pos // BLOCO) // total
            progresso(pct, f"{rotulo}... {pct}%")


def le_configuracao(porta: str, chave: str, progresso=None):
    """Retorna (imagem_de_memória, identificação)."""
    progresso = progresso or (lambda p, t: None)
    AVISOS_LEITURA.clear()
    if chave == "UV5R":
        return _uv5r(uv5r.le, porta, progresso)
    p = _Porta(porta)
    try:
        progresso(0, "Conectando ao rádio...")
        ident = _identifica(p, chave, progresso)
        return _le_blocos(p, progresso), ident
    finally:
        p.fecha()


def grava_configuracao(porta: str, chave: str, dados: bytes, progresso=None, rotulo="Restaurando configurações"):
    progresso = progresso or (lambda p, t: None)
    if chave == "UV5R":
        return _uv5r(uv5r.grava, porta, dados, progresso)
    if len(dados) != TAM_TOTAL:
        raise ErroConfig("Imagem com tamanho inesperado para este rádio.")
    p = _Porta(porta)
    try:
        progresso(0, "Conectando ao rádio...")
        _identifica(p, chave, progresso)
        _grava_blocos(p, dados, progresso, rotulo=rotulo)
    finally:
        p.fecha()


def le_e_grava(porta: str, chave: str, dados: bytes, progresso=None, apos_leitura=None):
    """Numa ÚNICA conexão: lê a programação atual (cópia de segurança) e grava a nova.
    Evita uma segunda identificação logo após uma leitura, que o rádio pode recusar
    enquanto continua em modo de programação. apos_leitura(atual, ident) é chamada
    antes do primeiro bloco gravado; se ela falhar, nada é gravado."""
    progresso = progresso or (lambda p, t: None)
    AVISOS_LEITURA.clear()
    if chave == "UV5R":
        return _uv5r(uv5r.le_e_grava, porta, dados, progresso, apos_leitura)
    if len(dados) != TAM_TOTAL:
        raise ErroConfig("Imagem com tamanho inesperado para este rádio.")
    p = _Porta(porta)
    try:
        progresso(0, "Conectando ao rádio...")
        ident = _identifica(p, chave, progresso)
        atual = _le_blocos(p, progresso, (0, 50), "Lendo cópia de segurança")
        if apos_leitura:
            apos_leitura(atual, ident)
        _grava_blocos(p, dados, progresso, (50, 100), "Gravando no rádio")
        return atual, ident
    finally:
        p.fecha()


# Textos (em maiúsculas) que o rádio devolve na identificação de cada modelo. Se o rádio lido não tiver
# nenhum deles, o programa avisa que pode ser outro modelo. Modelos sem texto aqui não recebem esse aviso.
TERMOS_IDENT = {"RT3S": ("MD-UV380", "MD-UV390")}


def confere_modelo(chave, dados, desc):
    """Texto do alerta se o rádio lido parece ser outro modelo; "" quando está tudo certo.
    desc é o texto de identificação (descreve_leitura)."""
    if chave == "UV5R":
        if not uv5r.firmware_conhecido(dados):
            return f"O firmware deste rádio ({desc or 'sem nome'}) não é o de um UV-5R ou compatível."
        return ""
    termos = TERMOS_IDENT.get(chave)
    if termos and not any(t in desc.upper() for t in termos):
        return f"O rádio respondeu como {desc or 'sem identificação'}."
    return ""


def descreve_leitura(chave, dados, ident=b""):
    """Texto curto para o usuário: identificação do UV-17 ou firmware do UV-5R."""
    if chave == "UV5R":
        return uv5r.descreve_ident(dados)
    return descreve_ident(ident)


def salva_img(caminho, chave, dados, ident=b"", extra=None):
    c = CLONE[chave]
    meta = {
        "rclass": c["rclass"], "vendor": "Baofeng", "model": c["modelo_chirp"], "variant": "",
        "indicativo": INDICATIVO, "ident_radio": descreve_leitura(chave, dados, ident),
        "gerado_por": "PYProg",
        "data": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    if extra:
        meta.update(extra)
    if chave not in CLONE or len(dados) != tamanho_imagem(chave):
        raise ErroConfig("Imagem incompatível com o modelo selecionado.")
    if chave == "UV5R":
        dados = bytes(dados) + uv5r.MODELO_ARQ     # como o CHIRP salva o UV-5R (0x1950 bytes)
    grava_atomico(caminho, bytes(dados) + MAGIC_IMG + base64.b64encode(json.dumps(meta).encode()))


def abre_img(caminho):
    """Retorna (chave_do_modelo, dados, metadados)."""
    with open(caminho, "rb") as f:
        bruto = f.read()
    meta = {}
    if MAGIC_IMG in bruto:
        i = bruto.index(MAGIC_IMG)
        try:
            meta = json.loads(base64.b64decode(bruto[i + len(MAGIC_IMG):]).decode())
        except Exception as e:
            raise ErroConfig("Metadados inválidos no arquivo de configuração.") from e
        if not isinstance(meta, dict):
            raise ErroConfig("Metadados da configuração não são um objeto.")
        bruto = bruto[:i]
    modelo = str(meta.get("model", ""))
    if len(bruto) in (uv5r.TAM_IMAGEM, uv5r.TAM_IMAGEM + 8) and (
            modelo == "UV-5R" or bruto[uv5r.TAM_IMAGEM:].startswith(b"UV-5R") or not meta):
        return "UV5R", bruto[:uv5r.TAM_IMAGEM], meta
    if len(bruto) == uv5r.TAM_ANTIGO:
        raise ErroConfig("Este arquivo de UV-5R é de uma versão muito antiga do CHIRP, sem a área de "
                         "mensagem e firmware. Leia o rádio por este programa para criar um arquivo novo.")
    if len(bruto) != TAM_TOTAL:
        raise ErroConfig("Este arquivo não é uma imagem de configuração de um modelo suportado "
                         "(família UV-17 ou UV-5R).")
    chave = None
    for k, c in CLONE.items():
        if meta.get("rclass") == c["rclass"]:
            chave = k
    if chave is None:
        # Arquivos do CHIRP salvos por "apelido" (ex.: UV-16, UV-21Pro): rclass DynamicRadioAlias
        for k, c in CLONE.items():
            if modelo == c["modelo_chirp"]:
                chave = k
    return chave, bruto, meta

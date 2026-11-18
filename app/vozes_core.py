# -*- coding: utf-8 -*-
"""
Núcleo do Editor de Vozes Baofeng (UV-17 Pro GPS e UV-17 Pro/R/L).

Contém:
  - definição dos modelos (tabela de vozes, endereços, handshake);
  - leitura e gravação de pacotes .vpa, compatíveis com o BFVoicePackEditor original;
  - codec OKI/Dialogic ADPCM 4 bits a 8 kHz (o mesmo formato ".vox" que o SoX gera);
  - tratamento de áudio (decodificação, corte de silêncio, normalização);
  - geração de voz em português do Brasil (voz neural Francisca);
  - envio do pacote ao rádio pela porta serial (mesmo protocolo do editor original).
"""
from __future__ import annotations

import io
import json
import os
import struct
import sys
import time
import wave
import copy

from arquivos import grava_atomico, assinatura
from array import array
from dataclasses import dataclass, field

VERSAO = "1.0.0 (beta)"

# ---------------------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------------------

TAM_PACOTE = 1245184          # 0x130000 bytes (19 blocos de 64 KB)
TAM_TABELA = 2048             # área reservada para a tabela de índices
ENDERECO_RADIO = 0xD0000      # endereço de gravação usado pelo editor original
BLOCOS_APAGAR = 19
MARCA_TEXTOS = b"BFVE-PTBR-TEXTOS"


def _faixa(a, b):
    return list(range(a, b + 1))


NUMEROS_EN = [
    "Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
    "Seventeen", "Eighteen", "Nineteen", "Twenty", "Thirty", "Forty", "Fifty",
    "Sixty", "Seventy", "Eighty", "Ninety", "Hundred",
]
NUMEROS_PT = [
    "zero", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove",
    "dez", "onze", "doze", "treze", "catorze", "quinze", "dezesseis",
    "dezessete", "dezoito", "dezenove", "vinte", "trinta", "quarenta", "cinquenta",
    "sessenta", "setenta", "oitenta", "noventa", "cem",
]

# Termos do UV-17 Pro GPS além dos números (ordem do editor original)
GPS_TERMOS = [
    ("TOT", "tempo de transmissão esgotado"),
    ("Channel Mode", "modo canal"),
    ("Frequency Mode", "modo frequência"),
    ("Power Low", "potência baixa"),
    ("Lock", "teclado bloqueado"),
    ("Unlock", "teclado liberado"),
    ("Scan Off", "varredura desligada"),
    ("Scan On", "varredura ligada"),
    ("FM On", "rádio FM"),
    ("Enter", "salvo"),
    ("Escape", "sair"),
    ("End", "fim"),
]
GPS_INDICES = (_faixa(31, 41) + _faixa(62, 70) + _faixa(42, 50) + [61]
               + _faixa(51, 56) + [58, 57, 59, 60, 71])

PRO_TERMOS = [
    ("Welcome", "bem-vindo"),
    ("Lock", "teclado bloqueado"),
    ("Unlock", "teclado liberado"),
    ("Scanning Begin", "varredura iniciada"),
    ("Scanning Stop", "varredura parada"),
    ("CTCSS", "C T C S S"),
    ("DCS", "D C S"),
    ("Power", "potência"),
    ("Save Mode", "modo economia"),
    ("Memory Channel", "gravar canal"),
    ("Delete Channel", "apagar canal"),
    ("Frequency Set", "ajuste de frequência"),
    ("Squelch", "silenciador"),
    ("Transmit Over Time", "tempo limite de transmissão"),
    ("Backlight Selection", "luz de fundo"),
    ("VOX", "vox"),
    ("Frequency Direction", "direção do deslocamento"),
    ("Offset frequency", "deslocamento de frequência"),
    ("Transmitting Memory", "memória de transmissão"),
    ("Receiving Memory", "memória de recepção"),
    ("Emergency Call", "chamada de emergência"),
    ("Low Voltage", "bateria fraca"),
    ("Channel Mode", "modo canal"),
    ("Frequency Mode", "modo frequência"),
    ("Voice Prompt", "aviso de voz"),
    ("Band Selection", "seleção de faixa"),
    ("Dual Standby", "dupla escuta"),
    ("Channel Bandwidth", "largura de banda"),
    ("Optional Signal", "sinal opcional"),
    ("Mute Mode", "modo mudo"),
    ("BCL", "bloqueio de canal ocupado"),
    ("Beep Prompt", "bipe de teclas"),
    ("ANI Code", "código ANI"),
    ("Initialisation", "restaurar padrões"),
    ("Confirm", "confirmar"),
    ("Cancel", "cancelar"),
    ("On", "ligado"),
    ("Off", "desligado"),
    ("Menu", "menu"),
    ("Frequency Scan", "varredura de frequência"),
    ("End", "fim"),
]
PRO_INDICES = _faixa(52, 62) + _faixa(104, 120) + _faixa(63, 103) + [121]


@dataclass
class Modelo:
    chave: str              # cabeçalho gravado no .vpa
    nome: str               # nome exibido
    handshake: str
    inicio: int             # deslocamento base usado na tabela de índices
    total: int              # quantidade total de áudios no rádio
    arquivo_fabrica: str
    # slot -> (rótulo em inglês, texto padrão em português)
    rotulos: dict = field(default_factory=dict)

    @property
    def slots_ingles(self):
        return [s for s in range(self.total) if s in self.rotulos]

    @property
    def slots_tabela2(self):
        return [s for s in range(self.total) if s not in self.rotulos]


# Avisos em chinês do UV-17 Pro GPS (slots 0 a 30). São falados em chinês, com uma voz chinesa.
# Cada entrada: slot -> (rótulo em português, texto em chinês que a voz fala).
AVISOS_CHINES = {
    "UV17ProGPS": {
        0: ("Zero", "零"), 1: ("Um", "一"), 2: ("Dois", "二"), 3: ("Três", "三"), 4: ("Quatro", "四"),
        5: ("Cinco", "五"), 6: ("Seis", "六"), 7: ("Sete", "七"), 8: ("Oito", "八"), 9: ("Nove", "九"),
        10: ("Dez", "十"), 11: ("Vinte", "二十"), 12: ("Trinta", "三十"), 13: ("Quarenta", "四十"),
        14: ("Cinquenta", "五十"), 15: ("Sessenta", "六十"), 16: ("Setenta", "七十"), 17: ("Oitenta", "八十"),
        18: ("Noventa", "九十"), 19: ("Cem", "百"), 20: ("Modo canal", "频道模式"),
        21: ("Modo frequência", "频率模式"), 22: ("Bateria fraca", "电压低"), 23: ("Bloqueado", "锁定"),
        24: ("Desbloqueado", "解锁"), 25: ("Varredura desligada", "扫描关闭"),
        26: ("Rádio FM ligado", "收音机开启"), 27: ("Varredura ligada", "扫描开启"), 28: ("Confirmar", "确定"),
        29: ("Sair", "退出"), 30: ("Tempo de transmissão esgotado", "发射超时"),
    }
}

# Vozes em chinês: falam os avisos em chinês (AVISOS_CHINES)
VOZES_CHINES = {
    "Xiaoxiao (feminina, chinês mandarim)": ("edge", "zh-CN-XiaoxiaoNeural", False),
    "Yunxi (masculina, chinês mandarim)": ("edge", "zh-CN-YunxiNeural", False),
}


def _monta_rotulos(indices, termos):
    nomes = list(zip(NUMEROS_EN, NUMEROS_PT)) + termos
    assert len(nomes) == len(indices), (len(nomes), len(indices))
    return {slot: par for slot, par in zip(indices, nomes)}


MODELOS = {
    "UV17ProGPS": Modelo("UV17ProGPS", "UV-17 Pro GPS", "PROGRAMCOLORPROU", 0x90000, 72,
                         "Fabrica_UV17ProGPS.vpa", _monta_rotulos(GPS_INDICES, GPS_TERMOS)),
    "UV17Pro": Modelo("UV17Pro", "UV-17 Pro / R / L", "PROGRAMBFNORMALU", 0, 122,
                      "Fabrica_UV17Pro.vpa", _monta_rotulos(PRO_INDICES, PRO_TERMOS)),
}


# O pacote base (.vpa) não é distribuído
# com o PYProg. O usuário indica o arquivo uma vez; uma cópia fica na pasta de configuração.
PASTA_FABRICA_USUARIO = None     # definida pelo programa ao abrir


def caminho_fabrica(chave):
    nome = MODELOS[chave].arquivo_fabrica
    pastas = [PASTA_FABRICA_USUARIO] if PASTA_FABRICA_USUARIO else []
    pastas.append(pasta_dados())       # cópias de desenvolvimento, se houver
    for pasta in pastas:
        c = os.path.join(pasta, nome)
        if os.path.isfile(c):
            return c
    return None


def instala_fabrica(caminho):
    """Confere o .vpa base escolhido pelo usuário e guarda uma cópia. Retorna a chave do modelo."""
    chave, vozes, _ = _le_vpa(caminho)
    if not PASTA_FABRICA_USUARIO:
        raise ErroPacote("Pasta de configuração não definida.")
    os.makedirs(PASTA_FABRICA_USUARIO, exist_ok=True)
    with open(caminho, "rb") as f:
        dados = f.read()
    grava_atomico(os.path.join(PASTA_FABRICA_USUARIO, MODELOS[chave].arquivo_fabrica), dados)
    return chave


def pasta_dados():
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "dados")


# ---------------------------------------------------------------------------
# Codec OKI ADPCM (compatível com "sox -t vox")
# ---------------------------------------------------------------------------

_OKI_PASSOS = [
    256, 272, 304, 336, 368, 400, 448, 496, 544, 592, 656, 720, 800, 880, 960,
    1056, 1168, 1280, 1408, 1552, 1712, 1888, 2080, 2288, 2512, 2768, 3040, 3344,
    3680, 4048, 4464, 4912, 5392, 5936, 6528, 7184, 7904, 8704, 9568, 10528,
    11584, 12736, 14016, 15408, 16960, 18656, 20512, 22576, 24832,
]
_MUDANCA_PASSO = [-1, -1, -1, -1, 2, 4, 6, 8]


class _EstadoAdpcm:
    __slots__ = ("ultimo", "indice")

    def __init__(self):
        self.ultimo = 0
        self.indice = 0

    def decodifica(self, codigo):
        passo = _OKI_PASSOS[self.indice]
        s = ((((codigo & 7) << 1) | 1) * passo >> 3) & ~15
        if codigo & 8:
            s = -s
        s += self.ultimo
        if s < -32768:
            s = -32768
        elif s > 32767:
            s = 32767
        self.indice += _MUDANCA_PASSO[codigo & 7]
        if self.indice < 0:
            self.indice = 0
        elif self.indice > 48:
            self.indice = 48
        self.ultimo = s
        return s

    def codifica(self, amostra):
        delta = amostra - self.ultimo
        sinal = 0
        if delta < 0:
            sinal = 8
            delta = -delta
        codigo = (delta << 2) // _OKI_PASSOS[self.indice]
        codigo = sinal | min(codigo, 7)
        self.decodifica(codigo)
        return codigo


def adpcm_codifica(pcm) -> bytes:
    """PCM 16 bits mono 8 kHz -> OKI ADPCM (nibble alto primeiro)."""
    est = _EstadoAdpcm()
    saida = bytearray((len(pcm) + 1) // 2)
    for i, amostra in enumerate(pcm):
        c = est.codifica(int(amostra))
        if i & 1:
            saida[i >> 1] |= c
        else:
            saida[i >> 1] = c << 4
    return bytes(saida)


def adpcm_decodifica(dados: bytes) -> array:
    est = _EstadoAdpcm()
    pcm = array("h")
    for b in dados:
        pcm.append(est.decodifica(b >> 4))
        pcm.append(est.decodifica(b & 15))
    return pcm


def pcm_para_wav(pcm, taxa=8000) -> bytes:
    bio = io.BytesIO()
    with wave.open(bio, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        a = array("h", pcm)
        if sys.byteorder == "big":
            a.byteswap()
        w.writeframes(a.tobytes())
    return bio.getvalue()


# ---------------------------------------------------------------------------
# Áudio
# ---------------------------------------------------------------------------

TAXA_TRAB = 24000   # taxa de trabalho (a voz neural entrega 24 kHz)


class ErroAudio(Exception):
    pass


def _miniaudio():
    try:
        import miniaudio  # type: ignore
        return miniaudio
    except ImportError as e:  # pragma: no cover
        raise ErroAudio("Biblioteca 'miniaudio' não instalada (pip install miniaudio).") from e


def _np():
    try:
        import numpy  # type: ignore
        return numpy
    except ImportError as e:  # pragma: no cover
        raise ErroAudio("Biblioteca 'numpy' não instalada (pip install numpy).") from e


def decodifica_audio(dados: bytes | None = None, caminho: str | None = None):
    """Decodifica MP3, WAV, FLAC ou OGG para float mono a 24 kHz."""
    ma, np = _miniaudio(), _np()
    try:
        if caminho is not None:
            r = ma.decode_file(caminho, output_format=ma.SampleFormat.FLOAT32,
                               nchannels=1, sample_rate=TAXA_TRAB)
        else:
            r = ma.decode(dados, output_format=ma.SampleFormat.FLOAT32,
                          nchannels=1, sample_rate=TAXA_TRAB)
    except Exception as e:
        raise ErroAudio(f"Não foi possível ler o áudio: {e}") from e
    return np.asarray(r.samples, dtype=np.float64)


def _corta_silencio(x, taxa):
    np = _np()
    if x.size == 0:
        return x
    janela = max(1, int(taxa * 0.01))
    n = x.size // janela
    if n == 0:
        return x
    energia = np.sqrt(np.mean(x[:n * janela].reshape(n, janela) ** 2, axis=1))
    limiar = max(energia.max() * 0.04, 1e-4)
    ativos = np.nonzero(energia > limiar)[0]
    if ativos.size == 0:
        return x
    margem = int(taxa * 0.04)
    ini = max(0, ativos[0] * janela - margem)
    fim = min(x.size, (ativos[-1] + 1) * janela + margem)
    return x[ini:fim]


def muda_velocidade(x, fator, taxa=TAXA_TRAB):
    """Acelera ou desacelera sem alterar o tom (WSOLA). fator 1.2 = 20% mais rápido."""
    np = _np()
    if abs(fator - 1.0) < 0.01 or x.size == 0:
        return x
    N = int(taxa * 0.03)
    hs = N // 2
    ha = hs * fator
    tol = int(taxa * 0.008)
    win = np.hanning(N)
    xp = np.concatenate([np.zeros(tol), x, np.zeros(N + 2 * tol)])
    saida_n = int(x.size / fator) + N
    out = np.zeros(saida_n + N)
    norm = np.zeros(saida_n + N)
    k, ant = 0, None
    while True:
        ideal = tol + int(round(k * ha))
        if ideal + N + tol >= xp.size or k * hs + N > out.size:
            break
        if ant is None:
            ini = ideal
        else:
            alvo = xp[ant + hs: ant + hs + N]
            regiao = xp[ideal - tol: ideal + tol + N]
            corr = np.correlate(regiao, alvo, mode="valid")
            ini = ideal - tol + int(np.argmax(corr))
        out[k * hs: k * hs + N] += xp[ini: ini + N] * win
        norm[k * hs: k * hs + N] += win
        ant = ini
        k += 1
    norm[norm < 1e-3] = 1.0
    return (out / norm)[: int(x.size / fator)]


def _para_8k(x):
    """Filtro passa-baixas de boa qualidade (corte em 3,6 kHz) e redução de 24 para 8 kHz."""
    np = _np()
    taps = 161
    fc = 3600.0 / TAXA_TRAB
    n = np.arange(taps) - (taps - 1) / 2
    h = 2 * fc * np.sinc(2 * fc * n) * np.kaiser(taps, 8.6)
    h /= h.sum()
    y = np.convolve(x, h, mode="same")
    return y[::3]


def trata_audio(x, volume=1.0, velocidade=1.0, cortar=True, pico=0.89) -> array:
    """Corta silêncio, ajusta a velocidade, converte para 8 kHz e normaliza."""
    np = _np()
    x = np.asarray(x, dtype=np.float64)
    if cortar:
        x = _corta_silencio(x, TAXA_TRAB)
    x = muda_velocidade(x, velocidade)
    y = _para_8k(x)
    maior = float(np.max(np.abs(y))) if y.size else 0.0
    if maior > 0:
        y = y * (pico / maior) * volume
    y = np.clip(np.round(y * 32767), -32768, 32767).astype(np.int16)
    return array("h", y.tolist())


def silencio(ms=150) -> bytes:
    return adpcm_codifica(array("h", [0] * int(8 * ms)))


# ---------------------------------------------------------------------------
# Vozes em português do Brasil
# ---------------------------------------------------------------------------

class ErroVoz(Exception):
    pass


# nome exibido -> (serviço, identificador, marcar o pedido como pt-BR)
# A marcação de idioma (pt-BR) fez o serviço deixar de responder para Antonio e
# Thalita; todas as vozes voltam ao pedido simples, que sempre gerou áudio.
VOZES = {
    "Microsoft Francisca (feminina, neural, pt-BR)": ("edge", "pt-BR-FranciscaNeural", False),
    "Microsoft Antonio (masculina, neural, pt-BR)": ("edge", "pt-BR-AntonioNeural", False),
}
VOZ_PADRAO = "Microsoft Francisca (feminina, neural, pt-BR)"

# Vozes em inglês, para refazer os avisos em inglês sem o pacote base do CPS.
# Não reproduzem a voz original do rádio: a escolha é de quem ouve.
VOZES_INGLES = {
    "Guy (masculina, inglês americano)": ("edge", "en-US-GuyNeural", False),
    "Christopher (masculina, inglês americano)": ("edge", "en-US-ChristopherNeural", False),
    "Eric (masculina, inglês americano)": ("edge", "en-US-EricNeural", False),
    "Ryan (masculina, inglês britânico)": ("edge", "en-GB-RyanNeural", False),
    "Jenny (feminina, inglês americano)": ("edge", "en-US-JennyNeural", False),
    "Sonia (feminina, inglês britânico)": ("edge", "en-GB-SoniaNeural", False),
}
VOZ_INGLES_PADRAO = "Guy (masculina, inglês americano)"
AMOSTRA_INGLES = "Channel mode. Frequency mode. Scan on."
# como falar os rótulos que são siglas ou abreviações
_FALA_INGLES = {"TOT": "Time out", "CTCSS": "C T C S S", "DCS": "D C S", "BCL": "B C L", "FM On": "F M on",
                "ANI Code": "A N I code", "VOX": "Vox", "Escape": "Exit"}


def fala_ingles(rotulo):
    return _FALA_INGLES.get(rotulo, rotulo)


# Vozes em espanhol: falam os avisos traduzidos abaixo (a partir do rótulo em inglês)
VOZES_ESPANHOL = {
    "Elvira (feminina, espanhol da Espanha)": ("edge", "es-ES-ElviraNeural", False),
    "Alvaro (masculina, espanhol da Espanha)": ("edge", "es-ES-AlvaroNeural", False),
    "Dalia (feminina, espanhol do México)": ("edge", "es-MX-DaliaNeural", False),
    "Jorge (masculina, espanhol do México)": ("edge", "es-MX-JorgeNeural", False),
    "Elena (feminina, espanhol da Argentina)": ("edge", "es-AR-ElenaNeural", False),
    "Tomás (masculina, espanhol da Argentina)": ("edge", "es-AR-TomasNeural", False),
}
AMOSTRA_ESPANHOL = "Modo canal. Modo frecuencia. Escaneo activado."
_NUMEROS_ES = ["cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez", "once",
               "doce", "trece", "catorce", "quince", "dieciséis", "diecisiete", "dieciocho", "diecinueve", "veinte",
               "treinta", "cuarenta", "cincuenta", "sesenta", "setenta", "ochenta", "noventa", "cien"]
_FALA_ESPANHOL = dict(zip(NUMEROS_EN, _NUMEROS_ES)) | {
    "TOT": "tiempo de transmisión agotado", "Channel Mode": "modo canal", "Frequency Mode": "modo frecuencia",
    "Power Low": "potencia baja", "Lock": "teclado bloqueado", "Unlock": "teclado desbloqueado",
    "Scan Off": "escaneo desactivado", "Scan On": "escaneo activado", "FM On": "radio FM", "Enter": "guardado",
    "Escape": "salir", "End": "fin", "Welcome": "bienvenido", "Scanning Begin": "escaneo iniciado",
    "Scanning Stop": "escaneo detenido", "CTCSS": "C T C S S", "DCS": "D C S", "Power": "potencia",
    "Save Mode": "modo ahorro", "Memory Channel": "guardar canal", "Delete Channel": "borrar canal",
    "Frequency Set": "ajuste de frecuencia", "Squelch": "silenciador",
    "Transmit Over Time": "tiempo límite de transmisión", "Backlight Selection": "luz de fondo", "VOX": "vox",
    "Frequency Direction": "dirección del desplazamiento", "Offset frequency": "desplazamiento de frecuencia",
    "Transmitting Memory": "memoria de transmisión", "Receiving Memory": "memoria de recepción",
    "Emergency Call": "llamada de emergencia", "Low Voltage": "batería baja", "Voice Prompt": "aviso de voz",
    "Band Selection": "selección de banda", "Dual Standby": "doble escucha", "Channel Bandwidth": "ancho de banda",
    "Optional Signal": "señal opcional", "Mute Mode": "modo silencio", "BCL": "bloqueo de canal ocupado",
    "Beep Prompt": "pitido de teclas", "ANI Code": "código A N I", "Initialisation": "restablecer valores",
    "Confirm": "confirmar", "Cancel": "cancelar", "On": "activado", "Off": "desactivado", "Menu": "menú",
    "Frequency Scan": "escaneo de frecuencia",
}


def idioma_voz(voz):
    return ("en" if voz in VOZES_INGLES else "es" if voz in VOZES_ESPANHOL
            else "zh" if voz in VOZES_CHINES else "pt")


def fala_idioma(rotulo_en, idioma):
    """Texto do aviso no idioma da voz (inglês ou espanhol), a partir do rótulo original em inglês."""
    return fala_ingles(rotulo_en) if idioma == "en" else _FALA_ESPANHOL.get(rotulo_en, rotulo_en)
_trava_ssml = __import__("threading").Lock()


ULTIMO_AVISO_VOZ = ""   # preenchido quando foi preciso usar o modo antigo


def _voz_edge(texto, voz, velocidade, idioma_ptbr=False, espera=12):
    """Pede a voz ao serviço da Microsoft. Com idioma_ptbr=True, o texto vai dentro de
    <lang xml:lang='pt-BR'> (forma documentada para vozes multilíngues)."""
    try:
        import edge_tts  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise ErroVoz("Biblioteca 'edge-tts' não instalada (pip install edge-tts).") from e
    try:
        import edge_tts.communicate as ec  # type: ignore
    except ImportError:  # pragma: no cover
        ec = None
    taxa = f"{int(round((velocidade - 1.0) * 100)):+d}%"
    dados = bytearray()
    with _trava_ssml:
        original = getattr(ec, "mkssml", None) if ec else None
        if idioma_ptbr and original is not None:
            def mk(tc, t):
                ssml = original(tc, t)
                i = ssml.find("<prosody")
                j = ssml.rfind("</voice>")
                if i < 0 or j < 0:
                    return ssml
                return ssml[:i] + "<lang xml:lang='pt-BR'>" + ssml[i:j] + "</lang>" + ssml[j:]
            ec.mkssml = mk
        try:
            com = edge_tts.Communicate(texto, voz, rate=taxa, connect_timeout=8, receive_timeout=espera)
            for parte in com.stream_sync():
                if parte.get("type") == "audio":
                    dados += parte["data"]
        finally:
            if original is not None:
                ec.mkssml = original
    if not dados:
        raise ErroVoz("O serviço de voz não retornou áudio.")
    return bytes(dados)


def _com_limite(fn, segundos):
    """Executa fn numa linha separada e desiste depois de 'segundos' (o serviço às vezes não responde
    e a biblioteca não respeita o próprio limite de tempo)."""
    import threading
    res = {}

    def roda():
        try:
            res["ok"] = fn()
        except Exception as e:  # noqa: BLE001
            res["erro"] = e
    t = threading.Thread(target=roda, daemon=True)
    t.start()
    t.join(segundos)
    if t.is_alive():
        raise ErroVoz(f"O serviço de voz não respondeu em {segundos} segundos.")
    if "erro" in res:
        raise res["erro"]
    return res["ok"]


def obtem_voz(texto: str, voz=VOZ_PADRAO, velocidade=1.0) -> tuple[bytes, bool]:
    """Retorna (mp3, velocidade_ja_aplicada). Usa limites de conexão e recebimento em cada tentativa."""
    global ULTIMO_AVISO_VOZ
    ULTIMO_AVISO_VOZ = ""
    texto = (texto or "").strip()
    if not texto:
        raise ErroVoz("Texto vazio.")
    _, ident, ptbr = (VOZES.get(voz) or VOZES_INGLES.get(voz) or VOZES_ESPANHOL.get(voz)
                      or VOZES_CHINES.get(voz) or VOZES[VOZ_PADRAO])
    tentativas = ([True] if ptbr else []) + [False, False]
    ultimo = None
    for n, marca in enumerate(tentativas):
        try:
            mp3 = _com_limite(lambda: _voz_edge(texto, ident, velocidade, idioma_ptbr=marca), 30)
            if ptbr and not marca:
                ULTIMO_AVISO_VOZ = ("O serviço não aceitou a marcação de português do Brasil para esta voz; "
                                    "o áudio foi gerado do jeito antigo e pode sair com sotaque de Portugal.")
            return mp3, True
        except ErroVoz as e:
            if "não instalada" in str(e):
                raise
            ultimo = e
        except Exception as e:  # rede, tempo esgotado, limite de uso etc.
            ultimo = e
        if n < len(tentativas) - 1 and not marca:
            time.sleep(1.5)
    raise ErroVoz(f"O serviço de voz não respondeu (verifique a internet ou tente outra voz). "
                  f"Detalhe: {type(ultimo).__name__} {ultimo}")


def gera_voz_ptbr(texto: str, voz=VOZ_PADRAO, velocidade=1.0, volume=1.0) -> bytes:
    base = os.environ.get("APPDATA") or os.path.expanduser("~/.config")
    pasta = os.path.join(base, "EditorVozesBaofeng", "CacheVozes")
    chave = assinatura("codec-2.7", texto.strip(), voz, velocidade, volume)
    caminho = os.path.join(pasta, chave + ".vox")
    try:
        with open(caminho, "rb") as f:
            audio = f.read()
        if audio:
            return audio
    except OSError:
        pass
    mp3, aplicada = obtem_voz(texto, voz, velocidade)
    x = decodifica_audio(dados=mp3)
    pcm = trata_audio(x, volume=volume, velocidade=1.0 if aplicada else velocidade)
    audio = adpcm_codifica(pcm)
    if audio:
        try:
            grava_atomico(caminho, audio)
        except OSError:
            pass  # cache indisponível não invalida a fala produzida
    return audio


def importa_arquivo(caminho: str, volume=1.0, velocidade=1.0, cortar=True) -> bytes:
    pcm = trata_audio(decodifica_audio(caminho=caminho), volume=volume,
                      velocidade=velocidade, cortar=cortar)
    return adpcm_codifica(pcm)


# ---------------------------------------------------------------------------
# Pacote de vozes (.vpa)
# ---------------------------------------------------------------------------

class ErroPacote(Exception):
    pass


MSG_SEM_FABRICA = ("Falta indicar um pacote de vozes (.vpa) deste rádio. Ele preenche os avisos que você não "
                   "gerou. Em Vozes, clique em \"Indicar o pacote base...\" e escolha um pacote .vpa do "
                   "UV-17 Pro GPS.")


def _le_vpa(caminho):
    with open(caminho, "rb") as f:
        dados = f.read()
    nul = dados.find(b"\0", 0, 21)
    if nul < 0:
        raise ErroPacote("Arquivo .vpa inválido (cabeçalho não encontrado).")
    chave = dados[:nul].decode("ascii", "replace")
    if chave not in MODELOS:
        raise ErroPacote(f"Modelo '{chave}' não suportado.")
    buf = dados[nul + 1: nul + 1 + TAM_PACOTE]
    if len(buf) < TAM_PACOTE:
        raise ErroPacote("Arquivo .vpa incompleto.")
    m = MODELOS[chave]
    vozes = []
    for i in range(m.total):
        tam, end = struct.unpack_from("<II", buf, i * 8)
        if tam in (0, 0xFFFFFFFF):
            raise ErroPacote(f"Tabela do pacote termina antes do esperado (item {i}).")
        pos = end - m.inicio
        if pos < TAM_TABELA or pos + tam > TAM_PACOTE:
            raise ErroPacote(f"Índice inválido no item {i}.")
        vozes.append(bytes(buf[pos:pos + tam]))
    textos = {}
    resto = dados[nul + 1 + TAM_PACOTE:]
    if resto.startswith(MARCA_TEXTOS):
        try:
            info = json.loads(resto[len(MARCA_TEXTOS):].decode("utf-8"))
            if info.get("formato") == 2:
                textos = {int(k): v for k, v in info["textos"].items()}
                textos["_origens"] = info.get("origens", {})
            else:
                textos = {int(k): v for k, v in info.items()}
        except Exception:
            textos = {}
    return chave, vozes, textos


class PacoteVozes:
    def __init__(self, chave="UV17ProGPS"):
        self.modelo = MODELOS[chave]
        arq = caminho_fabrica(chave)
        self.tem_fabrica = arq is not None
        if arq:
            _, self.fabrica, _ = _le_vpa(arq)
        else:
            # Sem o pacote base não há áudio de base: o pacote fica incompleto e não pode
            # ser salvo nem enviado até o usuário indicar o arquivo do CPS ou abrir um .vpa completo.
            self.fabrica = [silencio()] * self.modelo.total
        self._completo_marcado = False
        self.vozes = list(self.fabrica)
        self.textos = {s: pt for s, (_, pt) in self.modelo.rotulos.items()}
        self.textos.update({s: pt for s, (_, pt) in AVISOS_CHINES.get(self.modelo.chave, {}).items()})
        self.origens = {}

    # --- estado ------------------------------------------------------------
    def eh_fabrica(self, slot):
        return self.vozes[slot] == self.fabrica[slot]

    def _exige_fabrica(self):
        if not self.tem_fabrica:
            raise ErroPacote(MSG_SEM_FABRICA)

    def restaura(self, slot):
        self._exige_fabrica()
        self.vozes[slot] = self.fabrica[slot]
        self.origens.pop(slot, None)

    @property
    def completo(self):
        """Pronto para enviar: ou há pacote base (que preenche o que não foi gerado), ou todos os
        avisos já têm áudio (gerado ou importado)."""
        if self._completo_marcado or self.tem_fabrica:
            return True
        return all(s in self.origens for s in range(self.modelo.total))

    @completo.setter
    def completo(self, valor):
        self._completo_marcado = bool(valor)

    def faltam(self):
        """Posições que ainda não têm áudio (só faz sentido sem pacote base)."""
        return [s for s in range(self.modelo.total) if s not in self.origens]

    @property
    def slots_chines(self):
        return sorted(AVISOS_CHINES.get(self.modelo.chave, {}))

    def restaura_chines(self):
        """Devolve os avisos em chinês do pacote base indicado."""
        self._exige_fabrica()
        for s in self.slots_chines:
            self.restaura(s)

    def restaura_tudo(self):
        self._exige_fabrica()
        self.vozes = list(self.fabrica)
        self.origens = {}

    def aplica_pacote_ingles(self, caminho):
        """Coloca nos avisos em inglês as vozes de outro pacote .vpa do mesmo modelo
        (por exemplo, pacotes em inglês com outra voz)."""
        self._exige_fabrica()
        chave, vozes, _ = _le_vpa(caminho)
        if chave != self.modelo.chave:
            raise ErroPacote(f"Este pacote é do {MODELOS[chave].nome}; o modelo em uso é o {self.modelo.nome}.")
        self.vozes = list(self.fabrica)
        self.origens = {}
        for s in self.modelo.slots_ingles:
            self.vozes[s] = vozes[s]
            self.origens[s] = {"tipo": "Pacote em inglês"}
        if self.tamanho_usado() > TAM_PACOTE:
            self.vozes = list(self.fabrica)
            raise ErroPacote("O pacote ficou grande demais para a memória do rádio.")

    def define(self, slot, adpcm: bytes, origem=None):
        if not 0 <= slot < self.modelo.total or not isinstance(adpcm, bytes) or not adpcm:
            raise ErroPacote("Posição ou áudio inválido.")
        anterior = self.vozes[slot]
        self.vozes[slot] = adpcm
        if self.tamanho_usado() > TAM_PACOTE:
            self.vozes[slot] = anterior
            raise ErroPacote("O pacote de vozes ficou grande demais para a memória do rádio.")
        self.origens[slot] = origem or {"tipo": "Importada"}

    def assinatura(self):
        return assinatura(self.modelo.chave, *self.vozes, self.textos, self.origens)

    def copia(self):
        p = copy.copy(self)
        p.vozes = list(self.vozes)
        p.textos = dict(self.textos)
        p.origens = copy.deepcopy(self.origens)
        return p

    def precisa_gerar(self, slot, voz, velocidade, volume):
        origem = self.origens.get(slot, {})
        idioma = idioma_voz(voz)
        texto = (fala_idioma(self.modelo.rotulos[slot][0], idioma) if idioma != "pt" and slot in self.modelo.rotulos
                 else self.textos.get(slot, "").strip())
        return origem != {"tipo": "Gerada", "texto": texto, "voz": voz, "velocidade": velocidade, "volume": volume}

    def tamanho_usado(self):
        return TAM_TABELA + sum(len(v) for v in self.vozes)

    def duracao(self, slot):
        return len(self.vozes[slot]) * 2 / 8000.0

    # --- montagem ------------------------------------------------------------
    def monta_buffer(self):
        if not self.completo:
            raise ErroPacote(MSG_SEM_FABRICA)
        usado = self.tamanho_usado()
        if usado > TAM_PACOTE:
            raise ErroPacote("O pacote de vozes ficou grande demais para a memória do rádio.")
        buf = bytearray(TAM_PACOTE)
        pos = TAM_TABELA
        for i, v in enumerate(self.vozes):
            struct.pack_into("<II", buf, i * 8, len(v), self.modelo.inicio + pos)
            buf[pos:pos + len(v)] = v
            pos += len(v)
        buf[pos:] = b"\xff" * (TAM_PACOTE - pos)
        return bytes(buf), pos

    def salva(self, caminho, incluir_textos=True):
        buf, _ = self.monta_buffer()
        dados = self.modelo.chave.encode("ascii") + b"\0" + buf
        if incluir_textos:
            info = {"formato": 2, "textos": self.textos, "origens": self.origens}
            dados += MARCA_TEXTOS + json.dumps(info, ensure_ascii=False).encode("utf-8")
        grava_atomico(caminho, dados)

    @classmethod
    def abre(cls, caminho):
        chave, vozes, textos = _le_vpa(caminho)
        p = cls(chave)
        p.vozes = vozes
        p.completo = True          # um .vpa completo tem todos os áudios
        if textos:
            p.origens = {int(k): v for k, v in textos.pop("_origens", {}).items()}
            p.textos.update({k: v for k, v in textos.items() if isinstance(k, int) and 0 <= k < p.modelo.total and isinstance(v, str)})
        return p


# ---------------------------------------------------------------------------
# Comunicação com o rádio
# ---------------------------------------------------------------------------

class ErroRadio(Exception):
    pass


def crc16(dados: bytes) -> int:
    """CRC-16/XMODEM (polinômio 0x1021, valor inicial 0)."""
    crc = 0
    for b in dados:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return crc


def monta_pacote(cmd: int, arg: int, carga: bytes) -> bytes:
    corpo = bytes([cmd & 0xFF, (arg >> 8) & 0xFF, arg & 0xFF,
                   (len(carga) >> 8) & 0xFF, len(carga) & 0xFF]) + carga
    c = crc16(corpo)
    return b"\xa5" + corpo + bytes([c >> 8, c & 0xFF])


def lista_portas():
    try:
        from serial.tools import list_ports  # type: ignore
    except ImportError:
        return []
    return [(p.device, p.description) for p in list_ports.comports()]


class _Conexao:
    def __init__(self, porta, log=None):
        try:
            import serial  # type: ignore
        except ImportError as e:  # pragma: no cover
            raise ErroRadio("Biblioteca 'pyserial' não instalada (pip install pyserial).") from e
        try:
            self.s = serial.Serial(porta, 115200, bytesize=8, parity="N", stopbits=1, timeout=0.05, write_timeout=3)
        except Exception as e:
            raise ErroRadio(f"Não foi possível abrir a porta {porta}: {e}") from e
        try:
            self.s.dtr = True
            self.s.rts = True
        except Exception:
            pass
        self.log = log or (lambda m: None)

    def fecha(self):
        try:
            self.s.close()
        except Exception:
            pass

    def _le_exato(self, n, limite):
        dados = bytearray()
        while len(dados) < n:
            if time.monotonic() > limite:
                return None
            parte = self.s.read(n - len(dados))
            if parte:
                dados += parte
        return bytes(dados)

    def le_resposta(self, cmd_esperado, espera):
        """Lê respostas até achar a do comando esperado; retorna a carga ou None."""
        limite = time.monotonic() + espera
        while time.monotonic() < limite:
            b = self.s.read(1)
            if not b or b[0] != 0xA5:
                continue
            cab = self._le_exato(5, limite + 0.5)
            if cab is None:
                return None
            n = (cab[3] << 8) | cab[4]
            if n > 1024:
                self.log("Resposta com tamanho inválido, ignorada.")
                continue
            resto = self._le_exato(n + 2, limite + 0.5)
            if resto is None:
                return None
            carga, crc_rx = resto[:n], (resto[n] << 8) | resto[n + 1]
            if crc16(cab + carga) != crc_rx:
                self.log("Resposta com CRC inválido, ignorada.")
                continue
            if cab[0] != cmd_esperado:
                continue
            return carga
        return None

    def transacao(self, cmd, arg, carga, espera=1.0, tentativas=6):
        pacote = monta_pacote(cmd, arg, carga)
        for t in range(tentativas):
            self.s.write(pacote)
            resp = self.le_resposta(cmd, espera)
            if resp is None:
                self.log(f"Sem resposta ao comando 0x{cmd:02X} (tentativa {t + 1}).")
                continue
            if resp == b"Y":
                return
            raise ErroRadio(f"O rádio recusou o comando 0x{cmd:02X} (resposta {resp!r}).")
        raise ErroRadio(f"O rádio não respondeu ao comando 0x{cmd:02X}.")


def envia_dados(porta: str, handshake: str, buf: bytes, usado: int, endereco: int, blocos: int,
                progresso=None, log=None, rotulo="dados"):
    """Grava 'usado' bytes de 'buf' na flash do rádio (protocolo dos utilitários da Baofeng)."""
    progresso = progresso or (lambda p, txt: None)
    log = log or (lambda m: None)
    total = (usado + 1023) // 1024
    if len(buf) < total * 1024:
        buf = bytes(buf) + b"\xff" * (total * 1024 - len(buf))
    con = _Conexao(porta, log)
    try:
        progresso(0, "Conectando...")
        con.s.reset_input_buffer()
        hs = handshake.encode("ascii")
        ok = False
        for t in range(6):
            con.s.write(hs)
            limite = time.monotonic() + 1.0
            while time.monotonic() < limite:
                b = con.s.read(1)
                if b == b"\x06":
                    ok = True
                    break
            if ok:
                break
            log(f"Sem confirmação do handshake (tentativa {t + 1}).")
        if not ok:
            raise ErroRadio("O rádio não respondeu. Confira o cabo, a porta COM e se o rádio está ligado.")
        con.s.write(b"D")
        time.sleep(0.1)

        progresso(1, "Handshake...")
        con.transacao(0x02, 0, b"PROGRAM")
        progresso(2, f"Apagando memória ({rotulo})...")
        end = struct.pack("<I", endereco)
        con.transacao(0x04, 0x4504, end + bytes([blocos >> 8, blocos & 0xFF]), espera=3.0)
        con.transacao(0x03, 0, end)
        for pid in range(total):
            bloco = buf[pid * 1024:(pid + 1) * 1024]
            con.transacao(0x57, pid, bloco)
            pct = int((pid + 1) * 100 / total)
            progresso(pct, f"Enviando {rotulo}... {pct}%")
        con.s.write(monta_pacote(0x06, 0, b"Over"))
        time.sleep(0.1)
        progresso(100, "Concluído")
    finally:
        con.fecha()


def envia_ao_radio(porta: str, pacote: PacoteVozes, progresso=None, log=None):
    """Grava o pacote de vozes no rádio (protocolo do BFVoicePackEditor)."""
    buf, usado = pacote.monta_buffer()
    envia_dados(porta, pacote.modelo.handshake, buf, usado, ENDERECO_RADIO, BLOCOS_APAGAR,
                progresso, log, "vozes")

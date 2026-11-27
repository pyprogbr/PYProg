"""Filtros e conversão das repetidoras da RepeaterBook para canais do PYProg.

Este módulo não usa a rede. Filtra e converte cada repetidora em um canal
(programacao.Canal), que depois passa pela mesma conferência da importação de canais.
"""
import math
import re

import programacao as pg

# Modos que são analógicos. Os demais (DV, DMR, C4FM etc.) não funcionam nos rádios analógicos.
MODOS_ANALOGICOS = {"FM", "NFM", "WFM", "AM"}


def distancia_km(lat1, lon1, lat2, lon2):
    """Distância em quilômetros entre dois pontos (fórmula de Haversine)."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


_RE_CIDADE = re.compile(r"\bnear (.+?),")
_RE_ABERTA = re.compile(r"\bOPEN\b")


def cidade_de(comentario):
    """Cidade do comentário do RepeaterBook ('CALL near Cidade, ...'). Vazio se não houver."""
    m = _RE_CIDADE.search(comentario or "")
    return m.group(1).strip() if m else ""


def aberta_de(comentario):
    """True se o comentário diz OPEN (uso aberto). Sem a palavra, não é considerada aberta."""
    return bool(_RE_ABERTA.search(comentario or ""))


def _float(txt):
    try:
        return float(str(txt).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


def _tom(tipo, r_tone, c_tone, dtcs, pol):
    """Converte as colunas de tom do CHIRP para os textos de tom do PYProg. Retorna (tx, rx) ou None."""
    tipo = (tipo or "").strip()
    if tipo in ("", "None"):
        return pg.SEM_TOM, pg.SEM_TOM
    if tipo == "Tone":
        t = _float(r_tone)
        return (f"{t:.1f}", pg.SEM_TOM) if t is not None else None
    if tipo == "TSQL":
        t = _float(r_tone)
        return (f"{t:.1f}", f"{t:.1f}") if t is not None else None
    if tipo == "DTCS":
        try:
            cod = int(str(dtcs).strip())
        except ValueError:
            return None
        pol = (pol or "NN").upper().ljust(2, "N")
        return f"D{cod:03d}{pol[0]}", f"D{cod:03d}{pol[1]}"
    return None  # combinações cruzadas não são tratadas nesta versão


# Bandas que o RepeaterBook/CHIRP oferecem na busca. Inclui faixas que o PYProg não grava;
# nelas a repetidora aparece na lista como "Não usada: fora das faixas do rádio".
BANDAS_REPETIDORAS = [
    (28.0, 29.7, "10 m"),
    (50.0, 54.0, "6 m"),
    (144.0, 148.0, "2 m"),
    (219.0, 225.0, "1,25 m"),
    (420.0, 450.0, "70 cm"),
    (462.0, 467.0, "FRS/GMRS"),
    (902.0, 928.0, "33 cm"),
    (1240.0, 1300.0, "23 cm"),
]


def filtra(regs, faixas=None, so_analogicas=True, texto="", ponto=None, km=None, so_abertas=False):
    """Aplica os filtros e devolve uma lista de (registro, distância em km ou None).
    faixas: lista de (inicio_mhz, fim_mhz); None ou lista vazia = sem filtro de banda.
    ponto: (lat, lon) ou None. km: raio máximo."""
    out = []
    t = texto.strip().casefold()
    for r in regs:
        if faixas and not any(a <= r["freq_mhz"] <= b for a, b in faixas):
            continue
        if so_analogicas and r["modo"] not in MODOS_ANALOGICOS:
            continue
        if so_abertas and not r["aberta"]:
            continue
        if t and t not in (r["nome"] + " " + r["comentario"]).casefold():
            continue
        dist = None
        if ponto and r["lat"] is not None and r["lon"] is not None:
            dist = distancia_km(ponto[0], ponto[1], r["lat"], r["lon"])
            if km is not None and dist > km:
                continue
        elif ponto and km is not None:
            continue  # sem coordenadas não dá para medir a distância
        out.append((r, dist))
    if ponto:
        out.sort(key=lambda x: (x[1] is None, x[1] or 0, x[0]["freq_mhz"]))
    return out


def para_canal(r):
    """Converte um registro em pg.Canal. Retorna (canal, motivo). Canal é None se não der para usar."""
    if not pg.dentro_das_faixas(round(r["freq_mhz"] * 1e6), pg.FAIXAS_LIBERADAS_PADRAO):
        return None, "fora das faixas do rádio"
    tom = _tom(r["tom"], r["r_tone"], r["c_tone"], r["dtcs"], r["dtcs_pol"])
    if tom is None:
        return None, "tom que o PYProg não trata nesta versão"
    tx, rx = tom
    for t in (tx, rx):
        if t not in (pg.SEM_TOM,) and t not in pg.OPCOES_TOM:
            return None, f"tom {t} fora da lista do rádio"
    duplex = r["duplex"] if r["duplex"] in ("+", "-") else "Simplex"
    offset = round(r["offset_mhz"] * 1e6) if duplex != "Simplex" else 0
    nome = r["nome"] or r["comentario"]
    c = pg.Canal(numero=0, vazio=False, nome=nome, rx=round(r["freq_mhz"] * 1e6),
                 duplex=duplex, offset=offset, tom_tx=tx, tom_rx=rx)
    return c, ""


# ------------------------------------------------------------ localização do computador

_PS_LOCALIZACAO = r"""
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Devices.Geolocation.Geolocator,Windows.Devices.Geolocation,ContentType=WindowsRuntime]
$tarefa = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
  $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
  $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Espera($op, $tipo) {
  $t = $tarefa.MakeGenericMethod($tipo).Invoke($null, @($op)); $t.Wait(-1) | Out-Null; $t.Result }
$geo = [Windows.Devices.Geolocation.Geolocator]::new()
$pos = Espera ($geo.GetGeopositionAsync()) ([Windows.Devices.Geolocation.Geoposition])
$p = $pos.Coordinate.Point.Position
$cultura = [Globalization.CultureInfo]::InvariantCulture
$p.Latitude.ToString($cultura) + ';' + $p.Longitude.ToString($cultura)
"""


def le_localizacao(texto):
    """Lê a resposta 'lat;lon' do script do Windows. Levanta ValueError se não for válida."""
    partes = (texto or "").strip().split(";")
    if len(partes) != 2:
        raise ValueError("resposta inesperada do Windows")
    try:
        lat, lon = float(partes[0]), float(partes[1])
    except ValueError:
        raise ValueError("coordenadas inválidas")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("coordenadas fora do intervalo")
    return lat, lon


def localizacao_windows(timeout=20):
    """Pede a localização ao serviço de localização do Windows 10 e 11.
    Levanta RuntimeError com o motivo se não for possível (desligado, negado ou sem suporte)."""
    import subprocess
    import sys
    if not sys.platform.startswith("win"):
        raise RuntimeError("a localização do Windows só existe no Windows")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", _PS_LOCALIZACAO],
                           capture_output=True, text=True, timeout=timeout, creationflags=flags)
    except subprocess.TimeoutExpired:
        raise RuntimeError("o Windows demorou demais para informar a localização")
    except OSError:
        raise RuntimeError("não foi possível executar o PowerShell")
    if r.returncode != 0:
        raise RuntimeError("o Windows não informou a localização (verifique se o serviço de localização está ligado)")
    try:
        return le_localizacao(r.stdout)
    except ValueError as e:
        raise RuntimeError(f"o Windows não informou a localização: {e}")

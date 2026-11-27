"""Consulta direta à API de exportação da RepeaterBook (aplicativo aprovado, token por usuário).

Regras da aprovação: o User-Agent é fixo e igual ao aprovado; o token do usuário vai no cabeçalho
X-RB-App-Token; redirecionamentos não são seguidos; em 429 o programa para e não insiste; os dados
ficam só na memória desta sessão. Crédito obrigatório: "Data courtesy of RepeaterBook.com."
"""
import json
import urllib.error
import urllib.parse
import urllib.request

import repetidoras as rep

# Idêntico ao aprovado pela RepeaterBook. Não trocar a versão sem nova aprovação.
USER_AGENT = "PYProg/1.0.1 (Windows; +mailto:pu2keu@gmail.com)"
URL_BASE = "https://www.repeaterbook.com/api/exportROW.php"
ATRIBUICAO = "Data courtesy of RepeaterBook.com."
TEMPO_LIMITE = 40

# Filtros enviados à API. Os valores de país e modo são suposições a confirmar no primeiro teste real.
PARAMETROS_BRASIL = {"country": "Brazil", "mode": "analog"}

# Cache só em memória, restrito ao necessário para a consulta; some ao fechar o programa.
_CACHE = {}


class ErroAPI(Exception):
    pass


class _SemRedirecionamento(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None   # a RepeaterBook pede que 3xx seja tratado como parada


_ABRIDOR = urllib.request.build_opener(_SemRedirecionamento)


def consulta(token, parametros):
    """Devolve a lista bruta de registros da API. Levanta ErroAPI com mensagem para o usuário."""
    chave = (token, tuple(sorted(parametros.items())))
    if chave in _CACHE:
        return _CACHE[chave]
    url = URL_BASE + "?" + urllib.parse.urlencode(parametros)
    pedido = urllib.request.Request(url, headers={
        "X-RB-App-Token": token,
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    })
    try:
        with _ABRIDOR.open(pedido, timeout=TEMPO_LIMITE) as r:
            corpo = r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise ErroAPI("A RepeaterBook recusou o token ou a permissão (código %d). Confira o token "
                          "no painel de API Apps." % e.code)
        if e.code == 429:
            raise ErroAPI("Limite de consultas da RepeaterBook atingido. Aguarde um pouco antes de tentar de novo.")
        if 300 <= e.code < 400:
            raise ErroAPI("A RepeaterBook respondeu com redirecionamento (código %d). A consulta foi interrompida." % e.code)
        raise ErroAPI("A RepeaterBook respondeu com erro (código %d)." % e.code)
    except (urllib.error.URLError, OSError) as e:
        raise ErroAPI("Não foi possível conectar à RepeaterBook (%s)." % e)
    try:
        dados = json.loads(corpo)
    except ValueError:
        raise ErroAPI("A resposta da RepeaterBook não está em JSON.")
    if isinstance(dados, dict):
        if str(dados.get("status", "")).lower() == "error":
            raise ErroAPI("A RepeaterBook devolveu erro: %s" % (dados.get("message") or "sem detalhes"))
        for k in ("results", "data", "repeaters"):
            if isinstance(dados.get(k), list):
                dados = dados[k]
                break
        else:
            dados = []
    if not isinstance(dados, list):
        raise ErroAPI("Formato de resposta da RepeaterBook não reconhecido.")
    _CACHE[chave] = dados
    return dados


def _sim(v):
    return str(v or "").strip().lower() in ("yes", "sim", "true", "1")


def _modo_da_linha(d):
    """Modo pelos indicadores da RepeaterBook (FM Analog, DMR, System Fusion, etc.)."""
    if _sim(d.get("FM Analog")):
        return "FM"
    if _sim(d.get("DMR")):
        return "DMR"
    if _sim(d.get("System Fusion")):
        return "DV"
    for campo, nome in (("NXDN", "NXDN"), ("APCO P-25", "P25"), ("D-Star", "DSTAR"), ("M17", "M17")):
        if _sim(d.get(campo)):
            return nome
    return "OUTRO"


def _deslocamento(saida, entrada):
    """Duplex e deslocamento no padrão do CHIRP: a saída do repetidor é a frequência de RX do rádio."""
    if saida is None or entrada is None or abs(saida - entrada) < 1e-6:
        return "", 0.0
    if entrada < saida:
        return "-", round(saida - entrada, 6)
    return "+", round(entrada - saida, 6)


def normaliza_lista(brutos):
    """Converte os registros da RepeaterBook (campos da API de exportação) no formato da busca.
    Devolve (registros, tem_coordenadas)."""
    regs = []
    tem_coord = False
    for d in brutos:
        if not isinstance(d, dict):
            continue
        saida = _float_ou_none(d.get("Frequency"))
        if saida is None:
            continue
        entrada = _float_ou_none(d.get("Input Freq"))
        duplex, offset = _deslocamento(saida, entrada)
        lat = _float_ou_none(d.get("Lat"))
        lon = _float_ou_none(d.get("Long"))
        if lat is not None and lon is not None:
            tem_coord = True
        else:
            lat, lon = None, None
        pl = str(d.get("PL") or "").strip()
        tsq = str(d.get("TSQ") or "").strip()
        cidade = str(d.get("Nearest City") or "").strip()
        uso = str(d.get("Use") or "").strip().upper()
        aberta = uso == "OPEN"
        indicativo = str(d.get("Callsign") or "").strip()
        regs.append({
            "nome": indicativo,
            "comentario": str(d.get("Notes") or "").strip(),
            "cidade": cidade,
            "aberta": aberta,
            "freq_mhz": saida,
            "duplex": duplex,
            "offset_mhz": offset,
            "tom": "TSQL" if pl else ("Tone" if tsq else ""),
            "r_tone": pl or tsq or None,
            "c_tone": pl or tsq or None,
            "dtcs": None,
            "dtcs_pol": None,
            "modo": _modo_da_linha(d),
            "lat": lat,
            "lon": lon,
        })
    return regs, tem_coord


def _float_ou_none(v):
    try:
        return float(str(v).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None



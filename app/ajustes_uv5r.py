# -*- coding: utf-8 -*-
"""Ajustes do UV-5R pela árvore de ajustes do driver do CHIRP.

Mostra os 100 ajustes que o driver lê da imagem, organizados em grupos (menus) e
submenus. Cada gravação relê a árvore da própria imagem, troca só o valor
escolhido e grava de volta, para que nada que mudou desde a abertura seja perdido.
"""
from chirp import memmap, settings as cs
from chirp.drivers import uv5r as _drv


class ErroAjuste(Exception):
    pass


GRUPOS = {
    "basic": "Básico",
    "advanced": "Avançado",
    "other": "Outros",
    "workmode": "Modo de trabalho e VFO",
    "dtmf": "DTMF e PTT ID",
    "service": "Serviço (faixas e squelch de fábrica)",
}

SUBMENUS = {
    "": "Geral",
    "pttid": "Códigos de PTT ID (1 a 15)",
    "ani": "ANI e código de alarme",
    "vfoa": "VFO A",
    "vfob": "VFO B",
    "wmchannel": "Canais de memória (MR A e B)",
    "limits_new.vhf": "Limites de frequência VHF",
    "limits_new.uhf": "Limites de frequência UHF",
    "squelch_new.vhf": "Squelch VHF (níveis)",
    "squelch_new.uhf": "Squelch UHF (níveis)",
    "firmware_msg": "Mensagem do firmware",
    "poweron_msg": "Mensagem ao ligar",
    "sixpoweron_msg": "Mensagem 6+ ao ligar",
}


def rotulo_grupo(nome):
    return GRUPOS.get(nome, nome)


def _chave_submenu(nome):
    """Prefixo que define o submenu de um ajuste (ex.: 'vfoa.freq' -> 'vfoa')."""
    if nome.startswith(("limits_new.", "squelch_new.")):
        return ".".join(nome.split(".")[:2])
    if nome.startswith("pttid/"):
        return "pttid"
    if nome.startswith("ani."):
        return "ani"
    if "." in nome:
        return nome.split(".")[0]
    return ""


def _radio(img):
    return _drv.BaofengUV5RGeneric(memmap.MemoryMapBytes(bytes(img)))


def arvore(img):
    """Árvore de ajustes lida da imagem (lança exceção se o driver não conseguir ler)."""
    arv = _radio(img).get_settings()
    if arv is None:
        raise ErroAjuste("o driver não conseguiu ler os ajustes desta imagem")
    return arv


def submenus(grupo):
    """Lista de (chave, rótulo, [ajustes]) do grupo, na ordem em que aparecem."""
    ordem, mapa = [], {}
    for el in grupo:
        if not isinstance(el, cs.RadioSetting):
            continue
        k = _chave_submenu(el.get_name())
        if k not in mapa:
            mapa[k] = []
            ordem.append(k)
        mapa[k].append(el)
    return [(k, SUBMENUS.get(k, k), mapa[k]) for k in ordem]


def _procura(arv, nome):
    for el in arv.walk():
        if isinstance(el, cs.RadioSetting) and el.get_name() == nome:
            return el
    raise ErroAjuste(f"ajuste desconhecido: {nome}")


def grava(img, nome, valor):
    """Grava um ajuste na imagem (bytearray), lendo a árvore atual dela."""
    if not isinstance(img, bytearray):
        raise ErroAjuste("a imagem precisa ser um bytearray")
    radio = _radio(img)
    arv = radio.get_settings()
    if arv is None:
        raise ErroAjuste("o driver não conseguiu ler os ajustes desta imagem")
    _procura(arv, nome).value.set_value(valor)
    radio.set_settings(arv)
    novo = radio.get_mmap().get_packed()
    if len(novo) != len(img):
        raise ErroAjuste("tamanho da imagem alterado ao gravar o ajuste")
    img[:] = novo

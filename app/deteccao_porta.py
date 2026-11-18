# -*- coding: utf-8 -*-
"""Identificação da porta COM do cabo de programação.

Pergunta a cada porta disponível, uma por uma, se há um rádio do modelo escolhido ali.
Em cada porta envia só a sequência com que a leitura começa e espera o "ACK" do rádio.
Não envia dados de programação e não grava nada no rádio.
"""
import time

import configuracao_radio as cr
import uv5r

ACK = b"\x06"
# Portas que não são cabo de programação (um fone ou GPS Bluetooth, por exemplo)
EXCLUIDAS = ("bluetooth",)
SEM_TESTE = {"IC2730A", "RT3S"}

RESPONDEU = "respondeu"
SEM_RESPOSTA = "sem resposta"
NAO_ABRIU = "não abriu"


class ErroDeteccao(Exception):
    pass


def candidatas(portas):
    """Portas (device, descrição) que podem ser o cabo, sem as excluídas."""
    return [p for p, desc in portas if not any(x in (desc or "").lower() for x in EXCLUIDAS)]


def _responde_uv5r(porta):
    p = uv5r.Porta(porta)
    try:
        for magia in uv5r.MAGICS:
            for b in magia:
                p.write(bytes([b]))
                time.sleep(0.01)
            if p.read(1) == ACK:
                return True
        return False
    finally:
        p.close()


def _responde_baofeng(porta, chave):
    p = cr._Porta(porta)
    try:
        p.limpa()
        p.envia(cr.CLONE[chave]["magic"])
        try:
            return p.recebe(1, "identificação") == ACK
        except cr.ErroConfig:
            return False
    finally:
        p.fecha()


def procura(chave, portas, progresso=None):
    """Testa as portas e devolve [(porta, RESPONDEU | SEM_RESPOSTA | NAO_ABRIU), ...]."""
    if chave in SEM_TESTE:
        raise ErroDeteccao("Este modelo não tem identificação automática de porta. Escolha a porta na lista.")
    if chave != "UV5R" and chave not in cr.CLONE:
        raise ErroDeteccao("Modelo sem identificação de porta.")
    resultado = []
    for porta in candidatas(portas):
        if progresso:
            progresso(porta)
        try:
            ok = _responde_uv5r(porta) if chave == "UV5R" else _responde_baofeng(porta, chave)
        except (uv5r.ErroUV5R, cr.ErroConfig):
            resultado.append((porta, NAO_ABRIU))
            continue
        resultado.append((porta, RESPONDEU if ok else SEM_RESPOSTA))
    return resultado

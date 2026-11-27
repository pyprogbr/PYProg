# -*- coding: utf-8 -*-
"""
Conversão de canais entre modelos de rádio.

A origem (a programação carregada) é ajustada às regras do rádio de destino, e o
resultado traz a situação de cada linha para a tela de revisão. A revisão só
mostra. Os ajustes de nome e potência são feitos depois, na programação do rádio de
destino, a partir do arquivo exportado.

Situações (derivadas da linha):
  ok          passa sem mudança
  ajustado    mudou algo (nome cortado, sem acento, potência)
  descartado  não cabe no destino (fora das faixas ou sem espaço)
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field, replace

import programacao as pg

OK, AJUSTADO, DESCARTADO = "ok", "ajustado", "descartado"


@dataclass
class Linha:
    origem: pg.Canal
    canal: pg.Canal | None = None                # já ajustado ao destino; None se fora das faixas
    motivos: list = field(default_factory=list)  # ajustes feitos ou motivo de descarte
    sem_espaco: bool = False                     # cabe nas faixas, mas o destino já está cheio

    @property
    def destino(self) -> pg.Canal | None:
        return None if (self.canal is None or self.sem_espaco) else self.canal

    @property
    def situacao(self) -> str:
        if self.destino is None:
            return DESCARTADO
        return AJUSTADO if self.motivos else OK

    def motivos_texto(self, total_canais=None) -> str:
        textos = list(self.motivos)
        if self.sem_espaco:
            textos.append(f"sem espaço: o destino comporta {total_canais} canais")
        return "; ".join(textos)


def _sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")


def _potencia(valor: str) -> str:
    if valor in pg.POTENCIAS:
        return valor
    return "Baixa" if valor.lower().startswith(("m", "b")) else "Alta"


def ajusta(origem: pg.Canal, destino: pg.Perfil) -> Linha:
    """Ajusta um canal às regras do destino. Sem canal de destino se as frequências não couberem."""
    rx_mhz = origem.rx / 1e6
    if not destino.rx_valido(origem.rx):
        return Linha(origem, None, [f"{rx_mhz:.4f} MHz fora das faixas do destino"])
    tx = origem.tx
    if tx is not None and origem.modo != "AM" and not destino.tx_valido(tx):
        return Linha(origem, None, [f"transmissão em {tx / 1e6:.4f} MHz fora das faixas do destino"])

    motivos = []
    nome = _sem_acento(origem.nome)
    if nome != origem.nome:
        motivos.append("acento removido do nome")
    if len(nome) > destino.nome_max:
        motivos.append(f"nome cortado de {len(nome)} para {destino.nome_max} caracteres")
        nome = nome[:destino.nome_max].rstrip()
    potencia = _potencia(origem.potencia)
    if potencia != origem.potencia:
        motivos.append(f"potência {origem.potencia} ajustada para {potencia}")
    canal = replace(origem, numero=0, nome=nome, potencia=potencia, perfil=destino, bruto=b"\xff" * 32)
    return Linha(origem, canal, motivos)


def numera(linhas, destino: pg.Perfil):
    """Numera os canais aceitos em ordem. Os que passam do limite do destino ficam como sem espaço."""
    n = 0
    for l in linhas:
        l.sem_espaco = False
        if l.canal is None:
            continue
        n += 1
        if n <= destino.total_canais:
            l.canal = replace(l.canal, numero=n)
        else:
            l.sem_espaco = True
    return linhas


def converte(canais, destino: pg.Perfil):
    """Devolve a lista de Linha (uma por canal ocupado da origem), na ordem da origem."""
    linhas = [ajusta(c, destino) for c in canais if not c.vazio]
    return numera(linhas, destino)


def canais_do_destino(linhas):
    return [l.destino for l in linhas if l.destino is not None]


def resumo(linhas):
    cont = {OK: 0, AJUSTADO: 0, DESCARTADO: 0}
    for l in linhas:
        cont[l.situacao] += 1
    return (f"{cont[OK] + cont[AJUSTADO]} canais convertidos, {cont[AJUSTADO]} ajustados, "
            f"{cont[DESCARTADO]} descartados")

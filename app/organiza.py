"""Organização dos canais dos rádios analógicos: ordenar, apagar e recortar.

As regras são as mesmas para todos os rádios. As diferenças de cada modelo ficam nos
adaptadores abaixo, sem mudar a lógica:

  - Rádios com zonas (UV-17 Pro, UV-17 Pro GPS): ordenar e compactar acontecem dentro de cada
    zona, para que um canal nunca saia da zona em que o rádio o guarda.
  - Rádios sem zonas (UV-21 Pro V2, UV-5R, IC-2730A): a lista inteira é um único escopo.
  - IC-2730A: os bancos (A a J) e os ajustes de cada canal acompanham o canal, e a
    gravação de cada canal é feita pelo driver do CHIRP (icom2730.aplica_ordem).
"""

POR_NOME = "nome"
POR_FREQUENCIA = "frequencia"


def _chave(nome, freq, numero, por):
    nm = (nome or "").strip().casefold()
    if por == POR_NOME:
        return (nm == "", nm, freq, numero)
    return (freq, nm, numero)


class Uv:
    """Adaptador dos rádios da programação em bytes (programacao.Programacao).
    Números de canal começam em 1."""

    def __init__(self, prog):
        self.prog = prog

    def faixas(self):
        p = self.prog.perfil
        if not p.tem_zonas:
            return [list(range(1, p.total_canais + 1))]
        por = p.canais_por_zona
        return [list(range(z * por + 1, min((z + 1) * por, p.total_canais) + 1))
                for z in range(p.total_zonas)]

    def ocupado(self, n):
        return not self.prog.canal(n).vazio

    def chave(self, n, por):
        c = self.prog.canal(n)
        return _chave(c.nome, c.rx, n, por)

    def aplica(self, nums, ordem):
        self.prog.reordena(nums[0], ordem)

    def apaga(self, n):
        self.prog.apaga(n)


class Icom:
    """Adaptador do IC-2730A (driver do CHIRP). Números de canal começam em 0.
    Não tem zonas: a lista inteira é um escopo, e os bancos acompanham cada canal."""

    def __init__(self, radio, ic):
        self.radio = radio
        self.ic = ic

    def faixas(self):
        return [list(range(self.ic.TOTAL_CANAIS))]

    def ocupado(self, n):
        return not self.radio.get_memory(n).empty

    def chave(self, n, por):
        m = self.radio.get_memory(n)
        return _chave(m.name, m.freq, n, por)

    def aplica(self, nums, ordem):
        self.ic.aplica_ordem(self.radio, ordem)

    def apaga(self, n):
        self.radio.erase_memory(n)


def faixa_de(ad, n):
    for f in ad.faixas():
        if n in f:
            return f
    return []


def ordena(ad, nums, por):
    """Ordena os canais ocupados de 'nums' (uma faixa, em ordem). Vazios ficam no fim.
    Retorna True se alguma posição mudou."""
    ocup = [n for n in nums if ad.ocupado(n)]
    if not ocup:
        return False
    vaz = [n for n in nums if not ad.ocupado(n)]
    ocup.sort(key=lambda n: ad.chave(n, por))
    ordem = ocup + vaz
    if ordem == list(nums):
        return False
    ad.aplica(nums, ordem)
    return True


def compacta(ad, nums):
    """Puxa os canais ocupados de 'nums' para o começo, sem mudar a ordem entre eles.
    Retorna True se mudou algo."""
    ocup = [n for n in nums if ad.ocupado(n)]
    vaz = [n for n in nums if not ad.ocupado(n)]
    ordem = ocup + vaz
    if ordem == list(nums):
        return False
    ad.aplica(nums, ordem)
    return True


def apaga(ad, numeros):
    """Apaga os canais e compacta a faixa de cada um, para não sobrar buraco."""
    for n in numeros:
        ad.apaga(n)
    for f in ad.faixas():
        if any(n in f for n in numeros):
            compacta(ad, f)
    return len(numeros)


NOTA_ORDEM = ("Os canais vazios vão para o fim. Nos rádios com zonas,\n"
              "a ordem vale só para a zona escolhida. Bancos e ajustes\n"
              "de cada canal vão junto.")


def monta_menu(menu, ordena_fn, tem_nome=True):
    """Menu 'Ordenar canais' igual em todos os rádios analógicos."""
    menu.limpa()
    if tem_nome:
        menu.add_command(label="Por nome (A a Z)", command=lambda: ordena_fn(POR_NOME))
    menu.add_command(label="Por frequência", command=lambda: ordena_fn(POR_FREQUENCIA))
    menu.add_separator()
    menu.add_nota(NOTA_ORDEM)

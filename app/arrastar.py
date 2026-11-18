# -*- coding: utf-8 -*-
"""Arrastar linhas de uma lista (ttk.Treeview) com o mouse para mudar a ordem dos canais."""
import tkinter as tk

import tema

LIMIAR = 6          # pixels de movimento antes de começar a arrastar


def move_bloco(ordem, origens, destino, depois=False):
    """Tira os itens 'origens' da lista 'ordem' e os põe antes (ou depois) de 'destino',
    mantendo a ordem entre eles. Retorna a lista nova."""
    origens = [o for o in ordem if o in set(origens)]
    if not origens or destino in origens:
        return list(ordem)
    resto = [o for o in ordem if o not in set(origens)]
    i = resto.index(destino) + (1 if depois else 0)
    return resto[:i] + origens + resto[i:]


class ArrastaLinhas:
    """Liga o arraste na lista. ao_soltar(iids_arrastados, iid_destino, depois) faz a mudança.
    pode(): se o arraste está permitido agora (ex.: sem busca ativa). Depois de um arraste,
    'arrastou' fica True até o próximo clique, para outros tratadores ignorarem o soltar."""

    def __init__(self, tv, ao_soltar, pode=lambda: True, aviso=None):
        self.tv, self.ao_soltar, self.pode, self.aviso = tv, ao_soltar, pode, aviso
        self.inicio = None
        self.ativo = False
        self.arrastou = False
        self.linha = tk.Frame(tv, bg=tema.C["azul"], height=3)
        tv.bind("<ButtonPress-1>", self._aperta, add="+")
        tv.bind("<B1-Motion>", self._move, add="+")
        tv.bind("<ButtonRelease-1>", self._solta, add="+")

    def _aperta(self, ev):
        self.arrastou = False
        self.ativo = False
        linha = self.tv.identify_row(ev.y)
        if not linha or self.tv.identify_region(ev.x, ev.y) not in ("cell", "tree"):
            self.inicio = None
            return
        self.inicio = (ev.x, ev.y, linha)
        self._reduzir = None
        sel = self.tv.selection()
        if linha in sel and len(sel) > 1 and not (ev.state & 0x0005):    # sem Shift/Ctrl
            # mantém a seleção múltipla para poder arrastar o grupo; vira seleção simples
            # no soltar, se não houver arraste
            self._reduzir = linha
            self.tv.focus(linha)
            return "break"

    def _alvo(self, y):
        linha = self.tv.identify_row(y)
        if not linha:
            filhos = self.tv.get_children()
            if not filhos:
                return None, False
            ultimo = filhos[-1]
            bb = self.tv.bbox(ultimo)
            if bb and y > bb[1] + bb[3]:
                return ultimo, True
            return filhos[0], False
        bb = self.tv.bbox(linha)
        depois = bool(bb) and y > bb[1] + bb[3] / 2
        return linha, depois

    def _move(self, ev):
        if not self.inicio:
            return
        x0, y0, linha0 = self.inicio
        if not self.ativo:
            if abs(ev.y - y0) < LIMIAR:
                return
            if not self.pode():
                if self.aviso:
                    self.aviso()
                self.inicio = None
                return
            if linha0 not in self.tv.selection():
                self.tv.selection_set(linha0)
            self.ativo = True
            self.tv.configure(cursor="sb_v_double_arrow")
        # rola a lista quando o ponteiro chega perto das bordas
        altura = self.tv.winfo_height()
        if ev.y < 24:
            self.tv.yview_scroll(-1, "units")
        elif ev.y > altura - 12:
            self.tv.yview_scroll(1, "units")
        alvo, depois = self._alvo(ev.y)
        if alvo is None:
            return
        bb = self.tv.bbox(alvo)
        if bb:
            y = bb[1] + (bb[3] if depois else 0) - 1
            self.linha.place(x=0, y=y, relwidth=1.0)
            self.linha.lift()

    def _solta(self, ev):
        if not self.ativo:
            if getattr(self, "_reduzir", None):
                self.tv.selection_set(self._reduzir)
                self._reduzir = None
            self.inicio = None
            return
        self.ativo = False
        self.arrastou = True
        self.linha.place_forget()
        self.tv.configure(cursor="")
        alvo, depois = self._alvo(ev.y)
        sel = list(self.tv.selection())
        self.inicio = None
        if alvo is None or not sel or alvo in sel:
            return
        self.ao_soltar(sel, alvo, depois)


def liga_setas(tv, soltou, pode=lambda: True):
    """Ctrl+↑ / Ctrl+↓ move as linhas selecionadas uma posição, pelo mesmo caminho do arraste."""
    def move(d):
        sel = list(tv.selection())
        filhos = list(tv.get_children())
        if not sel or not pode():
            return "break"
        idx = sorted(filhos.index(x) for x in sel if x in filhos)
        if not idx:
            return "break"
        j = idx[0] - 1 if d < 0 else idx[-1] + 1
        if 0 <= j < len(filhos):
            soltou(sel, filhos[j], d > 0)
        return "break"
    tv.bind("<Control-Up>", lambda e: move(-1))
    tv.bind("<Control-Down>", lambda e: move(1))

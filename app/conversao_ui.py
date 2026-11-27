# -*- coding: utf-8 -*-
"""Tela de conferência da conversão de canais entre rádios.

Só mostra o resultado: cada canal com a situação (ok, ajustado ou descartado) e o
motivo. Dá para filtrar por situação. Os ajustes de nome e potência são feitos
depois, no arquivo exportado, que é aberto no programa para gravar no rádio.
"""
import tkinter as tk
from tkinter import ttk

import conversao as cv
import programacao as pg
import tema

COLUNAS = (
    ("sit", "Situação", 13, "w"),
    ("onum", "Nº", 5, "center"),
    ("onome", "Nome original", 18, "w"),
    ("orx", "RX (MHz)", 11, "center"),
    ("dnum", "Nº destino", 9, "center"),
    ("dnome", "Nome no destino", 16, "w"),
    ("dpot", "Potência", 9, "center"),
    ("motivo", "Motivo", 52, "w"),
)
ROTULO_SIT = {cv.OK: "Ok", cv.AJUSTADO: "Ajustado", cv.DESCARTADO: "Descartado"}
COR_SIT = {cv.OK: tema.C["ok"], cv.AJUSTADO: tema.C["aviso"], cv.DESCARTADO: tema.C["erro"]}
FILTROS = [("todos", "Todos")] + [(s, ROTULO_SIT[s]) for s in (cv.OK, cv.AJUSTADO, cv.DESCARTADO)]


class JanelaRevisao(tk.Toplevel):
    """Conferência da importação. `ao_importar` recebe a lista de canais do destino, na ordem, e devolve
    True quando importou (a janela então fecha). `origem_nome` aparece no título da janela."""

    def __init__(self, app, linhas, destino: pg.Perfil, ao_importar=None, origem_nome=""):
        raiz = app.raiz
        super().__init__(raiz)
        self.app = app
        self.linhas = linhas
        self.destino = destino
        self.ao_importar = ao_importar
        self.title(f"Importar canais para {destino.nome}" + (f"  ·  {origem_nome}" if origem_nome else ""))
        self.transient(raiz)
        larg = min(1200, raiz.winfo_screenwidth() - 40)
        alt = min(760, raiz.winfo_screenheight() - 80)
        self.geometry(f"{larg}x{alt}+{max(0, raiz.winfo_rootx() + (raiz.winfo_width() - larg) // 2)}"
                      f"+{max(0, raiz.winfo_rooty() + 10)}")

        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)

        ttk.Label(f, style="Suave.TLabel", wraplength=larg - 60, text=(
            "Confira os canais que serão importados. Depois de importar, você pode fazer os ajustes "
            "na programação e gravar no rádio.")).pack(fill="x")
        self.lbl_resumo = ttk.Label(f, font=getattr(app, "fonte_negrito", "TkDefaultFont"))
        self.lbl_resumo.pack(fill="x", pady=(8, 4))

        self.filtro = tk.StringVar(value="todos")
        barra_filtro = ttk.Frame(f)
        barra_filtro.pack(fill="x", pady=(0, 6))
        self.rotulos_filtro = {}
        for valor, texto in FILTROS:
            cor = COR_SIT.get(valor, tema.C["texto"])
            rb = tk.Radiobutton(barra_filtro, text=texto, value=valor, variable=self.filtro, fg=cor,
                                bg=tema.C["fundo"], activebackground=tema.C["fundo"],
                                selectcolor=tema.C["fundo"], font="TkDefaultFont",
                                command=self.renderiza, cursor="hand2")
            rb.pack(side="left", padx=(0, 18))
            self.rotulos_filtro[valor] = rb

        meio = ttk.Frame(f)
        meio.pack(fill="both", expand=True)
        self.tv = ttk.Treeview(meio, columns=[c for c, *_ in COLUNAS], show="headings", selectmode="browse")
        for c, titulo, largura, ancora in COLUNAS:
            self.tv.heading(c, text=titulo)
            self.tv.column(c, width=app.largura_texto(largura) if hasattr(app, "largura_texto")
                           else largura * 8, anchor=ancora, stretch=c == "motivo")
        rol = ttk.Scrollbar(meio, orient="vertical", command=self.tv.yview)
        self.tv.configure(yscrollcommand=rol.set)
        self.tv.pack(side="left", fill="both", expand=True)
        rol.pack(side="right", fill="y")
        self.tv.tag_configure("zebra", background=tema.C["zebra"])
        for sit, cor in COR_SIT.items():
            self.tv.tag_configure(sit, foreground=cor)
        self.tv.bind("<<TreeviewSelect>>", lambda _e: self._mostra_motivo())

        self.lbl_motivo = ttk.Label(f, style="Suave.TLabel", wraplength=larg - 60, text="")
        self.lbl_motivo.pack(fill="x", pady=(6, 0))

        rodape = ttk.Frame(f)
        rodape.pack(fill="x", pady=(12, 0))
        ttk.Button(rodape, text="Cancelar", command=self.destroy).pack(side="right", padx=(6, 0))
        self.bt_importar = tema.botao(rodape, "Importar canais", self.importa, "download", "Gravar.TButton")
        self.bt_importar.pack(side="right")

        self.renderiza()

    # ----- tabela ---------------------------------------------------------
    def _contagem(self):
        cont = {cv.OK: 0, cv.AJUSTADO: 0, cv.DESCARTADO: 0}
        for l in self.linhas:
            cont[l.situacao] += 1
        return cont

    def renderiza(self):
        """Redesenha a tabela com o filtro escolhido."""
        filtro = self.filtro.get()
        self.tv.delete(*self.tv.get_children(""))
        for i, l in enumerate(self.linhas):
            if filtro != "todos" and l.situacao != filtro:
                continue
            d = l.destino
            valores = (
                f"●  {ROTULO_SIT[l.situacao]}", l.origem.numero, l.origem.nome, f"{l.origem.rx / 1e6:.4f}",
                d.numero if d else "", d.nome if d else "", d.potencia if d else "",
                l.motivos_texto(self.destino.total_canais),
            )
            self.tv.insert("", "end", iid=str(i), values=valores, tags=[l.situacao])
        tema.zebra(self.tv)
        self._atualiza_resumo()
        self._mostra_motivo()

    def _atualiza_resumo(self):
        self.lbl_resumo.config(text=cv.resumo(self.linhas))
        cont = self._contagem()
        for valor, texto in FILTROS:
            n = len(self.linhas) if valor == "todos" else cont[valor]
            self.rotulos_filtro[valor].config(text=f"{texto} ({n})")
        pode = bool(cv.canais_do_destino(self.linhas)) and self.ao_importar is not None
        self.bt_importar.state(["!disabled"] if pode else ["disabled"])

    def _mostra_motivo(self):
        sel = self.tv.selection()
        if not sel:
            self.lbl_motivo.config(text="")
            return
        l = self.linhas[int(sel[0])]
        texto = l.motivos_texto(self.destino.total_canais) or "Sem ajustes. O canal passa como está."
        self.lbl_motivo.config(text=f"Motivo: {texto}")

    # ----- saída ----------------------------------------------------------
    def importa(self):
        canais = cv.canais_do_destino(self.linhas)
        if canais and self.ao_importar is not None and self.ao_importar(canais):
            self.destroy()

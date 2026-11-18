# -*- coding: utf-8 -*-
"""Aba "Programação" dos rádios DMR com arquivo .rdt (Retevis RT3S e Baofeng DM-1701):
canais, zonas, listas de varredura, contatos, grupos de RX, mensagens e ajustes gerais."""
import os
import shutil
import time
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import arrastar
import configuracao_radio as cr
import dmr380 as dm
import exportar
import tema

# Larguras em caracteres: mais espaço para Nome e Contato, menos para os campos curtos
COLUNAS = [("num", "Nº", 6), ("nome", "Nome", 22), ("rx", "RX (MHz)", 11), ("tx", "TX (MHz)", 11),
           ("modo", "Modo", 10), ("cc", "CC", 4), ("slot", "Slot", 5), ("contato", "Contato", 20),
           ("tomrx", "Tom RX", 8), ("tomtx", "Tom TX", 8), ("pot", "Potência", 9)]
COL_ZONA = [("pos", "Posição", 7), ("num", "Canal", 6), ("nome", "Nome", 17), ("rx", "RX (MHz)", 11),
            ("modo", "Modo", 10), ("cc", "CC", 4), ("slot", "Slot", 4), ("contato", "Contato", 14)]
COL_CONT = [("num", "Nº", 6), ("nome", "Nome", 18), ("id", "ID", 10), ("tipo", "Tipo", 9), ("tom", "Tom de chamada", 13)]
COL_MEMB = [("pos", "Posição", 7), ("num", "Nº", 6), ("nome", "Nome", 18), ("det", "", 14)]
LIMITE_HISTORICO = 50
TONS = [""] + [f"{t:.1f}" for t in (67.0, 69.3, 71.9, 74.4, 77.0, 79.7, 82.5, 85.4, 88.5, 91.5, 94.8, 97.4, 100.0,
                                     103.5, 107.2, 110.9, 114.8, 118.8, 123.0, 127.3, 131.8, 136.5, 141.3, 146.2,
                                     151.4, 156.7, 159.8, 162.2, 165.5, 167.9, 171.3, 173.8, 177.3, 179.9, 183.5,
                                     186.2, 189.9, 192.8, 196.6, 199.5, 203.5, 206.5, 210.7, 218.1, 225.7, 229.1,
                                     233.6, 241.8, 250.3, 254.1)]
# Códigos DCS padrão (digite D023I, por exemplo, para o invertido)
DCS = [23, 25, 26, 31, 32, 36, 43, 47, 51, 53, 54, 65, 71, 72, 73, 74, 114, 115, 116, 122, 125, 131, 132,
       134, 143, 145, 152, 155, 156, 162, 165, 172, 174, 205, 212, 223, 225, 226, 243, 244, 245, 246, 251,
       252, 255, 261, 263, 265, 266, 271, 274, 306, 311, 315, 325, 331, 332, 343, 346, 351, 356, 364, 365,
       371, 411, 412, 413, 423, 431, 432, 445, 446, 452, 454, 455, 462, 464, 465, 466, 503, 506, 516, 523,
       526, 532, 546, 565, 606, 612, 624, 627, 631, 632, 654, 662, 664, 703, 712, 723, 731, 732, 734, 743,
       754]
TONS = TONS + [f"D{n:03d}N" for n in DCS]
SEM_TX = {0xFFFF: "Último canal ativo", 0: "Canal selecionado"}
SEM_PRIO = {0xFFFF: "Nenhum", 0: "Canal selecionado"}


def _centraliza(j, raiz):
    j.update_idletasks()
    j.geometry(f"+{max(0, raiz.winfo_rootx() + (raiz.winfo_width() - j.winfo_reqwidth()) // 2)}"
               f"+{max(0, raiz.winfo_rooty() + (raiz.winfo_height() - j.winfo_reqheight()) // 4)}")


class EditorCanalDMR(tk.Toplevel):
    def __init__(self, aba, n):
        super().__init__(aba.app.raiz)
        self.aba, self.n = aba, n
        cp = aba.cp
        self.vfo = n if isinstance(n, str) else None      # "A" ou "B": edita o VFO
        f = cp.campos_vfo(n) if self.vfo else cp.campos_canal(n)
        novo = f is None
        if novo:
            f = dm._campos_canal(dm._MODELO_CANAL)
            f.update(nome="", rx=0, tx=0, potencia="Alta", tot=180)
        self.title(f"VFO {n}" if self.vfo else f"Canal {n}" + (" (novo)" if novo else ""))
        self.transient(aba.app.raiz)
        self.resizable(False, False)
        corpo = ttk.Frame(self, padding=12)
        corpo.pack(fill="both", expand=True)
        abas = ttk.Notebook(corpo)
        abas.grid(row=0, column=0, columnspan=3, sticky="nsew")
        paginas = [ttk.Frame(abas, padding=(0, 10, 0, 0)), ttk.Frame(abas, padding=(0, 10, 0, 0))]
        abas.add(paginas[0], text="Canal")
        abas.add(paginas[1], text="Mais ajustes")
        self.contatos = [(c["numero"], f"{c['nome']} ({c['id']})") for c in cp.contatos()]
        self.grupos = [(g, cp.nome_grupo(g)) for g in cp.grupos()]
        self.varreds = [(i, cp.varredura(i)["nome"]) for i in cp.varreduras()]
        # referência a um item que não existe (o CPS mostra em branco): mantida como está
        for lista, k in ((self.contatos, f["contato"]), (self.grupos, f["grupo"]), (self.varreds, f["varredura"])):
            if k and all(i != k for i, _ in lista):
                lista.append((k, f"(nº {k}, vazio)"))
        rot = lambda lista, k: next((t for i, t in lista if i == k), "Nenhum")  # noqa: E731
        self.v = {
            "nome": tk.StringVar(value=f["nome"]), "modo": tk.StringVar(value=f["modo"]),
            "rx": tk.StringVar(value=dm.mhz(f["rx"]) if f["rx"] else ""),
            "tx": tk.StringVar(value=dm.mhz(f["tx"]) if f["tx"] else ""),
            "potencia": tk.StringVar(value=f["potencia"]), "largura": tk.StringVar(value=f["largura"]),
            "squelch": tk.StringVar(value=str(f["squelch"])), "tot": tk.StringVar(value=str(f["tot"])),
            "admissao": tk.StringVar(value=f["admissao"]),
            "varredura": tk.StringVar(value=rot(self.varreds, f["varredura"])),
            "tom_rx": tk.StringVar(value=f["tom_rx"]), "tom_tx": tk.StringVar(value=f["tom_tx"]),
            "cc": tk.StringVar(value=str(f["cc"])), "slot": tk.StringVar(value=str(f["slot"])),
            "contato": tk.StringVar(value=rot(self.contatos, f["contato"])),
            "grupo": tk.StringVar(value=rot(self.grupos, f["grupo"])),
            "privacidade": tk.StringVar(value=f["privacidade"]),
            "privacidade_n": tk.StringVar(value=str(f["privacidade_n"])),
        }
        self.b = {k: tk.BooleanVar(value=f[k]) for k in ("so_rx", "vox", "autoscan")}
        self.x = {}
        for k, (_, _, _, _, _, op) in dm.EXTRAS_CANAL.items():
            self.x[k] = (tk.BooleanVar(value=f[k]) if op is None or op == "inv"
                         else tk.StringVar(value=self._rot_extra(k, f[k])))
        self.f = f

        def grupo(titulo, linhas, col, row=0):
            lf = ttk.LabelFrame(paginas[row], text=titulo, padding=8)
            lf.grid(row=0, column=col, sticky="nsew", padx=6)
            for i, (r, w) in enumerate(linhas):
                if r:
                    ttk.Label(lf, text=r).grid(row=i, column=0, sticky="w", pady=3, padx=(0, 8))
                w_ = w(lf)
                w_.grid(row=i, column=1 if r else 0, columnspan=1 if r else 2, sticky="w", pady=3)
            return lf

        def ent(var, w=14):
            return lambda p: ttk.Entry(p, textvariable=var, width=w)

        def cb(var, valores, w=14, edita=False):
            return lambda p: ttk.Combobox(p, textvariable=var, values=valores, width=w,
                                          state="normal" if edita else "readonly")

        def chk(var, txt):
            return lambda p: ttk.Checkbutton(p, text=txt, variable=var)

        grupo("Canal", [
            ("Nome (até 16 letras)", (lambda p: ttk.Entry(p, textvariable=self.v["nome"], width=18,
                                                          state="disabled")) if self.vfo
             else ent(self.v["nome"], 18)),
            ("Modo", cb(self.v["modo"], ["Analógico", "Digital"])),
            ("RX (MHz)", ent(self.v["rx"])),
            ("TX (MHz)", ent(self.v["tx"])),
            ("Potência", cb(self.v["potencia"], list(dm.POTENCIAS))),
            ("Tempo máximo de TX (s)", cb(self.v["tot"], ["0"] + [str(x * 15) for x in range(1, 38)])),
            ("Lista de varredura", cb(self.v["varredura"], ["Nenhum"] + [t for _, t in self.varreds], 18)),
            ("Admissão para transmitir", cb(self.v["admissao"], dm.ADMISSAO)),
            (None, chk(self.b["so_rx"], "Só recepção")),
            (None, chk(self.b["autoscan"], "Varredura automática")),
            (None, chk(self.b["vox"], "VOX")),
        ], 0)
        grupo("Digital", [
            ("Color code", cb(self.v["cc"], [str(x) for x in range(16)], 6)),
            ("Slot", cb(self.v["slot"], ["1", "2"], 6)),
            ("Contato", cb(self.v["contato"], ["Nenhum"] + [t for _, t in self.contatos], 22)),
            ("Grupo de RX", cb(self.v["grupo"], ["Nenhum"] + [t for _, t in self.grupos], 22)),
            ("Privacidade", cb(self.v["privacidade"], dm.PRIVACIDADE)),
            ("Chave de privacidade", cb(self.v["privacidade_n"], [str(x) for x in range(1, 17)], 6)),
        ], 1)
        grupo("Analógico", [
            ("Largura de banda", cb(self.v["largura"], list(dm.LARGURAS))),
            ("Squelch", cb(self.v["squelch"], [str(x) for x in range(10)], 6)),
            ("Tom de RX", cb(self.v["tom_rx"], TONS, 10, edita=True)),
            ("Tom de TX", cb(self.v["tom_tx"], TONS, 10, edita=True)),
        ], 2)
        def extras(quadro):
            out = []
            for k, (rot, q, _, _, _, op) in dm.EXTRAS_CANAL.items():
                if q != quadro:
                    continue
                if op is None or op == "inv":
                    out.append((None, chk(self.x[k], rot)))
                elif isinstance(op, tuple):
                    out.append((rot, cb(self.x[k], self._opcoes_num(k), 12)))
                else:
                    out.append((rot, cb(self.x[k], list(op.values()), 16)))
            return out

        grupo("Mais ajustes do canal", extras("mais"), 0, 1)
        grupo("Digital: mais ajustes", extras("dig"), 1, 1)
        lf = grupo("Analógico: sinalização", extras("ana"), 2, 1)
        dec = ttk.Frame(lf)
        dec.grid(row=len(extras("ana")) + 1, column=0, columnspan=2, sticky="w", pady=(4, 0))
        for i in range(8):
            ttk.Checkbutton(dec, text=str(i + 1), variable=self.x[f"decode{i + 1}"]).grid(
                row=0, column=i, sticky="w", padx=(0, 4))
        ttk.Label(lf, text="Decode (sinalização DTMF)").grid(row=len(extras("ana")), column=0, columnspan=2,
                                                            sticky="w", pady=(4, 0))
        ttk.Label(corpo, style="Suave.TLabel", justify="left", wraplength=760,
                  text="Tom: deixe vazio para desligado; CTCSS como 88.5; DCS como D023N (normal) ou D023I "
                       "(invertido). TX vazio repete o RX (simplex). Ajustes que o PYProg não mostra são "
                       "mantidos como estão no arquivo.").grid(row=1, column=0, columnspan=3, sticky="w",
                                                              pady=(10, 0), padx=6)
        bt = ttk.Frame(corpo)
        bt.grid(row=2, column=0, columnspan=3, sticky="e", pady=(10, 0))
        ttk.Button(bt, text="Cancelar", command=self.destroy).pack(side="right")
        ttk.Button(bt, text="Salvar", command=self.salvar, style="Neutro.TButton").pack(side="right", padx=8)
        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<Return>", lambda e: self.salvar())
        _centraliza(self, aba.app.raiz)
        self.grab_set()

    def _opcoes_num(self, k):
        maximo = dm.EXTRAS_CANAL[k][5][1]
        if k == "emergencia":
            cp = self.aba.cp
            return ["Nenhum"] + [f"{i}: {cp.sistema(i)['nome']}" for i in cp.sistemas()]
        if k in ("emergencia", "gps"):
            return ["Nenhum"] + [str(i) for i in range(1, maximo + 1)]
        return [str(i) for i in range(maximo + 1)]

    def _rot_extra(self, k, v):
        if k == "emergencia" and v:
            cp = self.aba.cp
            return f"{v}: {cp.sistema(v)['nome']}" if v in cp.sistemas() else str(v)
        if isinstance(dm.EXTRAS_CANAL[k][5], tuple):
            return "Nenhum" if k in ("emergencia", "gps") and not v else str(v)
        return v

    def _valor_extra(self, k):
        v = self.x[k].get()
        if isinstance(dm.EXTRAS_CANAL[k][5], tuple):
            return 0 if v == "Nenhum" else v.split(":")[0]
        return v

    @staticmethod
    def _indice(lista, texto):
        return next((i for i, t in lista if t == texto), 0)

    def salvar(self):
        cp = self.aba.cp
        v = self.v
        try:
            rx = dm.le_hz(v["rx"].get())
            tx = dm.le_hz(v["tx"].get()) if v["tx"].get().strip() else rx
            f = dict(self.f)
            f.update(nome=v["nome"].get(), modo=v["modo"].get(), rx=rx, tx=tx, potencia=v["potencia"].get(),
                     largura=v["largura"].get(), squelch=int(v["squelch"].get()), tot=int(v["tot"].get()),
                     admissao=v["admissao"].get(), varredura=self._indice(self.varreds, v["varredura"].get()),
                     tom_rx=v["tom_rx"].get(), tom_tx=v["tom_tx"].get(), cc=int(v["cc"].get()),
                     slot=int(v["slot"].get()), contato=self._indice(self.contatos, v["contato"].get()),
                     grupo=self._indice(self.grupos, v["grupo"].get()), privacidade=v["privacidade"].get(),
                     privacidade_n=int(v["privacidade_n"].get()),
                     **{k: b.get() for k, b in self.b.items()},
                     **{k: self._valor_extra(k) for k in self.x})
            if f["modo"] == "Digital" and not f["contato"]:
                if not messagebox.askyesno("Canal", "Canal digital sem contato: o rádio não terá para quem "
                                                    "transmitir. Salvar assim mesmo?", parent=self):
                    return
            if self.vfo:
                cp.grava_vfo(self.vfo, f)
            else:
                cp.grava_canal(self.n, f)
        except (dm.ErroDMR, ValueError) as e:
            messagebox.showerror("Canal", str(e), parent=self)
            return
        self.aba.alterado()
        self.destroy()


class EscolheItens(tk.Toplevel):
    """Lista para escolher vários itens (canais ou contatos) e acrescentar."""

    def __init__(self, aba, titulo, itens, ao_ok, modo_de=None):
        super().__init__(aba.app.raiz)
        self.title(titulo)
        self.transient(aba.app.raiz)
        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)
        self.busca = tk.StringVar()
        e = ttk.Entry(f, textvariable=self.busca, width=40)
        e.pack(fill="x")
        from programacao_ui import _dica_no_campo
        _dica_no_campo(e, self.busca, "Buscar")
        # modo_de(n) devolve "Analógico" ou "Digital" para o canal n; sem ele, não há filtro de modo
        self.modo_de = modo_de
        self.filtro_modo = tk.StringVar(value="Todos")
        if modo_de:
            # Caixas com tique no mesmo padrão do programa; só uma fica marcada por vez
            linha_modo = ttk.Frame(f)
            linha_modo.pack(fill="x", pady=(8, 0))
            ttk.Label(linha_modo, text="Mostrar:").pack(side="left", padx=(0, 10))
            self._caixas_modo = {}
            for rotulo in ("Todos", "Analógicos", "Digitais"):
                v = tk.BooleanVar(value=(rotulo == "Todos"))
                self._caixas_modo[rotulo] = v
                ttk.Checkbutton(linha_modo, text=rotulo, variable=v,
                                command=lambda r=rotulo: self._escolhe_modo(r)).pack(side="left", padx=(0, 12))
        self.itens = itens
        self.tv = ttk.Treeview(f, columns=("num", "nome", "det"), show="headings", height=18, selectmode="extended")
        for c, t, w in (("num", "Nº", 6), ("nome", "Nome", 20), ("det", "", 14)):
            self.tv.heading(c, text=t, anchor="w")
            self.tv.column(c, width=aba.app.largura_texto(w), anchor="w")
        self.tv.pack(fill="both", expand=True, pady=8)
        self.busca.trace_add("write", lambda *_: self._preenche())
        self._preenche()
        ttk.Label(f, text="Selecione um ou mais (Ctrl ou Shift) e clique em Acrescentar.",
                  style="Suave.TLabel").pack(anchor="w")
        bt = ttk.Frame(f)
        bt.pack(fill="x", pady=(8, 0))

        def ok():
            sel = [int(i) for i in self.tv.selection()]
            self.destroy()
            if sel:
                ao_ok(sel)
        ttk.Button(bt, text="Cancelar", command=self.destroy).pack(side="right")
        ttk.Button(bt, text="Acrescentar", command=ok, style="Neutro.TButton").pack(side="right", padx=8)
        self.tv.bind("<Double-1>", lambda e: ok())
        self.bind("<Escape>", lambda e: self.destroy())
        _centraliza(self, aba.app.raiz)
        self.grab_set()
        e.focus_set()

    def _escolhe_modo(self, rotulo):
        # Marcar uma opção desmarca as outras; desmarcar a atual volta para "Todos"
        for r, v in self._caixas_modo.items():
            v.set(r == rotulo if self._caixas_modo[rotulo].get() else r == "Todos")
        self.filtro_modo.set(next(r for r, v in self._caixas_modo.items() if v.get()))
        self._preenche()

    def _preenche(self):
        self.tv.delete(*self.tv.get_children())
        t = self.busca.get().strip().casefold()
        escolhido = self.filtro_modo.get() if self.modo_de else "Todos"
        wanted = {"Analógicos": "Analógico", "Digitais": "Digital"}.get(escolhido)
        for n, nome, det in self.itens:
            if t and t not in f"{n} {nome} {det}".casefold():
                continue
            if wanted and self.modo_de(n) != wanted:
                continue
            self.tv.insert("", "end", iid=str(n), values=(n, nome, det))


def _liga_setas(tv, soltou):
    arrastar.liga_setas(tv, soltou)


class OrganizaLista(tk.Toplevel):
    """Muda a ordem de uma lista (contatos, grupos de RX, zonas, listas de varredura): arrastando,
    com os botões ▲ ▼ (ou Ctrl+↑ / Ctrl+↓) ou em ordem alfabética. ao_ok(ordem) aplica a nova ordem."""

    def __init__(self, aba, titulo, itens, ao_ok, nota):
        super().__init__(aba.app.raiz)
        self.title(titulo)
        self.transient(aba.app.raiz)
        self.ordem = [k for k, _ in itens]
        self.nomes = dict(itens)
        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text=nota, style="Suave.TLabel", wraplength=420, justify="left").pack(anchor="w", pady=(0, 8))
        meio = ttk.Frame(f)
        meio.pack(fill="both", expand=True)
        self.tv = ttk.Treeview(meio, columns=("pos", "nome"), show="headings", height=18, selectmode="extended")
        self.tv.heading("pos", text="Posição", anchor="w")
        self.tv.heading("nome", text="Nome", anchor="w")
        self.tv.column("pos", width=aba.app.largura_texto(7), anchor="w", stretch=False)
        self.tv.column("nome", width=aba.app.largura_texto(28), anchor="w")
        rol = ttk.Scrollbar(meio, orient="vertical", command=self.tv.yview)
        self.tv.configure(yscrollcommand=rol.set)
        self.tv.pack(side="left", fill="both", expand=True)
        rol.pack(side="left", fill="y")
        lado = ttk.Frame(meio)
        lado.pack(side="left", fill="y", padx=(8, 0))
        ttk.Button(lado, text="▲", width=4, command=lambda: self.sobe(-1)).pack(pady=(0, 4))
        ttk.Button(lado, text="▼", width=4, command=lambda: self.sobe(1)).pack(pady=(0, 12))
        ttk.Button(lado, text="A-Z", width=4, command=self.alfabetica).pack()
        arrastar.ArrastaLinhas(self.tv, self._soltou)
        self.tv.bind("<Control-Up>", lambda e: (self.sobe(-1), "break")[1])
        self.tv.bind("<Control-Down>", lambda e: (self.sobe(1), "break")[1])
        bt = ttk.Frame(f)
        bt.pack(fill="x", pady=(10, 0))

        def ok():
            self.destroy()
            ao_ok(list(self.ordem))
        ttk.Button(bt, text="Cancelar", command=self.destroy).pack(side="right")
        ttk.Button(bt, text="Aplicar", command=ok, style="Neutro.TButton").pack(side="right", padx=8)
        self.bind("<Escape>", lambda e: self.destroy())
        self._preenche()
        _centraliza(self, aba.app.raiz)
        self.grab_set()
        self.tv.focus_set()

    def _preenche(self, sel=()):
        self.tv.delete(*self.tv.get_children())
        for i, k in enumerate(self.ordem, start=1):
            self.tv.insert("", "end", iid=str(k), values=(i, self.nomes[k]))
        if sel:
            self.tv.selection_set([str(k) for k in sel])
            self.tv.see(str(sel[0]))
            self.tv.focus(str(sel[0]))

    def _soltou(self, sel, alvo, depois):
        sel = [int(x) for x in sel]
        self.ordem = arrastar.move_bloco(self.ordem, sel, int(alvo), depois)
        self._preenche(sel)

    def sobe(self, d):
        sel = [int(x) for x in self.tv.selection()]
        if not sel:
            return
        pos = sorted(self.ordem.index(k) for k in sel)
        if (d < 0 and pos[0] == 0) or (d > 0 and pos[-1] == len(self.ordem) - 1):
            return
        alvo = self.ordem[pos[0] - 1] if d < 0 else self.ordem[pos[-1] + 1]
        self.ordem = arrastar.move_bloco(self.ordem, sel, alvo, d > 0)
        self._preenche(sel)

    def alfabetica(self):
        self.ordem.sort(key=lambda k: self.nomes[k].casefold())
        self._preenche()


class AbaDMR:
    def __init__(self, app, pai):
        self.app, self.pai = app, pai
        self.cp = None
        self.caminho = None
        self.origem = ""
        self.modificado = False
        self.historico, self.pos_historico = [], -1
        self.salvo_estado = None
        self.copia = []

        barra = tema.barra_comandos(pai)
        # Como nos outros rádios: Ler rádio e Gravar no rádio (pelo cabo USB); os arquivos .rdt ficam no Arquivo
        tema.botao(barra, "Ler rádio", self.le_usb, "download", "TButton").pack(side="left", padx=(0, 8))
        tema.botao(barra, "Gravar no rádio", self.grava_usb, "upload", "Gravar.TButton").pack(
            side="left", padx=(0, 20))
        self.mb_arquivo = ttk.Menubutton(barra, text="Arquivo")
        m = tema.MenuDesenhado(app.raiz)
        m.add_command(label="Abrir arquivo .rdt...", command=self.abrir)
        m.add_command(label="Salvar", command=self.salvar)
        m.add_command(label="Salvar como...", command=self.salvar_como)
        m.add_separator()
        m.add_command(label="Exportar a lista de canais (PDF ou CSV)...", command=self.exportar)
        m.add_command(label="Exportar canais para planilha...", command=self.exportar_cps)
        m.add_command(label="Importar canais de planilha...", command=self.importar_cps)
        m.add_separator()
        m.add_command(label="Abrir a pasta de backups", command=self.app.abre_pasta_backup)
        m.add_separator()
        # O teste de conexão (diagnóstico do cabo e do driver) fica aqui; não há mais o botão Testes
        m.add_command(label="Testar a conexão com o rádio...", command=self.testa_usb)
        m.anexa(self.mb_arquivo)
        self.mb_arquivo.pack(side="left")
        tema.botoes_historico(barra, self.desfazer, self.refazer)
        self.info = tema.LinhaArquivo(pai)

        self.nb = ttk.Notebook(pai, style="Semabas.TNotebook")
        self.nb.pack(fill="both", expand=True)
        tema.titulo_do_caderno(pai, self.nb, app.fonte_titulo)
        self.f_canais = ttk.Frame(self.nb)
        self.f_zonas = ttk.Frame(self.nb)
        self.f_var = ttk.Frame(self.nb)
        self.f_cont = ttk.Frame(self.nb)
        self.f_grp = ttk.Frame(self.nb)
        self.f_msg = ttk.Frame(self.nb)
        self.f_ger = ttk.Frame(self.nb)
        self.f_menu = ttk.Frame(self.nb)
        self.f_bot = ttk.Frame(self.nb)
        self.f_priv = ttk.Frame(self.nb)
        self.f_emerg = ttk.Frame(self.nb)
        self.f_dtmf = ttk.Frame(self.nb)
        self.f_vfo = ttk.Frame(self.nb)
        self.f_gps = ttk.Frame(self.nb)
        # mesma sequência das telas do CPS da Retevis
        for fr, t in ((self.f_ger, "Geral"), (self.f_menu, "Menu"), (self.f_bot, "Botões"),
                      (self.f_msg, "Mensagens"), (self.f_priv, "Privacidade"), (self.f_emerg, "Emergência"),
                      (self.f_cont, "Contatos e TGs"), (self.f_grp, "Grupos de RX"), (self.f_zonas, "Zonas"),
                      (self.f_var, "Varredura"), (self.f_canais, "Canais"), (self.f_dtmf, "DTMF"),
                      (self.f_vfo, "VFO"), (self.f_gps, "GPS")):
            self.nb.add(fr, text=t)
        self._monta_canais()
        self._monta_zonas()
        self._monta_varreduras()
        self._monta_contatos()
        self._monta_grupos()
        self._monta_mensagens()
        self._monta_gerais()
        self.nb.select(self.f_canais)      # abre na aba mais usada
        self._atualiza_tudo()

    # ------------------------------------------------------------- comuns
    def _tabela(self, pai, colunas, ancora_esq=("nome", "contato", "det"), estica="contato", chave=None):
        meio = ttk.Frame(pai)
        meio.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        if not colunas or colunas[-1][0] != estica:
            # coluna vazia no fim absorve a sobra de largura, sem abrir espaço no meio da tabela
            colunas = list(colunas) + [("_sobra", "", 1)]
            estica = "_sobra"
        tv = ttk.Treeview(meio, columns=[c for c, _, _ in colunas], show="headings", selectmode="extended")
        for c, t, w in colunas:
            tv.heading(c, text=t, anchor="w" if c in ancora_esq else "center")
            tv.column(c, width=self.app.largura_texto(w), minwidth=self.app.largura_texto(w),
                      anchor="w" if c in ancora_esq else "center", stretch=c == estica)
        rol = ttk.Scrollbar(meio, orient="vertical", command=tv.yview)
        rolh = ttk.Scrollbar(meio, orient="horizontal", command=tv.xview)
        tv.configure(yscrollcommand=rol.set, xscrollcommand=tema.rolagem_automatica(rolh))
        tv.grid(row=0, column=0, sticky="nsew")
        rol.grid(row=0, column=1, sticky="ns")
        rolh.grid(row=1, column=0, sticky="ew")
        meio.rowconfigure(0, weight=1)
        meio.columnconfigure(0, weight=1)
        tema.configura_tags_tx(tv)
        if chave:
            tema.memoriza_colunas(tv, self.app.cfg, chave, self.app._salva_cfg)
        tv.bind("<Control-z>", lambda e: self.desfazer())
        tv.bind("<Control-y>", lambda e: self.refazer())
        tv._colunas = colunas
        return tv

    def ajusta_colunas(self):
        for tv in (self.tv, self.tvz, self.tvv, self.tvc, self.tvg, self.tvm):
            for c, _, w in tv._colunas:
                tv.column(c, width=self.app.largura_texto(w), minwidth=self.app.largura_texto(w))

    def _menu(self, tv, itens):
        m = tema.MenuDesenhado(self.app.raiz)
        for rot, fn in itens:
            if rot is None:
                m.add_separator()
            else:
                m.add_command(label=rot, command=fn)

        def abre(ev):
            if not self.cp:
                return
            linha = tv.identify_row(ev.y)
            if linha and linha not in tv.selection():
                tv.selection_set(linha)
            m.tk_popup(ev.x_root, ev.y_root)
        tv.bind("<Button-3>", abre)
        tv.bind("<Button-2>", abre)

    def _botoes(self, pai, itens):
        f = ttk.Frame(pai)
        f.pack(side="left")
        for t, fn in itens:
            ttk.Button(f, text=t, command=fn).pack(side="left", padx=(0, 6))
        return f

    @staticmethod
    def _valores(c):
        return (c["nome"], dm.mhz(c["rx"]), dm.mhz(c["tx"]) if c["tx"] != c["rx"] else "", c["modo"], c["cc"],
                c["slot"], c["contato"], c["tom_rx"], c["tom_tx"], c["potencia"])

    # ------------------------------------------------------------- canais
    def _monta_canais(self):
        topo = ttk.Frame(self.f_canais, padding=(16, 10, 16, 10))
        topo.pack(fill="x")
        self._topo = topo
        self.busca = tk.StringVar()
        campo, _ent = tema.campo_busca(topo, self.busca, "Buscar nome, número ou frequência")
        campo.pack(side="left")
        self.busca.trace_add("write", lambda *_: self._preenche())
        self.so_ocupados = tk.BooleanVar(value=True)
        ttk.Checkbutton(topo, text="Somente canais preenchidos", variable=self.so_ocupados,
                        command=self._preenche).pack(side="left", padx=14)
        tema.botao(topo, "Novo canal", self.novo_canal, "plus").pack(side="left", padx=(0, 8))
        mb = ttk.Menubutton(topo, text="Ordenar canais")
        mo = tema.MenuDesenhado(self.app.raiz)
        mo.add_command(label="Por nome (A a Z)", command=lambda: self.ordenar("nome"))
        mo.add_command(label="Por frequência", command=lambda: self.ordenar("frequencia"))
        mo.add_separator()
        mo.add_command(label="Analógicos e digitais separados, por nome", command=lambda: self.ordenar("nome", True))
        mo.add_command(label="Analógicos e digitais separados, por frequência",
                       command=lambda: self.ordenar("frequencia", True))
        mo.add_separator()
        mo.add_nota("Os canais vazios vão para o fim e os números são\n"
                    "refeitos a partir do 1. As zonas e as listas de\n"
                    "varredura continuam com os mesmos canais.\n"
                    "Para voltar, use Desfazer (↶).")
        mo.anexa(mb)
        mb.pack(side="left")
        ttk.Label(self.f_canais, text="Arraste um canal para mudar a ordem  ·  botão direito: mais opções",
                  style="Suave.TLabel").pack(side="bottom", anchor="w", padx=16, pady=(0, 8), before=topo)
        tema.fluxo(topo)
        self.tv = self._tabela(self.f_canais, COLUNAS, chave="dmr_canais")
        self.arraste = arrastar.ArrastaLinhas(
            self.tv, self._soltou, pode=lambda: bool(self.cp) and not self.busca.get().strip(),
            aviso=lambda: self.app.status.config(text="Para arrastar canais, limpe a busca (Esc)."))
        _liga_setas(self.tv, lambda sel, alvo, depois: (self._soltou(sel, alvo, depois)
                                                        if self.cp and not self.busca.get().strip() else None))
        self._menu(self.tv, [("Editar...", self.editar), ("Copiar", self.copiar), ("Colar", self.colar),
                             (None, None), ("Apagar", self.apagar)])
        self.tv.bind("<Double-1>", lambda e: self.editar())
        self.tv.bind("<Return>", lambda e: self.editar())
        self.tv.bind("<Delete>", lambda e: self.apagar())
        self.tv.bind("<Control-c>", lambda e: self.copiar())
        self.tv.bind("<Control-v>", lambda e: self.colar())
        self.aviso = tema.painel_inicial(self.f_canais, self.app.fonte_titulo, self.le_usb, self.abrir)

    def _preenche(self):
        sel = self.tv.selection()
        self.tv.delete(*self.tv.get_children())
        if not self.cp:
            return
        termo = self.busca.get().strip().casefold().replace(",", ".")
        for n in range(1, dm.TOTAL_CANAIS + 1):
            c = self.cp.canal(n)
            zebra = ("zebra",) if n % 2 == 0 else ()
            if c is None:
                if self.so_ocupados.get() or (termo and termo not in str(n)):
                    continue
                self.tv.insert("", "end", iid=str(n), values=(n, "(vazio)") + ("",) * 9, tags=("vazio",) + zebra)
                continue
            v = self._valores(c)
            if termo and termo not in f"{n} {v[0]} {v[1]} {v[2]}".casefold():
                continue
            self.tv.insert("", "end", iid=str(n), values=(n,) + v, tags=zebra)
        tema.zebra(self.tv)
        sel = [s for s in sel if self.tv.exists(s)]
        if sel:
            self.tv.selection_set(sel)

    def _sel(self, tv):
        return [int(i) for i in tv.selection()]

    def editar(self):
        if not self._exige():
            return
        sel = self._sel(self.tv)
        if not sel:
            messagebox.showinfo("Canais", "Selecione um canal na lista.")
            return
        EditorCanalDMR(self, sel[0])

    def novo_canal(self):
        if not self._exige():
            return
        sel = self._sel(self.tv)
        try:
            n = sel[0] if sel and not self.cp.usado(sel[0]) else self.cp.canal_livre(max(self.cp.usados() or [0]))
        except dm.ErroDMR as e:
            messagebox.showerror("Canais", str(e))
            return
        EditorCanalDMR(self, n)

    def apagar(self):
        if not self._exige():
            return
        sel = [n for n in self._sel(self.tv) if self.cp.usado(n)]
        if not sel:
            return
        zonas = {self.cp.nome_zona(z) for n in sel for z in self.cp.zonas_do_canal(n)}
        aviso = f"\n\nEle(s) também sai(em) das zonas: {', '.join(sorted(zonas))}." if zonas else ""
        if messagebox.askyesno("Canais", f"Apagar {len(sel)} canal(is)?{aviso}"):
            self.cp.apaga_canais(sel)
            self.alterado()

    def copiar(self):
        if self.cp:
            self.copia = [self.cp.bruto_canal(n) for n in self._sel(self.tv) if self.cp.usado(n)]
            self.app.status.config(text=f"{len(self.copia)} canal(is) copiado(s).")

    def colar(self):
        if not self.cp or not self.copia:
            return
        sel = self._sel(self.tv)
        inicio = min(sel) if sel else self.cp.canal_livre()
        alvo = list(range(inicio, inicio + len(self.copia)))
        if alvo[-1] > dm.TOTAL_CANAIS:
            messagebox.showinfo("Canais", "Os canais copiados não cabem a partir do canal selecionado.")
            return
        ocup = [n for n in alvo if self.cp.usado(n)]
        if ocup and not messagebox.askyesno("Canais", f"Substituir {len(ocup)} canal(is) já ocupado(s)?"):
            return
        for n, b in zip(alvo, self.copia):
            self.cp.poe_bruto_canal(n, b)
        self.alterado()

    def _soltou(self, sel, alvo, depois):
        nums = [int(i) for i in sel]
        mapa = self.cp.move(nums, int(alvo), depois)
        if not mapa:
            return
        self.alterado()
        novos = [str(mapa[n]) for n in nums if n in mapa and self.tv.exists(str(mapa[n]))]
        if novos:
            self.tv.selection_set(novos)
            self.tv.see(novos[0])
        self.app.status.config(text=f"{len(nums)} canal(is) movido(s) para a posição {mapa[nums[0]]}. "
                                    "Zonas e varreduras foram atualizadas. Desfazer (↶) volta.")

    def ordenar(self, por, por_modo=False):
        if not self._exige():
            return
        mapa = self.cp.ordena(por, por_modo)
        mudou = sum(1 for a, b in mapa.items() if a != b)
        self.alterado()
        self.tv.yview_moveto(0)
        criterio = ("nome" if por == "nome" else "frequência") + (", analógicos antes dos digitais" if por_modo else "")
        self.app.status.config(text=(f"Canais ordenados por {criterio}: "
                                     f"{mudou} mudaram de número; zonas e varreduras atualizadas."
                                     if mudou else "Os canais já estavam nessa ordem."))

    def _itens_canais(self):
        return [(n, self.cp.canal(n)["nome"], dm.mhz(self.cp.canal(n)["rx"])) for n in self.cp.usados()]

    # -------------------------------------------------------------- zonas
    def _monta_zonas(self):
        topo = ttk.Frame(self.f_zonas, padding=(16, 10, 16, 8))
        topo.pack(fill="x")
        self.zona = tk.StringVar()
        self.cb_zona = ttk.Combobox(topo, textvariable=self.zona, state="readonly", width=24)
        self.cb_zona.pack(side="left", padx=(0, 10))
        self.cb_zona.bind("<<ComboboxSelected>>", lambda e: self._preenche_zona())
        self._botoes(topo, [("Organizar zonas...", self.organiza_zonas), ("Nova zona", self.nova_zona),
                            ("Renomear", self.renomeia_zona),
                            ("Apagar zona", self.apaga_zona), ("Acrescentar canais...", self.acrescenta_zona)])
        linha = ttk.Frame(self.f_zonas, padding=(16, 0, 16, 6))    # segunda linha: lado A/B e ordem
        mb = ttk.Menubutton(linha, text="Ordenar a zona", width=15)
        mo = tema.MenuDesenhado(self.app.raiz)
        mo.add_command(label="Por nome (A a Z)", command=lambda: self.ordenar_zona("nome"))
        mo.add_command(label="Por frequência", command=lambda: self.ordenar_zona("frequencia"))
        mo.add_separator()
        mo.add_command(label="Analógicos e digitais separados, por nome",
                       command=lambda: self.ordenar_zona("nome", True))
        mo.add_command(label="Analógicos e digitais separados, por frequência",
                       command=lambda: self.ordenar_zona("frequencia", True))
        mo.add_separator()
        mo.add_nota("Muda só a ordem em que o rádio mostra os\n"
                    "canais desta zona; os números dos canais\n"
                    "não mudam.")
        mo.anexa(mb)
        # lados A e B da zona, independentes como no CPS (A: linha de cima do visor; B: de baixo)
        linha.pack(fill="x")
        self.lado_zona = tk.StringVar(value="A")
        for l in "AB":
            ttk.Radiobutton(linha, text=f"Lado {l}", value=l, variable=self.lado_zona,
                            command=self._preenche_zona).pack(side="left", padx=(0, 10))
        self._botoes(linha, [("Copiar para o outro lado", self.copia_lado_zona)])
        mb.pack(side="left")
        ttk.Label(linha, style="Suave.TLabel", text="Lado A: linha de cima do visor; lado B: linha de baixo."
                  ).pack(side="left", padx=(6, 0))
        ttk.Label(self.f_zonas, style="Suave.TLabel",
                  text="A ordem da lista é a ordem do botão de canais no rádio. Arraste para mudar; "
                       "botão direito para tirar da zona. Até 64 canais por lado."
                  ).pack(anchor="w", padx=8, pady=(0, 6))
        self.tvz = self._tabela(self.f_zonas, COL_ZONA)
        self.arraste_z = arrastar.ArrastaLinhas(self.tvz, self._soltou_zona, pode=lambda: bool(self.cp))
        _liga_setas(self.tvz, self._soltou_zona)
        self._menu(self.tvz, [("Editar o canal...", self._edita_da_zona), (None, None),
                              ("Tirar da zona", self.tira_da_zona)])
        self.tvz.bind("<Delete>", lambda e: self.tira_da_zona())
        self.tvz.bind("<Double-1>", lambda e: self._edita_da_zona())

    def _zona_atual(self):
        i = self.cb_zona.current()
        zs = self.cp.zonas() if self.cp else []
        return zs[i] if 0 <= i < len(zs) else (zs[0] if zs else None)

    def _preenche_zona(self):
        self.tvz.delete(*self.tvz.get_children())
        if not self.cp:
            return
        z = self._zona_atual()
        if z is None:
            return
        for k, n in enumerate(self.cp.membros(z, self.lado_zona.get()), start=1):
            c = self.cp.canal(n)
            if c is None:
                continue
            v = self._valores(c)
            self.tvz.insert("", "end", iid=f"{k}:{n}", values=(k, n, v[0], v[1], v[3], v[4], v[5], v[6]),
                            tags=("zebra",) if k % 2 == 0 else ())

    def _membros_sel(self):
        return [int(i.split(":")[1]) for i in self.tvz.selection()]

    def _edita_da_zona(self):
        sel = self._membros_sel()
        if sel:
            EditorCanalDMR(self, sel[0])

    def _soltou_zona(self, sel, alvo, depois):
        z = self._zona_atual()
        ordem = list(self.tvz.get_children())
        nova = arrastar.move_bloco(ordem, sel, alvo, depois)
        if nova == ordem:
            return
        self.cp.reordena_zona(z, [int(i.split(":")[1]) for i in nova], self.lado_zona.get())
        self.alterado()

    def ordenar_zona(self, por, por_modo=False):
        if not self._exige():
            return
        z = self._zona_atual()
        if z is not None:
            self.cp.ordena_zona(z, por, por_modo, self.lado_zona.get())
            self.alterado()

    def nova_zona(self):
        if not self._exige():
            return
        nome = simpledialog.askstring("Nova zona", "Nome da zona (até 16 letras):", parent=self.app.raiz)
        if not nome:
            return
        try:
            z = self.cp.cria_zona(nome)
        except dm.ErroDMR as e:
            messagebox.showerror("Zonas", str(e))
            return
        self.alterado()
        self.cb_zona.current(self.cp.zonas().index(z))
        self._preenche_zona()

    def renomeia_zona(self):
        z = self._zona_atual() if self.cp else None
        if z is None:
            return
        nome = simpledialog.askstring("Renomear zona", "Nome da zona (até 16 letras):",
                                      initialvalue=self.cp.nome_zona(z), parent=self.app.raiz)
        if nome:
            try:
                self.cp.renomeia_zona(z, nome)
            except dm.ErroDMR as e:
                messagebox.showerror("Zonas", str(e))
                return
            self.alterado()

    def apaga_zona(self):
        z = self._zona_atual() if self.cp else None
        if z is None:
            return
        if messagebox.askyesno("Zonas", f"Apagar a zona {self.cp.nome_zona(z)}? Os canais continuam existindo."):
            self.cp.apaga_zona(z)
            self.cp.reordena_zonas(self.cp.zonas())        # fecha o buraco na numeração
            self.alterado()

    def acrescenta_zona(self):
        z = self._zona_atual() if self.cp else None
        if z is None:
            messagebox.showinfo("Zonas", "Crie uma zona primeiro.")
            return
        lado = self.lado_zona.get()
        # Cada lado oferece os canais que ainda não estão nesse lado
        ja = set(self.cp.membros(z, lado))

        def ok(nums):
            try:
                self.cp.define_membros_zona(z, self.cp.membros(z, lado) + [n for n in nums if n not in ja], lado)
            except dm.ErroDMR as e:
                messagebox.showerror("Zonas", str(e))
                return
            self.alterado()
        EscolheItens(self, f"Acrescentar canais à zona {self.cp.nome_zona(z)}, lado {lado}",
                     [i for i in self._itens_canais() if i[0] not in ja], ok,
                     modo_de=lambda n: self.cp.canal(n)["modo"])

    def tira_da_zona(self):
        z = self._zona_atual() if self.cp else None
        sel = self._membros_sel()
        if z is None or not sel:
            return
        lado = self.lado_zona.get()
        self.cp.define_membros_zona(z, [n for n in self.cp.membros(z, lado) if n not in sel], lado)
        self.alterado()

    def copia_lado_zona(self):
        z = self._zona_atual() if self.cp else None
        if z is None:
            return
        de = self.lado_zona.get()
        para = "B" if de == "A" else "A"
        if self.cp.membros(z, para) and not messagebox.askyesno(
                "Zonas", f"Substituir a lista do lado {para} da zona {self.cp.nome_zona(z)} pela do lado {de}?"):
            return
        self.cp.copia_lado(z, de, para)
        self.alterado()

    # --------------------------------------------------- listas de varredura
    def _monta_lista_detalhe(self, fr, titulo_lista):
        """Lista de nomes à esquerda, detalhe à direita (varreduras e grupos de RX)."""
        esq = ttk.Frame(fr, padding=(16, 10, 16, 8))
        esq.pack(side="left", fill="y")
        ttk.Label(esq, text=titulo_lista, font=self.app.fonte_negrito).pack(anchor="w")
        lb = tk.Listbox(esq, width=24, height=20, exportselection=False, font="TkDefaultFont", relief="solid",
                        bd=1, highlightthickness=0, selectbackground=tema.C["selecao"],
                        selectforeground=tema.C["texto"], activestyle="none")
        lb.pack(fill="y", expand=True, pady=(4, 6))
        dir_ = ttk.Frame(fr, padding=(16, 10, 16, 8))
        dir_.pack(side="left", fill="both", expand=True)
        return esq, lb, dir_

    def _monta_varreduras(self):
        esq, self.lbv, dir_ = self._monta_lista_detalhe(self.f_var, "Listas")
        self._botoes(esq, [("Nova", self.nova_varredura), ("Apagar", self.apaga_varredura),
                           ("Organizar...", self.organiza_varreduras)]).pack(side="bottom", anchor="w", before=esq.winfo_children()[1])
        self.lbv.bind("<<ListboxSelect>>", lambda e: self._mostra_varredura())
        lin = ttk.Frame(dir_)
        lin.pack(fill="x")
        self.v_var = {k: tk.StringVar() for k in ("nome", "prio1", "prio2", "tx")}
        for i, (k, r) in enumerate((("nome", "Nome"), ("prio1", "Canal prioritário 1"),
                                    ("prio2", "Canal prioritário 2"), ("tx", "Canal de transmissão"))):
            ttk.Label(lin, text=r).grid(row=i // 2, column=(i % 2) * 2, sticky="w", padx=(0, 6), pady=3)
            w = ttk.Entry(lin, textvariable=self.v_var[k], width=20) if k == "nome" else \
                ttk.Combobox(lin, textvariable=self.v_var[k], state="readonly", width=24)
            w.grid(row=i // 2, column=(i % 2) * 2 + 1, sticky="w", padx=(0, 18), pady=3)
            if k != "nome":
                setattr(self, f"cb_var_{k}", w)
                w.bind("<<ComboboxSelected>>", lambda e: self._grava_varredura())
            else:
                w.bind("<FocusOut>", lambda e: self._grava_varredura())
                w.bind("<Return>", lambda e: self._grava_varredura())
        bts = ttk.Frame(dir_)
        bts.pack(fill="x", pady=(8, 6))
        self._botoes(bts, [("Acrescentar canais...", self.acrescenta_varredura), ("Tirar", self.tira_varredura)])
        ttk.Label(bts, text="Até 31 canais. Arraste para mudar a ordem.", style="Suave.TLabel").pack(side="right")
        self.tvv = self._tabela(dir_, COL_MEMB, estica="det")
        self.arraste_v = arrastar.ArrastaLinhas(self.tvv, self._soltou_var, pode=lambda: bool(self.cp))
        _liga_setas(self.tvv, self._soltou_var)
        self.tvv.bind("<Delete>", lambda e: self.tira_varredura())

    def _var_atual(self):
        s = self.lbv.curselection()
        vs = self.cp.varreduras() if self.cp else []
        return vs[s[0]] if s and s[0] < len(vs) else None

    def _opcoes_canais(self, especiais):
        return [especiais[k] for k in especiais] + [f"{n} - {self.cp.canal(n)['nome']}" for n in self.cp.usados()]

    @staticmethod
    def _rot_canal(cp, v, especiais):
        if v in especiais:
            return especiais[v]
        c = cp.canal(v)
        return f"{v} - {c['nome']}" if c else especiais.get(0xFFFF)

    @staticmethod
    def _num_canal(txt, especiais):
        for k, t in especiais.items():
            if t == txt:
                return k
        return int(txt.split(" - ")[0])

    def _preenche_varreduras(self):
        sel = self.lbv.curselection()
        self.lbv.delete(0, "end")
        if not self.cp:
            return
        for i in self.cp.varreduras():
            self.lbv.insert("end", f"{i}. {self.cp.varredura(i)['nome']}")
        if self.lbv.size():
            self.lbv.selection_set(min(sel[0] if sel else 0, self.lbv.size() - 1))
        self._mostra_varredura()

    def _mostra_varredura(self):
        self.tvv.delete(*self.tvv.get_children())
        i = self._var_atual()
        if i is None:
            for v in self.v_var.values():
                v.set("")
            return
        d = self.cp.varredura(i)
        self._carregando = True
        self.v_var["nome"].set(d["nome"])
        for k, esp in (("prio1", SEM_PRIO), ("prio2", SEM_PRIO), ("tx", SEM_TX)):
            getattr(self, f"cb_var_{k}")["values"] = self._opcoes_canais(esp)
            self.v_var[k].set(self._rot_canal(self.cp, d[k], esp))
        self._carregando = False
        for k, n in enumerate(d["membros"], start=1):
            c = self.cp.canal(n)
            if c:
                self.tvv.insert("", "end", iid=f"{k}:{n}", values=(k, n, c["nome"], dm.mhz(c["rx"])),
                                tags=("zebra",) if k % 2 == 0 else ())

    def _grava_varredura(self, membros=None):
        i = self._var_atual()
        if i is None or getattr(self, "_carregando", False):
            return
        d = self.cp.varredura(i)
        novo = dict(d, nome=self.v_var["nome"].get() or d["nome"],
                    prio1=self._num_canal(self.v_var["prio1"].get(), SEM_PRIO),
                    prio2=self._num_canal(self.v_var["prio2"].get(), SEM_PRIO),
                    tx=self._num_canal(self.v_var["tx"].get(), SEM_TX),
                    membros=d["membros"] if membros is None else membros)
        if novo == d:
            return
        try:
            self.cp.grava_varredura(i, novo)
        except dm.ErroDMR as e:
            messagebox.showerror("Listas de varredura", str(e))
            return
        self.alterado()

    def nova_varredura(self):
        if not self._exige():
            return
        nome = simpledialog.askstring("Nova lista de varredura", "Nome (até 16 letras):", parent=self.app.raiz)
        if not nome:
            return
        try:
            i = self.cp.varredura_livre()
            self.cp.grava_varredura(i, {"nome": nome, "prio1": 0xFFFF, "prio2": 0xFFFF, "tx": 0xFFFF,
                                        "membros": []})
        except dm.ErroDMR as e:
            messagebox.showerror("Listas de varredura", str(e))
            return
        self.alterado()
        self.lbv.selection_clear(0, "end")
        self.lbv.selection_set(self.cp.varreduras().index(i))
        self._mostra_varredura()

    def apaga_varredura(self):
        i = self._var_atual() if self.cp else None
        if i is None:
            return
        if messagebox.askyesno("Listas de varredura", f"Apagar a lista {self.cp.varredura(i)['nome']}? "
                                                      "Os canais que usavam esta lista ficam sem lista."):
            self.cp.apaga_varredura(i)
            self.cp.reordena_varreduras(self.cp.varreduras())
            self.alterado()

    def acrescenta_varredura(self):
        i = self._var_atual() if self.cp else None
        if i is None:
            return
        ja = set(self.cp.varredura(i)["membros"])
        EscolheItens(self, "Acrescentar canais à lista de varredura",
                     [x for x in self._itens_canais() if x[0] not in ja],
                     lambda nums: self._grava_varredura(self.cp.varredura(i)["membros"]
                                                        + [n for n in nums if n not in ja]))

    def tira_varredura(self):
        i = self._var_atual() if self.cp else None
        sel = [int(x.split(":")[1]) for x in self.tvv.selection()]
        if i is not None and sel:
            self._grava_varredura([n for n in self.cp.varredura(i)["membros"] if n not in sel])

    def _soltou_var(self, sel, alvo, depois):
        ordem = list(self.tvv.get_children())
        nova = arrastar.move_bloco(ordem, sel, alvo, depois)
        if nova != ordem:
            self._grava_varredura([int(x.split(":")[1]) for x in nova])

    # ------------------------------------------------------------- contatos
    def _monta_contatos(self):
        topo = ttk.Frame(self.f_cont, padding=(16, 10, 16, 8))
        topo.pack(fill="x")
        self.busca_c = tk.StringVar()
        ent = ttk.Entry(topo, textvariable=self.busca_c, width=30)
        ent.pack(side="left", padx=(0, 10))
        from programacao_ui import _dica_no_campo
        _dica_no_campo(ent, self.busca_c, "Buscar nome ou ID")
        self.busca_c.trace_add("write", lambda *_: self._preenche_contatos())
        self._botoes(topo, [("Organizar...", self.organiza_contatos), ("Novo contato", self.novo_contato),
                            ("Editar", self.edita_contato),
                            ("Apagar", self.apaga_contato),
                            ("Exportar...", self.exportar_contatos), ("Importar...", self.importar_contatos)])
        ttk.Label(topo, text="Grupo = talkgroup (TG); Privada = chamada para uma pessoa (ID DMR).",
                  style="Suave.TLabel").pack(side="right")
        self.tvc = self._tabela(self.f_cont, COL_CONT, estica="tom")
        self.tvc.bind("<Double-1>", lambda e: self.edita_contato())
        self.tvc.bind("<Delete>", lambda e: self.apaga_contato())

    def _preenche_contatos(self):
        self.tvc.delete(*self.tvc.get_children())
        if not self.cp:
            return
        t = self.busca_c.get().strip().casefold()
        for k, c in enumerate(self.cp.contatos()):
            if t and t not in f"{c['nome']} {c['id']}".casefold():
                continue
            self.tvc.insert("", "end", iid=str(c["numero"]), tags=("zebra",) if k % 2 else (),
                            values=(c["numero"], c["nome"], c["id"], c["tipo"], "Sim" if c["tom"] else ""))

    def _janela_contato(self, i, dados):
        j = tk.Toplevel(self.app.raiz)
        j.title("Contato")
        j.transient(self.app.raiz)
        j.resizable(False, False)
        f = ttk.Frame(j, padding=14)
        f.pack()
        v = {"nome": tk.StringVar(value=dados.get("nome", "")), "id": tk.StringVar(value=str(dados.get("id", ""))),
             "tipo": tk.StringVar(value=dados.get("tipo", "Grupo"))}
        tom = tk.BooleanVar(value=dados.get("tom", False))
        for r, (t, w) in enumerate((("Nome (até 16 letras)", ttk.Entry(f, textvariable=v["nome"], width=20)),
                                    ("ID (número do TG ou da pessoa)", ttk.Entry(f, textvariable=v["id"], width=12)),
                                    ("Tipo", ttk.Combobox(f, textvariable=v["tipo"], values=list(dm.TIPOS_CONTATO),
                                                          state="readonly", width=10)))):
            ttk.Label(f, text=t).grid(row=r, column=0, sticky="w", pady=3, padx=(0, 8))
            w.grid(row=r, column=1, sticky="w", pady=3)
        ttk.Checkbutton(f, text="Tocar o tom ao receber a chamada", variable=tom).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=3)

        def ok():
            try:
                self.cp.grava_contato(i, v["nome"].get(), int(v["id"].get() or 0), v["tipo"].get(), tom.get())
            except (dm.ErroDMR, ValueError) as e:
                messagebox.showerror("Contato", str(e) if isinstance(e, dm.ErroDMR) else "ID inválido.", parent=j)
                return
            j.destroy()
            self.alterado()
        bt = ttk.Frame(f)
        bt.grid(row=4, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(bt, text="Cancelar", command=j.destroy).pack(side="right")
        ttk.Button(bt, text="Salvar", command=ok, style="Neutro.TButton").pack(side="right", padx=8)
        j.bind("<Return>", lambda e: ok())
        j.bind("<Escape>", lambda e: j.destroy())
        _centraliza(j, self.app.raiz)
        j.grab_set()

    def novo_contato(self):
        if not self._exige():
            return
        try:
            i = self.cp.contato_livre()
        except dm.ErroDMR as e:
            messagebox.showerror("Contatos", str(e))
            return
        self._janela_contato(i, {})

    def edita_contato(self):
        sel = self._sel(self.tvc) if self.cp else []
        if sel:
            c = next(c for c in self.cp.contatos() if c["numero"] == sel[0])
            self._janela_contato(sel[0], c)

    def exportar_contatos(self):
        if not self._exige():
            return
        caminho = filedialog.asksaveasfilename(title="Exportar contatos para planilha", defaultextension=".csv",
                                               initialfile=f"Contatos_{self.app.modelo_radio}.csv",
                                               filetypes=[("Planilha (.csv)", "*.csv")])
        if caminho:
            n = dm.exporta_csv_contatos(self.cp, caminho)
            self.app.status.config(text=f"{n} contatos exportados.")

    def importar_contatos(self):
        if not self._exige():
            return
        caminho = filedialog.askopenfilename(title="Planilha de contatos",
                                             filetypes=[("Planilha (.csv)", "*.csv"), ("Todos", "*.*")])
        if not caminho:
            return
        if not messagebox.askyesno("Importar contatos", "Substituir os contatos atuais pelos da planilha?"):
            return
        try:
            n = dm.importa_csv_contatos(self.cp, caminho)
        except dm.ErroDMR as e:
            messagebox.showerror("Importar contatos", str(e))
            return
        self.alterado()
        self.app.status.config(text=f"{n} contatos importados da planilha.")

    def apaga_contato(self):
        sel = self._sel(self.tvc) if self.cp else []
        if sel and messagebox.askyesno("Contatos", f"Apagar {len(sel)} contato(s)? Canais e grupos de RX que "
                                                   "usavam esse(s) contato(s) ficam sem ele."):
            for i in sel:
                self.cp.apaga_contato(i)
            self.cp.reordena_contatos([c["numero"] for c in self.cp.contatos()])
            self.alterado()

    # ---------------------------------------------------------- grupos de RX
    def _monta_grupos(self):
        esq, self.lbg, dir_ = self._monta_lista_detalhe(self.f_grp, "Grupos de RX")
        self._botoes(esq, [("Novo", self.novo_grupo), ("Apagar", self.apaga_grupo),
                           ("Organizar...", self.organiza_grupos)]).pack(side="bottom", anchor="w", before=esq.winfo_children()[1])
        self.lbg.bind("<<ListboxSelect>>", lambda e: self._mostra_grupo())
        lin = ttk.Frame(dir_)
        lin.pack(fill="x")
        ttk.Label(lin, text="Nome").pack(side="left", padx=(0, 6))
        self.v_grp = tk.StringVar()
        e = ttk.Entry(lin, textvariable=self.v_grp, width=20)
        e.pack(side="left")
        e.bind("<FocusOut>", lambda ev: self._grava_grupo())
        e.bind("<Return>", lambda ev: self._grava_grupo())
        bts = ttk.Frame(dir_)
        bts.pack(fill="x", pady=(8, 6))
        self._botoes(bts, [("Acrescentar contatos...", self.acrescenta_grupo), ("Tirar", self.tira_grupo)])
        ttk.Label(bts, text="Até 32 contatos: os TGs que o rádio escuta neste canal.",
                  style="Suave.TLabel").pack(side="right")
        self.tvg = self._tabela(dir_, COL_MEMB, estica="det")
        self.arraste_g = arrastar.ArrastaLinhas(self.tvg, self._soltou_grupo, pode=lambda: bool(self.cp))
        _liga_setas(self.tvg, self._soltou_grupo)
        self.tvg.bind("<Delete>", lambda e: self.tira_grupo())

    def _grupo_atual(self):
        s = self.lbg.curselection()
        gs = self.cp.grupos() if self.cp else []
        return gs[s[0]] if s and s[0] < len(gs) else None

    def _preenche_grupos(self):
        sel = self.lbg.curselection()
        self.lbg.delete(0, "end")
        if not self.cp:
            return
        for g in self.cp.grupos():
            self.lbg.insert("end", f"{g}. {self.cp.nome_grupo(g)}")
        if self.lbg.size():
            self.lbg.selection_set(min(sel[0] if sel else 0, self.lbg.size() - 1))
        self._mostra_grupo()

    def _mostra_grupo(self):
        self.tvg.delete(*self.tvg.get_children())
        g = self._grupo_atual()
        if g is None:
            self.v_grp.set("")
            return
        d = self.cp.grupo(g)
        self.v_grp.set(d["nome"])
        cont = {c["numero"]: c for c in self.cp.contatos()}
        for k, i in enumerate(d["membros"], start=1):
            c = cont.get(i)
            if c:
                self.tvg.insert("", "end", iid=f"{k}:{i}", values=(k, i, c["nome"], c["id"]),
                                tags=("zebra",) if k % 2 == 0 else ())

    def _grava_grupo(self, membros=None):
        g = self._grupo_atual()
        if g is None:
            return
        d = self.cp.grupo(g)
        nome = self.v_grp.get().strip() or d["nome"]
        membros = d["membros"] if membros is None else membros
        if nome == d["nome"] and membros == d["membros"]:
            return
        try:
            self.cp.grava_grupo(g, nome, membros)
        except dm.ErroDMR as e:
            messagebox.showerror("Grupos de RX", str(e))
            return
        self.alterado()

    def novo_grupo(self):
        if not self._exige():
            return
        nome = simpledialog.askstring("Novo grupo de RX", "Nome (até 16 letras):", parent=self.app.raiz)
        if not nome:
            return
        try:
            g = self.cp.grupo_livre()
            self.cp.grava_grupo(g, nome, [])
        except dm.ErroDMR as e:
            messagebox.showerror("Grupos de RX", str(e))
            return
        self.alterado()
        self.lbg.selection_clear(0, "end")
        self.lbg.selection_set(self.cp.grupos().index(g))
        self._mostra_grupo()

    def apaga_grupo(self):
        g = self._grupo_atual() if self.cp else None
        if g is not None and messagebox.askyesno("Grupos de RX", f"Apagar o grupo {self.cp.nome_grupo(g)}? Os "
                                                                 "canais que o usavam ficam sem grupo de RX."):
            self.cp.apaga_grupo(g)
            self.cp.reordena_grupos(self.cp.grupos())
            self.alterado()

    def acrescenta_grupo(self):
        g = self._grupo_atual() if self.cp else None
        if g is None:
            return
        ja = set(self.cp.grupo(g)["membros"])
        itens = [(c["numero"], c["nome"], str(c["id"])) for c in self.cp.contatos()
                 if c["numero"] not in ja and c["tipo"] == "Grupo"]
        EscolheItens(self, "Acrescentar contatos ao grupo de RX", itens,
                     lambda nums: self._grava_grupo(self.cp.grupo(g)["membros"] + [n for n in nums if n not in ja]))

    def tira_grupo(self):
        g = self._grupo_atual() if self.cp else None
        sel = [int(x.split(":")[1]) for x in self.tvg.selection()]
        if g is not None and sel:
            self._grava_grupo([i for i in self.cp.grupo(g)["membros"] if i not in sel])

    def _soltou_grupo(self, sel, alvo, depois):
        ordem = list(self.tvg.get_children())
        nova = arrastar.move_bloco(ordem, sel, alvo, depois)
        if nova != ordem:
            self._grava_grupo([int(x.split(":")[1]) for x in nova])

    # ------------------------------------------------------------- mensagens
    def _monta_mensagens(self):
        ttk.Label(self.f_msg, style="Suave.TLabel",
                  text="Mensagens de texto prontas (até 144 caracteres). Duplo clique para editar.").pack(
            anchor="w", padx=8, pady=(10, 6))
        self.tvm = self._tabela(self.f_msg, [("num", "Nº", 5), ("texto", "Mensagem", 60)],
                                ancora_esq=("texto",), estica="texto")
        self.tvm.bind("<Double-1>", lambda e: self.edita_mensagem())
        self.tvm.bind("<Return>", lambda e: self.edita_mensagem())

    def _preenche_mensagens(self):
        self.tvm.delete(*self.tvm.get_children())
        if not self.cp:
            return
        for i in range(1, dm.TOTAL_MENSAGENS + 1):
            self.tvm.insert("", "end", iid=str(i), values=(i, self.cp.mensagem(i)),
                            tags=("zebra",) if i % 2 == 0 else ())

    def edita_mensagem(self):
        sel = self._sel(self.tvm) if self.cp else []
        if not sel:
            return
        i = sel[0]
        t = simpledialog.askstring("Mensagem", f"Mensagem {i} (até {dm.TAM_MENSAGEM} caracteres; vazio apaga):",
                                   initialvalue=self.cp.mensagem(i), parent=self.app.raiz)
        if t is None:
            return
        try:
            self.cp.grava_mensagem(i, t)
        except dm.ErroDMR as e:
            messagebox.showerror("Mensagem", str(e))
            return
        self.alterado()

    # ------------------------------------------------------------- ajustes gerais
    def _monta_gerais(self):
        self.v_ger, self.w_ger = {}, {}
        self._monta_painel(self.f_ger, dm.GRUPOS_GERAIS,
                           "Ajustes gerais do rádio. Cada mudança vale assim que você sai do campo. "
                           "Ajustes que o PYProg não mostra (senhas, anúncio de voz, preâmbulo salvo e outros) "
                           "são mantidos como estão no arquivo.")
        self._monta_painel(self.f_menu, dm.GRUPOS_MENU,
                           "Itens que aparecem no menu do rádio. Desmarque o que quiser "
                           "esconder.", colunas_bool=2)
        self._monta_painel(self.f_priv, dm.GRUPOS_PRIVACIDADE,
                           "Chaves de privacidade, usadas pelos canais digitais com "
                           "privacidade Básica ou Avançada. Básica: 4 dígitos; avançada: 32 dígitos, de 0 a 9 e "
                           "de A a F. Lembre que o serviço de radioamador não permite transmissões cifradas; use "
                           "a privacidade só onde a norma permitir.")
        self._monta_painel(self.f_emerg, dm.GRUPOS_EMERGENCIA,
                           "Emergência digital: ajustes gerais e os sistemas "
                           "de emergência que os canais digitais usam.", expande=False)
        self._monta_sistemas()
        self._monta_painel(self.f_dtmf, dm.GRUPOS_DTMF,
                           "Sistemas DTMF (aba System). Códigos: até 16 dígitos, de 0 a "
                           "9, A a D, * e #. Na decodificação, a confirmação (ACK) envia um dos códigos da lista Encode.")
        self._monta_painel(self.f_vfo, dm.GRUPOS_VFO,
                           "VFO A e VFO B: o canal que o rádio usa no modo frequência. "
                           "Use os botões abaixo para editar frequências, modo, potência, tons e os demais campos.",
                           expande=False)
        bt = ttk.Frame(self.f_vfo)
        bt.pack(anchor="w", padx=8, pady=8)
        for lado in "AB":
            ttk.Button(bt, text=f"Editar o VFO {lado}...", style="Neutro.TButton",
                       command=lambda l=lado: self._edita_vfo(l)).pack(side="left", padx=(0, 8))
        self.lbl_vfo = ttk.Label(self.f_vfo, style="Suave.TLabel", justify="left")
        self.lbl_vfo.pack(anchor="w", padx=8)
        self._monta_painel(self.f_gps, dm.GRUPOS_GPS,
                           "Sistemas de GPS, escolhidos em cada canal digital no campo "
                           "\"Sistema de GPS\": canal de retorno, intervalo de envio da posição e contato de destino.")
        self._monta_painel(self.f_bot, dm.GRUPOS_BOTOES,
                           "Funções dos botões laterais e contatos das teclas numéricas, e o acesso rápido (One Touch Access), que os botões chamam com a função "
                           "\"Acesso rápido 1\" a \"6\".")

    def _monta_painel(self, aba, grupos, texto, colunas_bool=1, expande=True):
        ttk.Label(aba, style="Suave.TLabel", wraplength=1100, justify="left", text=texto).pack(
            anchor="w", padx=8, pady=(10, 6))
        caixa = ttk.Frame(aba)
        caixa.pack(fill="both" if expande else "x", expand=expande, padx=4)
        tela = tk.Canvas(caixa, highlightthickness=0, bd=0, bg=tema.C["fundo"])
        rol = ttk.Scrollbar(caixa, orient="vertical", command=tela.yview)
        tela.configure(yscrollcommand=rol.set)
        rol.pack(side="right", fill="y")
        tela.pack(side="left", fill="both", expand=True)
        corpo = ttk.Frame(tela)
        tela.create_window(0, 0, window=corpo, anchor="nw")
        corpo.bind("<Configure>", lambda e: tela.configure(scrollregion=tela.bbox("all")))

        def roda(e):
            if tela.yview() != (0.0, 1.0):
                tela.yview_scroll(-1 if (e.delta > 0 or e.num == 4) else 1, "units")
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            tela.bind(ev, roda)
            corpo.bind(ev, roda)
        quadros = {}
        for i, g in enumerate(grupos):
            lf = ttk.LabelFrame(corpo, text=g.replace("Menu: ", "").capitalize() if g.startswith("Menu: ") else g,
                                padding=8)
            if g.startswith("Acesso rápido"):
                lf.grid(row=i // 2 + 1, column=0, columnspan=2, sticky="nsew", padx=4, pady=(0, 8))
            else:
                lf.grid(row=i // 2, column=i % 2, sticky="nsew", padx=4, pady=(0, 8))
            quadros[g] = lf
        linha = {g: 0 for g in quadros}
        nbool = {g: 0 for g in quadros}
        for k, (rot, g, tipo, pos, extra) in dm.AJUSTES_GERAIS.items():
            if g not in quadros:
                continue
            lf = quadros[g]
            if tipo == "bool":
                v = tk.BooleanVar()
                w = ttk.Checkbutton(lf, text=rot, variable=v, command=lambda k=k: self._aplica_ajuste(k))
                c = nbool[g] % colunas_bool
                if c == 0:
                    r = linha[g]
                    linha[g] += 1
                else:
                    r = linha[g] - 1
                nbool[g] += 1
                w.grid(row=r, column=c * 2, columnspan=2, sticky="w", pady=3, padx=(0, 16))
            elif k[:3] in ("ota", "gps", "dec") and k[3:4].isdigit():   # tabelas: acesso rápido, GPS, decodificação
                pref = k[:3]
                i, campo = int(k[3:].split("_")[0]), k.split("_")[1]
                campos, titulos, largs = {
                    "ota": (["modo", "contato", "tipo", "msg"], ["Modo", "Contato", "Tipo de chamada", "Mensagem"],
                            (12, 24, 17, 20)),
                    "gps": (["canal", "intervalo", "destino"], ["Canal de retorno", "Intervalo", "Destino"],
                            (24, 12, 24)),
                    "dec": (["resp", "tipo", "id", "ack", "atraso"], ["Resposta", "Tipo", "Código DTMF",
                                                                      "Confirmação (ACK)", "Atraso da confirmação"],
                            (20, 18, 18, 14, 14))}[pref]
                col = campos.index(campo)
                if i == 1 and col == 0:
                    ttk.Label(lf, text="Nº").grid(row=0, column=0, sticky="w", padx=(0, 8))
                    for c, t in enumerate(titulos):
                        ttk.Label(lf, text=t).grid(row=0, column=c + 1, sticky="w", padx=(0, 6))
                if col == 0:
                    ttk.Label(lf, text=str(i)).grid(row=i, column=0, sticky="w")
                v = tk.StringVar()
                if tipo == "dtmf":
                    w = ttk.Entry(lf, textvariable=v, width=largs[col])
                    w.bind("<FocusOut>", lambda e, k=k: self._aplica_ajuste(k))
                    w.bind("<Return>", lambda e, k=k: self._aplica_ajuste(k))
                else:
                    valores = list(extra.values()) if tipo == "op" else []
                    w = ttk.Combobox(lf, textvariable=v, values=valores, state="readonly", width=largs[col])
                    w.bind("<<ComboboxSelected>>", lambda e, k=k: self._aplica_ajuste(k))
                w.grid(row=i, column=col + 1, sticky="w", pady=3, padx=(0, 6))
            else:
                r = linha[g]
                linha[g] += 1
                nbool[g] = 0
                rotulo = rot + (f" ({extra[3]})" if tipo == "num" else "")
                ttk.Label(lf, text=rotulo).grid(row=r, column=0, sticky="w", pady=3, padx=(0, 8))
                v = tk.StringVar()
                if tipo in ("op", "cont", "msg", "canal"):
                    valores = list(extra.values()) if tipo == "op" else []
                    w = ttk.Combobox(lf, textvariable=v, values=valores, state="readonly",
                                     width=max(8, max(len(t) for t in valores) + 1) if valores else 24)
                    w.bind("<<ComboboxSelected>>", lambda e, k=k: self._aplica_ajuste(k))
                else:
                    larg = (pos[1] + 2 if tipo in ("txt", "dtmf", "senha_txt") else 2 * pos[1] + 2
                            if tipo in ("hex", "senha_bcd")
                            else 12 if tipo == "id" else 8)
                    w = ttk.Entry(lf, textvariable=v, width=larg)
                    w.bind("<FocusOut>", lambda e, k=k: self._aplica_ajuste(k))
                    w.bind("<Return>", lambda e, k=k: self._aplica_ajuste(k))
                w.grid(row=r, column=1, columnspan=3, sticky="w", pady=3)
            self.v_ger[k], self.w_ger[k] = v, w
        for lf in quadros.values():
            for w in [lf] + list(lf.winfo_children()):
                if not isinstance(w, ttk.Combobox):
                    for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                        w.bind(ev, roda, add="+")
        if not expande:
            corpo.update_idletasks()
            tela.configure(height=corpo.winfo_reqheight())

    def _edita_vfo(self, lado):
        if self._exige():
            EditorCanalDMR(self, lado)

    def _preenche_vfo(self):
        if not self.cp:
            self.lbl_vfo.config(text="")
            return
        linhas = []
        for lado in "AB":
            f = self.cp.campos_vfo(lado)
            tx = f" / TX {dm.mhz(f['tx'])}" if f["tx"] != f["rx"] else ""
            linhas.append(f"VFO {lado}: RX {dm.mhz(f['rx'])} MHz{tx}  ·  {f['modo']}  ·  potência {f['potencia']}")
        self.lbl_vfo.config(text="\n".join(linhas))

    # ------------------------------------------------------------- organizar listas
    _NOTA_ORG = ("Arraste as linhas, use ▲ ▼ (ou Ctrl+↑ / Ctrl+↓) ou A-Z. Ao aplicar, o PYProg atualiza tudo "
                 "o que aponta para {o}, como as fórmulas de uma planilha.")

    def _organiza(self, titulo, itens, fazer, o, nome):
        if not self._exige() or not itens:
            return

        def ok(ordem):
            mapa = fazer(ordem)
            self.alterado()
            mudou = sum(1 for a, b in mapa.items() if a != b)
            self.app.status.config(text=f"{nome}: {mudou} mudaram de posição; referências atualizadas. "
                                        "Desfazer (↶) volta.")
        OrganizaLista(self, titulo, itens, ok, self._NOTA_ORG.format(o=o))

    def organiza_contatos(self):
        self._organiza("Organizar contatos", [(c["numero"], f"{c['nome']} ({c['id']})") for c in self.cp.contatos()]
                       if self.cp else [], lambda o: self.cp.reordena_contatos(o),
                       "eles (canais, grupos de RX, teclas numéricas, acesso rápido e GPS)", "Contatos")

    def organiza_grupos(self):
        self._organiza("Organizar grupos de RX", [(g, self.cp.nome_grupo(g)) for g in self.cp.grupos()]
                       if self.cp else [], lambda o: self.cp.reordena_grupos(o), "eles (os canais)", "Grupos de RX")

    def organiza_varreduras(self):
        self._organiza("Organizar listas de varredura", [(i, self.cp.varredura(i)["nome"]) for i in self.cp.varreduras()]
                       if self.cp else [], lambda o: self.cp.reordena_varreduras(o), "elas (os canais)",
                       "Listas de varredura")

    def organiza_zonas(self):
        self._organiza("Organizar zonas", [(z, self.cp.nome_zona(z)) for z in self.cp.zonas()] if self.cp else [],
                       lambda o: self.cp.reordena_zonas(o), "elas", "Zonas")

    # ------------------------------------------------------------- sistemas de emergência
    def _monta_sistemas(self):
        lf = ttk.LabelFrame(self.f_emerg, text="Sistemas de emergência", padding=8)
        lf.pack(fill="both", expand=True, padx=8, pady=(4, 8))
        topo = ttk.Frame(lf)
        topo.pack(fill="x", pady=(0, 6))
        self._botoes(topo, [("Novo sistema", self.novo_sistema), ("Editar", self.edita_sistema),
                            ("Apagar", self.apaga_sistema)])
        self.tvs = self._tabela(lf, [("num", "Nº", 4), ("nome", "Nome", 16), ("tipo", "Tipo de alarme", 16),
                                     ("modo", "Modo", 22), ("imp", "Impolidas", 9), ("pol", "Polidas", 8),
                                     ("mic", "Microfone (s)", 11), ("canal", "Canal de retorno", 22)],
                                ancora_esq=("nome", "tipo", "modo", "canal"), estica="canal")
        self.tvs.bind("<Double-1>", lambda e: self.edita_sistema())

    def _nome_canal_num(self, n):
        c = self.cp.canal(n) if n else None
        return f"{n}: {c['nome']}" if c else ("Nenhum" if not n else f"(nº {n})")

    def _preenche_sistemas(self):
        self.tvs.delete(*self.tvs.get_children())
        if not self.cp:
            return
        for i in self.cp.sistemas():
            d = self.cp.sistema(i)
            self.tvs.insert("", "end", iid=str(i), values=(i, d["nome"], d["tipo"], d["modo"], d["impolido"],
                                                           d["polido"], d["microfone"],
                                                           self._nome_canal_num(d["canal"])))

    def _janela_sistema(self, i, d):
        j = tk.Toplevel(self.app.raiz)
        j.title(f"Sistema de emergência {i}")
        j.transient(self.app.raiz)
        j.resizable(False, False)
        f = ttk.Frame(j, padding=12)
        f.pack(fill="both", expand=True)
        digitais = [n for n in self.cp.usados() if self.cp.canal(n)["modo"] == "Digital"]
        canais = ["Nenhum"] + [self._nome_canal_num(n) for n in digitais]
        if d["canal"] and d["canal"] not in digitais:
            canais.append(self._nome_canal_num(d["canal"]))
        v = {"nome": tk.StringVar(value=d["nome"]), "tipo": tk.StringVar(value=d["tipo"]),
             "modo": tk.StringVar(value=d["modo"]), "impolido": tk.StringVar(value=str(d["impolido"])),
             "polido": tk.StringVar(value=str(d["polido"])), "microfone": tk.StringVar(value=str(d["microfone"])),
             "canal": tk.StringVar(value=self._nome_canal_num(d["canal"]))}
        linhas = [("Nome (até 16 letras)", ttk.Entry(f, textvariable=v["nome"], width=20)),
                  ("Tipo de alarme", ttk.Combobox(f, textvariable=v["tipo"], values=list(dm.TIPOS_ALARME.values()),
                                                  state="readonly", width=20)),
                  ("Modo", ttk.Combobox(f, textvariable=v["modo"], values=list(dm.MODOS_ALARME.values()),
                                        state="readonly", width=26)),
                  ("Tentativas impolidas", ttk.Combobox(f, textvariable=v["impolido"],
                                                        values=[str(x) for x in range(16)], width=6)),
                  ("Tentativas polidas", ttk.Combobox(f, textvariable=v["polido"],
                                                      values=[str(x) for x in range(16)], width=6)),
                  ("Microfone aberto (s)", ttk.Combobox(f, textvariable=v["microfone"],
                                                        values=[str(x) for x in range(0, 125, 5)], width=6)),
                  ("Canal de retorno (digital)", ttk.Combobox(f, textvariable=v["canal"], values=canais,
                                                              state="readonly", width=26))]
        for r, (rot, w) in enumerate(linhas):
            ttk.Label(f, text=rot).grid(row=r, column=0, sticky="w", pady=3, padx=(0, 8))
            w.grid(row=r, column=1, sticky="w", pady=3)
        bt = ttk.Frame(f)
        bt.grid(row=len(linhas), column=0, columnspan=2, sticky="e", pady=(10, 0))

        def ok():
            canal = v["canal"].get()
            try:
                num = 0 if canal == "Nenhum" else int(canal.split(":")[0].strip("(nº )"))
                self.cp.grava_sistema(i, {"nome": v["nome"].get(), "tipo": v["tipo"].get(), "modo": v["modo"].get(),
                                          "impolido": int(v["impolido"].get()), "polido": int(v["polido"].get()),
                                          "microfone": int(v["microfone"].get()), "canal": num})
            except (dm.ErroDMR, ValueError) as e:
                messagebox.showerror("Sistema de emergência", str(e), parent=j)
                return
            j.destroy()
            self.alterado()
        ttk.Button(bt, text="Cancelar", command=j.destroy).pack(side="right")
        ttk.Button(bt, text="Salvar", command=ok, style="Neutro.TButton").pack(side="right", padx=8)
        j.bind("<Escape>", lambda e: j.destroy())
        _centraliza(j, self.app.raiz)
        j.grab_set()

    def novo_sistema(self):
        if not self._exige():
            return
        try:
            i = self.cp.sistema_livre()
        except dm.ErroDMR as e:
            messagebox.showerror("Emergência", str(e))
            return
        self._janela_sistema(i, {"nome": f"System{i}", "tipo": "Normal", "modo": "Alarme", "impolido": 15,
                                 "polido": 5, "microfone": 10, "canal": 0})

    def edita_sistema(self):
        sel = self._sel(self.tvs) if self.cp else []
        if sel:
            self._janela_sistema(sel[0], self.cp.sistema(sel[0]))

    def apaga_sistema(self):
        sel = self._sel(self.tvs) if self.cp else []
        if not sel:
            return
        i = sel[0]
        if messagebox.askyesno("Emergência", f"Apagar o sistema {i} ({self.cp.sistema(i)['nome']})?\n\n"
                                             "Os canais que usavam esse sistema ficam sem sistema de emergência, e "
                                             "os sistemas seguintes sobem uma posição."):
            self.cp.apaga_sistema(i)
            self.alterado()

    def _nomes_lista(self, k):
        if dm.AJUSTES_GERAIS[k][2] == "canal":
            return [(0, "Canal atual")] + [(n, f"{n}: {self.cp.canal(n)['nome']}") for n in self.cp.usados()
                                           if self.cp.canal(n)["modo"] == "Digital"]
        if dm.AJUSTES_GERAIS[k][2] == "msg":
            out = [(0, "Nenhuma")]
            for i in range(1, dm.TOTAL_MENSAGENS + 1):
                t = self.cp.mensagem(i)
                if t:
                    out.append((i, f"{i}: {t[:24]}"))
            return out
        return self._nomes_contatos()

    def _nomes_contatos(self):
        return [(0, "Nenhum")] + [(c["numero"], f"{c['nome']} ({c['id']})") for c in self.cp.contatos()]

    def _preenche_gerais(self):
        estado = "normal" if self.cp else "disabled"
        for k, v in self.v_ger.items():
            w = self.w_ger[k]
            if isinstance(w, ttk.Combobox):
                w.configure(state="readonly" if self.cp else "disabled")
            else:
                w.configure(state=estado)
            if not self.cp:
                v.set(False if isinstance(v, tk.BooleanVar) else "")
                continue
            val = self.cp.ajuste(k)
            if dm.AJUSTES_GERAIS[k][2] in ("cont", "msg", "canal"):
                nomes = self._nomes_lista(k)
                if all(n != val for n, _ in nomes):
                    nomes.append((val, f"(nº {val}, vazio)"))
                w["values"] = [t for _, t in nomes]
                v.set(next(t for n, t in nomes if n == val))
                continue
            v.set(val if isinstance(v, tk.BooleanVar) else str(val))

    def _aplica_ajuste(self, k, avisa=True):
        """Grava um ajuste no arquivo aberto. Devolve False se o valor for inválido."""
        if not self.cp:
            return True
        v = self.v_ger[k]
        tipo = dm.AJUSTES_GERAIS[k][2]
        valor = v.get()
        if tipo in ("cont", "msg", "canal"):
            nomes = self._nomes_lista(k)
            valor = next((n for n, t in nomes if t == valor), self.cp.ajuste(k))
        if tipo in ("hex", "dtmf", "senha_txt", "senha_bcd") and valor.strip().upper() == self.cp.ajuste(k):
            return True
        if tipo in ("id", "num"):
            valor = valor.strip()
            if valor.isdigit() and int(valor) == self.cp.ajuste(k):
                return True
        try:
            mudou = self.cp.grava_ajuste(k, valor)
        except dm.ErroDMR as e:
            if avisa:
                messagebox.showerror("Programação", str(e))
            v.set(str(self.cp.ajuste(k)))
            return False
        if mudou:
            self.alterado()
        return True

    def _aplica_gerais(self):
        return all([self._aplica_ajuste(k) for k, w in self.w_ger.items() if isinstance(w, ttk.Entry)])

    # ------------------------------------------------------------- estado
    def _exige(self):
        if not self.cp:
            messagebox.showinfo("Programação", "Primeiro leia o rádio ou abra um arquivo .rdt.")
            return False
        return True

    def _atualiza_origem(self):
        if not self.cp:
            self.info.mostra("Nenhum arquivo aberto.")
            return
        self.info.mostra(self.origem, "  ·  ".join((tema.plural(len(self.cp.usados()), "canal", "canais"),
                                                    tema.plural(len(self.cp.zonas()), "zona", "zonas"),
                                                    tema.plural(len(self.cp.contatos()), "contato", "contatos"))), self.modificado, self.caminho or "")

    def _atualiza_zonas_combo(self):
        if not self.cp:
            self.cb_zona["values"] = []
            self.zona.set("")
            return
        i = max(0, self.cb_zona.current())
        nomes = [f"{self.cp.nome_zona(z)} ({len(self.cp.membros(z))} canais)" for z in self.cp.zonas()]
        self.cb_zona["values"] = nomes
        if nomes:
            self.cb_zona.current(min(i, len(nomes) - 1))
        else:
            self.zona.set("")

    def alterado(self):
        self._registra()
        self._atualiza_tudo()

    def _atualiza_tudo(self):
        tema.alterna_inicio(self.aviso, self._topo, self.tv.master, not self.cp)
        self._preenche()
        self._atualiza_zonas_combo()
        self._preenche_zona()
        self._preenche_varreduras()
        self._preenche_contatos()
        self._preenche_grupos()
        self._preenche_mensagens()
        self._preenche_gerais()
        self._preenche_sistemas()
        self._preenche_vfo()
        self._atualiza_origem()

    def _registra(self):
        dados = self.cp.imagem()
        if self.pos_historico < 0 or dados != self.historico[self.pos_historico]:
            self.historico = self.historico[:self.pos_historico + 1] + [dados]
            self.historico = self.historico[-(LIMITE_HISTORICO + 1):]
            self.pos_historico = len(self.historico) - 1
        self.modificado = dados != self.salvo_estado

    def _historico_move(self, d):
        if not self.cp:
            return
        destino = self.pos_historico + d
        if not 0 <= destino < len(self.historico):
            return
        self.pos_historico = destino
        self.cp.mem[:] = self.historico[destino]
        self.modificado = self.historico[destino] != self.salvo_estado
        self._atualiza_tudo()

    def desfazer(self):
        self._historico_move(-1)

    def refazer(self):
        self._historico_move(1)

    def carrega(self, cp, caminho, origem):
        self.cp, self.caminho, self.origem = cp, caminho, origem
        dados = cp.imagem()
        self.historico, self.pos_historico = [dados], 0
        self.salvo_estado = dados
        self.modificado = False
        self._atualiza_tudo()

    def _confirma_descartar(self):
        return (not self.modificado or messagebox.askyesno(
            "Programação", "Há alterações não salvas no arquivo aberto. Descartar?"))

    def arquivo_rascunho(self):
        return os.path.join(self.app.pasta_rascunhos(), f"Rascunho_programacao_{self.app.modelo_radio}.rdt")

    def salva_rascunho(self):
        if self.cp and self.modificado:
            self.cp.salva(self.arquivo_rascunho())

    def remove_rascunho(self):
        try:
            os.unlink(self.arquivo_rascunho())
        except FileNotFoundError:
            pass

    # ------------------------------------------------------------ arquivo
    # ---------------------------------------------------------- USB (experimental, só leitura)
    def _janela_relatorio(self, titulo, texto):
        j = tk.Toplevel(self.app.raiz)
        j.title(titulo)
        j.transient(self.app.raiz)
        caixa = tk.Text(j, width=96, height=20, wrap="word", font=("Consolas", 9))
        caixa.insert("1.0", texto)
        caixa.configure(state="disabled")
        caixa.pack(fill="both", expand=True, padx=12, pady=(12, 6))
        rod = ttk.Frame(j, padding=(12, 0, 12, 12))
        rod.pack(fill="x")

        def copia():
            j.clipboard_clear()
            j.clipboard_append(texto)
            self.app.status.config(text="Relatório copiado. Cole no e-mail ou na mensagem.")
        ttk.Button(rod, text="Copiar o relatório", command=copia).pack(side="left")
        ttk.Button(rod, text="Fechar", command=j.destroy).pack(side="right")

    def testa_usb(self):
        """Só lê: identifica o rádio e lê 1 KB da memória. Nada é gravado."""
        linhas = []

        def tarefa():
            import dmr_usb
            ok = dmr_usb.diagnostico(log=linhas.append)
            linhas.append("")
            linhas.append("RESULTADO: " + ("conexão funcionou." if ok else "não foi possível ler o rádio."))

        def fim():
            import vozes_core as vc
            self._janela_relatorio("Teste da conexão", f"PYProg {vc.VERSAO} | modelo escolhido: "
                                   f"{self.app.modelo_radio}\n\n" + "\n".join(linhas))
        self.app.executa("Testando a conexão...", tarefa, depois=fim)

    def le_usb(self):
        if not self._confirma_descartar():
            return
        res = {}

        def tarefa():
            import dmr_usb
            r, caminho = dmr_usb.conecta(log=lambda s: None)
            try:
                r.entra()
                res["id"] = r.identifica()
                if "1701" in res["id"]:
                    raise dm.ErroDMR("Este rádio é um Baofeng DM-1701, que ainda não é suportado pelo PYProg.")
                try:
                    res["info"] = r.bloco_info()
                except Exception:
                    res["info"] = None
                    r._ocioso()
                res["mem"] = r.le_tudo(lambda n, tot: self.app.progresso(
                    100 * n / tot, f"Lendo o rádio... {100 * n // tot}%"))
                r.reinicia()             # sai da tela de programação, como no fim da gravação
            finally:
                dmr_usb.solta(r)

        def fim():
            cp = dm.codeplug_do_radio(res["mem"], self.app.modelo_radio, None, res.get("info"))
            try:
                destino = os.path.join(self.app.pasta_backup(), f"Lido_{time.strftime('%Y-%m-%d_%H-%M-%S')}_"
                                                                f"{self.app.modelo_radio}.rdt")
                cp.salva(destino)
                copia = f"Backup automático: {os.path.basename(destino)}"
            except OSError as e:
                copia = f"Não foi possível guardar o backup: {e}"
            self.carrega(cp, None, f"Lido do rádio às {time.strftime('%H:%M')} ({res['id']})")
            self.app.status.config(text=f"Rádio lido. {copia}")
            import configuracao_radio as cr
            termos = cr.TERMOS_IDENT.get(self.app.modelo_radio, ())
            if termos and not any(t in res["id"].upper() for t in termos):
                messagebox.showwarning("Modelo diferente", f"O rádio respondeu como {res['id'] or 'sem identificação'}."
                                                           f"\n\nO modelo escolhido no topo é o {self.app.nome_radio()}. "
                                                           "Confira antes de editar ou gravar.")
        self.app.executa("Lendo o rádio...", tarefa, depois=fim)

    def grava_usb(self):
        """Grava a programação aberta no rádio pelo USB: apaga e grava as áreas da programação e reinicia o
        rádio. A cópia antes da gravação segue as Preferências."""
        if self.cp is None or self.cp.formato != "rdt":
            messagebox.showinfo("Gravar no rádio", "Leia o rádio ou abra um arquivo .rdt antes.")
            return
        com_backup = bool(self.app.cfg.get("backup_antes_gravar", False))
        modelo_arquivo = bytes(self.cp.cab[0x125:0x135]).split(b"\x00")[0].split(b"\xff")[0].decode("ascii", "replace")
        if not messagebox.askyesno(
                "Gravar no rádio", f"Gravar no {self.app.nome_radio()} a programação atual "
                                   f"({tema.plural(len(self.cp.usados()), 'canal', 'canais')} em uso)? "
                                   "Ela substitui a que está no rádio."):
            return
        alvo = bytes(self.cp.mem)
        res = {}

        def prog(ini, fim, rotulo):
            return lambda n, tot, txt=None: self.app.progresso(
                ini + (fim - ini) * n / tot, f"{txt or rotulo}... {int(100 * n / tot)}%")

        def tarefa():
            import dmr_usb
            r, caminho = dmr_usb.conecta(log=lambda s: None)
            try:
                r.entra()
                res["id"] = r.identifica()
                if modelo_arquivo.startswith("MD-") and res["id"] and res["id"] != modelo_arquivo:
                    raise dmr_usb.ErroUSB(f"O arquivo é de um {modelo_arquivo} e o rádio conectado é um "
                                          f"{res['id']}. Nada foi gravado.")
                ini_grava = 0
                if com_backup:
                    try:
                        info = r.bloco_info()
                    except Exception:
                        info, _ = None, r._ocioso()
                    ini_grava = 30
                    antes = r.le_tudo(prog(0, ini_grava, "Lendo o rádio (cópia de segurança)"))
                    copia = dm.codeplug_do_radio(antes, self.app.modelo_radio, None, info)
                    res["copia"] = os.path.join(self.app.pasta_backup(),
                                                f"Antes_gravar_{time.strftime('%Y-%m-%d_%H-%M-%S')}_"
                                                f"{self.app.modelo_radio}.rdt")
                    copia.salva(res["copia"])            # sem a cópia salva, não grava
                r.grava_tudo(alvo, prog(ini_grava, 100, "Gravando"))
                r.reinicia()
            finally:
                dmr_usb.solta(r)

        def fim():
            self.app.status.config(text="Programação gravada no rádio; ele foi reiniciado." + (
                f" Cópia de antes da gravação: {os.path.basename(res['copia'])}" if res.get("copia") else ""))
        self.app.executa("Gravando no rádio...", tarefa, depois=fim, nota=tema.NOTA_GRAVACAO)

    def abrir(self, caminho=None):
        if not self._confirma_descartar():
            return
        caminho = caminho or filedialog.askopenfilename(
            title="Abrir o arquivo do rádio", filetypes=[("Arquivo do rádio (.rdt)", "*.rdt"), ("Todos", "*.*")])
        if not caminho:
            return
        try:
            cp = dm.Codeplug.abre(caminho)
        except Exception as e:
            messagebox.showerror("Programação", str(e))
            return
        if cp.formato == "rdt" and bytes(cp.cab[0x125:0x12C]) == b"DM-1701":
            messagebox.showerror("Programação", "Este arquivo é de um Baofeng DM-1701, que ainda não é "
                                                "suportado pelo PYProg.")
            return
        try:
            destino = os.path.join(self.app.pasta_backup(), f"Original_{time.strftime('%Y-%m-%d_%H-%M-%S')}_"
                                                            f"{os.path.basename(caminho)}")
            shutil.copy2(caminho, destino)
        except OSError:
            pass
        self.carrega(cp, caminho, f"Arquivo: {os.path.basename(caminho)}")

    def _grava(self, caminho):
        try:
            self.cp.salva(caminho)
        except Exception as e:
            messagebox.showerror("Programação", f"Não foi possível salvar: {e}")
            return False
        self.caminho = caminho
        self.origem = f"Arquivo: {os.path.basename(caminho)}"
        self.salvo_estado = self.cp.imagem()
        self.modificado = False
        self.remove_rascunho()
        self._atualiza_origem()
        self.app.status.config(text=f"Arquivo salvo: {os.path.basename(caminho)}")
        return True

    def salvar(self):
        if not self._exige() or not self._aplica_gerais():
            return False
        if not self.caminho:
            return self.salvar_como()
        # sem pergunta: uma cópia do arquivo original ficou na pasta de backups quando ele foi aberto
        return self._grava(self.caminho)

    def salvar_como(self):
        if not self._exige() or not self._aplica_gerais():
            return False
        base = os.path.splitext(os.path.basename(self.caminho or "codeplug.rdt"))[0]
        caminho = filedialog.asksaveasfilename(
            title="Salvar o arquivo do rádio", defaultextension=".rdt", initialfile=f"{base}_editado.rdt",
            initialdir=os.path.dirname(self.caminho) if self.caminho else None,
            filetypes=[("Arquivo do rádio (.rdt)", "*.rdt")])
        return self._grava(caminho) if caminho else False

    def exportar_cps(self):
        if not self._exige():
            return
        caminho = filedialog.asksaveasfilename(title="Exportar canais para planilha", defaultextension=".csv",
                                               initialfile=f"Canais_{self.app.modelo_radio}.csv",
                                               filetypes=[("Planilha (.csv)", "*.csv")])
        if caminho:
            n = dm.exporta_csv_cps(self.cp, caminho)
            self.app.status.config(text=f"{n} canais exportados.")

    def importar_cps(self):
        if not self._exige():
            return
        caminho = filedialog.askopenfilename(title="Planilha de canais",
                                             filetypes=[("Planilha (.csv)", "*.csv"), ("Todos", "*.*")])
        if not caminho:
            return
        if not messagebox.askyesno("Importar canais", "Substituir os canais atuais pelos da planilha?"):
            return
        try:
            n = dm.importa_csv_cps(self.cp, caminho)
        except dm.ErroDMR as e:
            messagebox.showerror("Importar canais", str(e))
            return
        self.alterado()
        self.app.status.config(text=f"{n} canais importados da planilha.")

    def exportar(self):
        if not self._exige():
            return
        colunas = ["Nº", "Nome", "RX (MHz)", "TX (MHz)", "Modo", "CC", "Slot", "Contato", "Tom RX", "Tom TX",
                   "Potência"]
        zonas_de = {}
        for z in self.cp.zonas():
            for n in self.cp.membros(z):
                zonas_de.setdefault(n, []).append(self.cp.nome_zona(z))
        linhas = [[n] + list(self._valores(self.cp.canal(n))) + [", ".join(zonas_de.get(n, []))]
                  for n in self.cp.usados()]
        grupos = []
        for z in self.cp.zonas():
            g = [[k, n] + list(self._valores(self.cp.canal(n)))
                 for k, n in enumerate(self.cp.membros(z), start=1) if self.cp.canal(n)]
            grupos.append((f"Zona {self.cp.nome_zona(z)}", g))
        sem_zona = [["", n] + list(self._valores(self.cp.canal(n))) for n in self.cp.usados() if n not in zonas_de]
        if sem_zona:
            grupos.append(("Canais fora das zonas", sem_zona))
        sub = (cr.INDICATIVO + "  ·  " if cr.INDICATIVO else "") + self.origem
        exportar.exporta(self.app, f"Canais_{self.app.modelo_radio}{cr.sufixo_arquivo()}",
                         f"Canais do {self.app.nome_radio()}", sub, colunas + ["Zonas"], linhas,
                         grupos=grupos, colunas_grupos=["Posição", "Canal"] + colunas[1:])

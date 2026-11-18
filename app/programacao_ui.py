# -*- coding: utf-8 -*-
"""Aba "Programação": canais, zonas e ajustes do rádio."""
import os
import time
import copy

from arquivos import RegistroEnvio, assinatura
import tkinter as tk
import ajuda
from tkinter import filedialog, messagebox, ttk

import ajustes_uv5r as aj5
import arrastar
import configuracao_radio as cr
from chirp import settings as cs
import exportar
import programacao as pg
import tema

# Varredura e BCL ficam no formulário do canal (a lista cabe sem rolar para o lado)
COLUNAS = [("num", "Nº", 5), ("nome", "Nome", 17), ("rx", "RX (MHz)", 11), ("duplex", "Duplex", 9),
           ("offset", "Offset/TX", 10), ("tomtx", "Tom TX", 9), ("tomrx", "Tom RX", 9),
           ("pot", "Potência", 8), ("modo", "Modo", 6), ("txst", "TX", 19)]
COL_TX = "#" + str([c for c, _, _ in COLUNAS].index("txst") + 1)


def _dica(widget, texto):
    """Dica curta ao parar o mouse (mesma do cabeçalho)."""
    tema.dica_ao_parar(widget, texto)


def _dica_no_campo(entrada, var, texto):
    """Exemplo de preenchimento em cinza dentro do campo vazio. Fica num rótulo por cima,
    então o valor do campo continua vazio de verdade."""
    lbl = tk.Label(entrada, text=texto, fg=tema.C["exemplo"], bg=tema.C["campo"], font="TkTextFont", cursor="xterm", bd=0)

    def atualiza(*_):
        if var.get() or entrada.focus_get() is entrada:
            lbl.place_forget()
        else:
            lbl.place(x=5, rely=0.5, anchor="w")
    lbl.bind("<Button-1>", lambda e: entrada.focus_set())
    entrada.bind("<FocusIn>", atualiza, add="+")
    entrada.bind("<FocusOut>", atualiza, add="+")
    var.trace_add("write", atualiza)
    entrada.after_idle(atualiza)


class EditorCanal(tk.Toplevel):
    def __init__(self, aba, canal: pg.Canal):
        super().__init__(aba.app.raiz)
        self.aba, self.base = aba, canal
        p = canal.p
        self.title(f"Canal {canal.rotulo}" + (f" (zona {canal.zona})" if p.tem_zonas else f" ({p.nome})"))
        self.transient(aba.app.raiz)
        self.resizable(False, False)
        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)
        c = canal if not canal.vazio else pg.Canal(numero=canal.numero, vazio=False, bruto=canal.bruto,
                                                   perfil=canal.perfil)
        self.v = {
            "nome": tk.StringVar(value=c.nome),
            "rx": tk.StringVar(value=pg.mhz(c.rx)),
            "duplex": tk.StringVar(value=c.duplex),
            "offset": tk.StringVar(value=pg.mhz(c.offset) if c.duplex in ("+", "-", "TX separado") else ""),
            "tomtx": tk.StringVar(value=c.tom_tx),
            "tomrx": tk.StringVar(value=c.tom_rx),
            "pot": tk.StringVar(value=c.potencia),
            "larg": tk.StringVar(value=c.largura),
            "pttid": tk.StringVar(value=c.pttid),
            "scode": tk.StringVar(value=c.scode),
        }
        self.varr = tk.BooleanVar(value=c.varredura)
        self.bcl = tk.BooleanVar(value=c.bcl)
        linhas = [
            (f"Nome (até {p.nome_max} letras, sem acento)", ttk.Entry(f, textvariable=self.v["nome"], width=16)),
            ("Frequência de recepção RX (MHz)", ttk.Entry(f, textvariable=self.v["rx"], width=16)),
            ("Duplex", ttk.Combobox(f, textvariable=self.v["duplex"], values=pg.DUPLEX, state="readonly", width=14)),
            ("Offset (MHz) ou frequência de TX", ttk.Entry(f, textvariable=self.v["offset"], width=16)),
            ("Tom de transmissão (TX)", ttk.Combobox(f, textvariable=self.v["tomtx"], values=pg.OPCOES_TOM, width=14)),
            ("Tom de recepção (RX)", ttk.Combobox(f, textvariable=self.v["tomrx"], values=pg.OPCOES_TOM, width=14)),
            ("Potência", ttk.Combobox(f, textvariable=self.v["pot"], values=pg.POTENCIAS, state="readonly", width=14)),
            ("Largura de banda", ttk.Combobox(f, textvariable=self.v["larg"], values=pg.LARGURAS, state="readonly", width=14)),
            ("PTT-ID", ttk.Combobox(f, textvariable=self.v["pttid"], values=pg.PTTID, state="readonly", width=14)),
            ("Código S-Code (DTMF)", ttk.Combobox(f, textvariable=self.v["scode"], values=p.scodes, state="readonly", width=14)),
        ]
        chaves_ajuda = ["nome", "rx", "duplex", "offset", "tomtx", "tomrx", "pot", "larg", "pttid", "scode"]
        for i, (rot, w) in enumerate(linhas):
            ttk.Label(f, text=rot).grid(row=i, column=0, sticky="w", pady=3, padx=(0, 10))
            w.grid(row=i, column=1, sticky="w", pady=3)
            ajuda.botao(f, chaves_ajuda[i]).grid(row=i, column=3, padx=(6, 0))
        linhas[2][1].bind("<<ComboboxSelected>>", self._sugere_offset)
        ttk.Button(f, text="RX = TX", width=8, command=lambda: self.v["tomrx"].set(self.v["tomtx"].get())
                   ).grid(row=5, column=2, padx=6)
        n = len(linhas)
        op_varr = ttk.Frame(f)
        op_varr.grid(row=n, column=0, sticky="w", pady=3)
        ttk.Checkbutton(op_varr, text="Incluir na varredura", variable=self.varr).pack(side="left")
        ajuda.botao(op_varr, "varredura").pack(side="left", padx=4)
        op_bcl = ttk.Frame(f)
        op_bcl.grid(row=n, column=1, columnspan=3, sticky="w", pady=3)
        ttk.Checkbutton(op_bcl, text="Bloquear TX com canal ocupado (BCL)", variable=self.bcl).pack(side="left")
        ajuda.botao(op_bcl, "bcl").pack(side="left", padx=4)
        ttk.Label(f, text="Duplex: + ou - usam o offset (ex.: 0.600 em VHF, 5.000 em UHF). "
                          "\"TX separado\" usa o campo como frequência de TX.",
                  style="Suave.TLabel", wraplength=430).grid(row=n + 1, column=0, columnspan=3, sticky="w", pady=(8, 4))
        bt = ttk.Frame(f)
        bt.grid(row=n + 2, column=0, columnspan=3, pady=(8, 0), sticky="e")
        ttk.Button(bt, text="Apagar canal", command=self.apagar).pack(side="left", padx=4)
        ttk.Button(bt, text="Cancelar", command=self.destroy).pack(side="left", padx=4)
        ttk.Button(bt, text="Salvar", command=self.salvar).pack(side="left", padx=4)
        self.bind("<Return>", lambda e: self.salvar())
        self.bind("<Escape>", lambda e: self.destroy())
        _dica_no_campo(linhas[1][1], self.v["rx"], "000.000")
        _dica_no_campo(linhas[3][1], self.v["offset"], "0.000")
        linhas[0][1].focus_set()
        self.update_idletasks()
        r = aba.app.raiz
        x = r.winfo_rootx() + (r.winfo_width() - self.winfo_reqwidth()) // 2
        y = r.winfo_rooty() + (r.winfo_height() - self.winfo_reqheight()) // 3
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
        self.grab_set()

    def _sugere_offset(self, *_):
        d = self.v["duplex"].get()
        if d in ("+", "-") and not self.v["offset"].get().strip():
            try:
                f = pg.le_mhz(self.v["rx"].get()) / 1e6
            except Exception:
                return
            self.v["offset"].set("0.600" if f < 300 else "5.000")

    def salvar(self):
        try:
            c = pg.Canal(numero=self.base.numero, vazio=False, bruto=self.base.bruto, perfil=self.base.perfil)
            c.nome = self.v["nome"].get().strip().upper()[:c.p.nome_max]
            c.rx = pg.le_mhz(self.v["rx"].get())
            c.duplex = self.v["duplex"].get()
            off = self.v["offset"].get().strip()
            if c.duplex in ("+", "-", "TX separado"):
                if not off:
                    raise pg.ErroProgramacao("Informe o offset ou a frequência de TX.")
                c.offset = pg.le_mhz(off)
            c.tom_tx = pg.decodifica_tom(pg.codifica_tom(self.v["tomtx"].get()))
            c.tom_rx = pg.decodifica_tom(pg.codifica_tom(self.v["tomrx"].get()))
            c.potencia, c.largura = self.v["pot"].get(), self.v["larg"].get()
            c.pttid, c.scode = self.v["pttid"].get(), self.v["scode"].get()
            c.varredura, c.bcl = self.varr.get(), self.bcl.get()
            c.valida()
            aba = self.aba
            if (aba.bloqueio_auto() and c.tx is not None and not pg.dentro_das_faixas(c.tx, aba.faixas())
                    and pg.chave_excecao(c) not in aba.excecoes()):
                r = messagebox.askyesnocancel(
                    "Canal", f"O TX deste canal ({pg.mhz(c.tx)} MHz) está fora das faixas liberadas.\n\n"
                             "Sim: bloquear o TX (canal só para recepção).\n"
                             "Não: liberar o TX neste canal (exceção, ex.: frequência comercial).\n"
                             "Cancelar: voltar ao formulário.", parent=self)
                if r is None:
                    return
                if r:
                    aba.prog.tx_bloqueados[c.numero] = {"rx": c.rx, "duplex": c.duplex, "offset": c.offset}
                    c.duplex, c.offset = "Sem TX", 0
                else:
                    exc = aba.excecoes()
                    exc.add(pg.chave_excecao(c))
                    aba.salva_excecoes(exc)
            self.aba.prog.define_canal(c)
            self.aba.salva_bloqueados()
        except Exception as e:
            messagebox.showerror("Canal", str(e), parent=self)
            return
        self.aba.alterado()
        self.destroy()

    def apagar(self):
        self.aba.prog.apaga(self.base.numero)
        self.aba.alterado()
        self.destroy()


class AbaProgramacao:
    def __init__(self, app, pai):
        self.app, self.pai = app, pai
        self.prog = None
        self.chave = None
        self.origem = ""
        self.modificado = False
        self.copia = None
        self.vars_ajuste = {}
        self.historico, self.pos_historico = [], -1
        self.base_gravacao = None
        self.salvo_estado = None

        barra = tema.barra_comandos(pai)
        # Só as duas ações principais têm cor; ícone e rótulo distinguem leitura de gravação
        self.bt_ler = tema.botao(barra, "Ler rádio", self.ler, "download", "TButton")
        self.bt_ler.pack(side="left", padx=(0, 8))
        self.bt_gravar = tema.botao(barra, "Gravar no rádio", self.gravar, "upload", "Gravar.TButton")
        self.bt_gravar.pack(side="left", padx=(0, 20))
        app.botoes_ocupado += [self.bt_ler, self.bt_gravar]
        self.mb_arquivo = ttk.Menubutton(barra, text="Arquivo", width=9)
        menu = tema.MenuDesenhado(app.raiz)
        menu.add_command(label="Fazer backup (.img)...", command=self.salvar)
        menu.add_command(label="Restaurar backup (.img)...", command=self.abrir)
        menu.add_separator()
        menu.add_command(label="Exportar a lista de canais (PDF ou CSV)...", command=self.exportar)
        menu.add_separator()
        menu.add_command(label="Abrir a pasta de backups", command=self.app.abre_pasta_backup)
        menu.anexa(self.mb_arquivo)
        self.mb_arquivo.pack(side="left")
        app.botoes_ocupado.append(self.mb_arquivo)
        app.botoes_ocupado += tema.botoes_historico(barra, self.desfazer, self.refazer)
        self.bt_bloqueio = ttk.Button(barra, text="Bloqueio de TX...", command=self.janela_bloqueio)
        if self.controle():
            self.bt_bloqueio.pack(side="right")
        self.info = tema.LinhaArquivo(pai)
        self.caminho = ""

        self.nb = ttk.Notebook(pai, style="Semabas.TNotebook")
        self.nb.pack(fill="both", expand=True)
        tema.titulo_do_caderno(pai, self.nb, app.fonte_titulo)
        self.f_canais = ttk.Frame(self.nb)
        self.f_zonas = ttk.Frame(self.nb)
        self.f_ajustes = ttk.Frame(self.nb)
        self.f_dtmf = ttk.Frame(self.nb)
        self.nb.add(self.f_canais, text="Canais")
        self.nb.add(self.f_zonas, text="Zonas")
        self.nb.add(self.f_ajustes, text="Ajustes do rádio")
        self.nb.add(self.f_dtmf, text="DTMF")
        self._dtmf_atual = None
        self._monta_canais()
        self._atualiza_tudo()

    # ------------------------------------------------------------------ canais
    def _monta_canais(self):
        # Uma linha só: zona, busca, filtro e canal novo
        topo = ttk.Frame(self.f_canais, padding=(16, 10, 16, 10))
        topo.pack(fill="x")
        self._topo = topo
        self.zona = tk.StringVar()
        self.cb_zona = ttk.Combobox(topo, textvariable=self.zona, state="readonly", width=32, style="Alto.TCombobox")
        self.cb_zona.pack(side="left")
        self.cb_zona.bind("<<ComboboxSelected>>", lambda e: self._preenche_tabela())
        self.busca = tk.StringVar()
        campo, _ent = tema.campo_busca(topo, self.busca, "Buscar nome, número ou frequência", 30)
        campo.pack(side="left", padx=(12, 0))
        self.busca.trace_add("write", lambda *_: self._preenche_tabela())
        self.so_ocupados = tk.BooleanVar(value=False)
        ttk.Checkbutton(topo, text="Somente canais preenchidos", variable=self.so_ocupados,
                        command=self._preenche_tabela).pack(side="left", padx=14)
        b = tema.botao(topo, "Novo canal", self.novo_canal, "plus")
        b.pack(side="left")
        self.app.botoes_ocupado.append(b)
        ttk.Label(self.f_canais, text="Arraste um canal para mudar a ordem  ·  botão direito: mais opções",
                  style="Suave.TLabel").pack(side="bottom", anchor="w", padx=16, pady=(0, 8), before=topo)
        tema.fluxo(topo)
        meio = ttk.Frame(self.f_canais)
        meio.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        # coluna vazia no fim absorve a sobra de largura: assim a coluna TX não se estende até a borda
        # e um clique na parte vazia da linha só seleciona o canal, sem bloquear ou liberar o TX
        self.tv = ttk.Treeview(meio, columns=[c for c, _, _ in COLUNAS] + ["_sobra"], show="headings",
                               selectmode="extended")
        for c, t, w in COLUNAS:
            self.tv.heading(c, text=t, anchor="w" if c in ("nome", "txst") else "center")
            self.tv.column(c, width=self.app.largura_texto(w), minwidth=self.app.largura_texto(w),
                           anchor="w" if c in ("nome", "txst") else "center", stretch=False)
        self.tv.heading("_sobra", text="")
        self.tv.column("_sobra", width=1, minwidth=1, stretch=True)
        rol = ttk.Scrollbar(meio, orient="vertical", command=self.tv.yview)
        rolh = ttk.Scrollbar(meio, orient="horizontal", command=self.tv.xview)
        self.tv.configure(yscrollcommand=rol.set, xscrollcommand=tema.rolagem_automatica(rolh))
        self.tv.grid(row=0, column=0, sticky="nsew")
        rol.grid(row=0, column=1, sticky="ns")
        rolh.grid(row=1, column=0, sticky="ew")
        meio.rowconfigure(0, weight=1)
        meio.columnconfigure(0, weight=1)
        tema.configura_tags_tx(self.tv)
        self.arraste = arrastar.ArrastaLinhas(self.tv, self._soltou, pode=self._pode_arrastar,
                                              aviso=self._aviso_arraste)
        arrastar.liga_setas(self.tv, self._soltou, pode=self._pode_arrastar)
        tema.memoriza_colunas(self.tv, self.app.cfg, "baofeng", self.app._salva_cfg)
        self.legenda = tema.legenda_tx(self.f_canais, "TkDefaultFont")
        if self.controle():
            self.legenda.pack(side="bottom", fill="x", padx=16, pady=(0, 6), before=self._topo)
        # Menu do botão direito (Button-2 no macOS)
        self.menu_canal = tema.MenuDesenhado(self.app.raiz)
        for rot, fn in [("Editar...", self.editar), ("Copiar", self.copiar), ("Colar", self.colar), (None, None),
                        ("Bloquear TX", lambda: self.tx_selecionados(False)),
                        ("Liberar TX", lambda: self.tx_selecionados(True)), (None, None), ("Apagar", self.apagar)]:
            if rot is None:
                self.menu_canal.add_separator()
            else:
                self.menu_canal.add_command(label=rot, command=fn)
        for botao in ("<Button-3>", "<Button-2>"):
            self.tv.bind(botao, self._menu_canal)
        self.tv.bind("<Double-1>", lambda e: self.editar())
        self.tv.bind("<Return>", lambda e: self.editar())
        self.tv.bind("<Delete>", lambda e: self.apagar())
        self.tv.bind("<Control-c>", lambda e: self.copiar())
        self.tv.bind("<Control-v>", lambda e: self.colar())
        self.tv.bind("<Control-z>", lambda e: self.desfazer())
        self.tv.bind("<Control-y>", lambda e: self.refazer())
        self.aviso = tema.painel_inicial(self.f_canais, self.app.fonte_titulo, self.ler, self.abrir)
        self.app.botoes_ocupado += list(self.aviso.botoes)

    def novo_canal(self):
        """Abre o editor no canal vazio selecionado ou, sem um, no primeiro vazio da zona em exibição."""
        if not self._exige_prog():
            return
        sel = [n for n in self._selecionados() if self.prog.canal(n).vazio]
        if sel:
            n = sel[0]
        else:
            z, por = max(0, self.cb_zona.current()), self.prog.perfil.canais_por_zona
            vazios = [c.numero for c in self.prog.canais[z * por:(z + 1) * por] if c.vazio]
            if not vazios:
                messagebox.showinfo("Canais", "Não há canal vazio nesta lista. Apague um canal ou escolha outra zona.")
                return
            n = vazios[0]
        EditorCanal(self, self.prog.canal(n))

    def _menu_canal(self, ev):
        if not self.prog or self.app.ocupado:
            return
        linha = self.tv.identify_row(ev.y)
        if linha and linha not in self.tv.selection():
            self.tv.selection_set(linha)
        self.tv.focus_set()
        self.menu_canal.tk_popup(ev.x_root, ev.y_root)

    def _rotulos_zona(self):
        if self.prog and not self.prog.perfil.tem_zonas:
            p = self.prog.perfil
            return [f"Todos os canais ({p.rotulo(1)} a {p.rotulo(p.total_canais)}, {self.prog.usados()} em uso)"]
        out = []
        for z in range(pg.TOTAL_ZONAS):
            nome = pg.le_nome_zona(self.prog.img, z) if self.prog else ""
            ini = z * pg.CANAIS_POR_ZONA + 1
            usados = sum(1 for c in self.prog.canais[ini - 1:ini + 99] if not c.vazio) if self.prog else 0
            out.append(f"Zona {z + 1}{': ' + nome if nome else ''} (canais {ini}-{ini + 99}, {usados} em uso)")
        return out

    def _preenche_tabela(self):
        sel = self.tv.selection()
        self.tv.delete(*self.tv.get_children())
        if not self.prog:
            return
        z = max(0, self.cb_zona.current())
        fx, exc = self.faixas(), self.excecoes()
        termo = self.busca.get().strip().casefold().replace(",", ".")
        por = self.prog.perfil.canais_por_zona
        for c in self.prog.canais[z * por:(z + 1) * por]:
            if self.so_ocupados.get() and c.vazio:
                continue
            conteudo = f"{c.rotulo} {c.nome} {pg.mhz(c.rx)} {pg.mhz(c.tx or 0)}".casefold()
            if termo and termo not in conteudo:
                continue
            if c.vazio:
                self.tv.insert("", "end", iid=str(c.numero), values=(c.rotulo, "(vazio)") + ("",) * 8,
                               tags=("vazio",) + (("zebra",) if c.numero % 2 == 0 else ()))
            else:
                off = pg.mhz(c.offset) if c.duplex in ("+", "-", "TX separado") else ""
                sit = pg.situacao_tx(self.prog, c, fx, exc)
                if c.duplex == "Sem TX":
                    sit = "bloqueado"
                txst = tema.TX_TEXTO[sit]
                tags = ((sit,) if sit else ()) + (("zebra",) if c.numero % 2 == 0 else ())
                self.tv.insert("", "end", iid=str(c.numero), tags=tags, values=(
                    c.rotulo, c.nome, pg.mhz(c.rx), c.duplex, off, c.tom_tx, c.tom_rx, c.potencia, c.modo, txst))
        tema.zebra(self.tv)
        sel = [s for s in sel if self.tv.exists(s)]
        if sel:
            self.tv.selection_set(sel)

    def _pode_arrastar(self):
        return bool(self.prog) and not self.app.ocupado and not self.busca.get().strip()

    def _aviso_arraste(self):
        if self.busca.get().strip():
            self.app.status.config(text="Para arrastar canais, limpe a busca (Esc).")

    def _soltou(self, sel, alvo, depois):
        """Move os canais arrastados para antes (ou depois) do canal de destino, dentro da zona."""
        por = self.prog.perfil.canais_por_zona
        z = max(0, self.cb_zona.current())
        inicio = z * por + 1
        ordem = list(range(inicio, inicio + por))
        nova = arrastar.move_bloco(ordem, [int(i) for i in sel], int(alvo), depois)
        if nova == ordem:
            return
        mapa = self.prog.reordena(inicio, nova)
        self.salva_bloqueados()
        self.alterado()
        novos = [str(mapa[int(i)]) for i in sel if self.tv.exists(str(mapa[int(i)]))]
        if novos:
            self.tv.selection_set(novos)
            self.tv.see(novos[0])
        r = self.prog.perfil.rotulo
        self.app.status.config(text=f"{len(sel)} canal(is) movido(s) para a posição {r(mapa[int(sel[0])])}. "
                                    "Desfazer (↶) volta a ordem anterior.")

    def exportar(self):
        if not self._exige_prog():
            return
        p = self.prog.perfil
        colunas = ["Nº", "Nome", "RX (MHz)", "Duplex", "Offset/TX", "Tom TX", "Tom RX", "Potência", "Modo",
                   "Largura", "Varredura"]
        if p.tem_zonas:
            colunas = ["Zona"] + colunas
        linhas, grupos = [], []
        for z in range(p.total_zonas):
            nome = pg.le_nome_zona(self.prog.img, z) if p.tem_zonas else ""
            g = []
            for c in self.prog.canais[z * p.canais_por_zona:(z + 1) * p.canais_por_zona]:
                if c.vazio:
                    continue
                off = pg.mhz(c.offset) if c.duplex in ("+", "-", "TX separado") else ""
                l = [c.rotulo, c.nome, pg.mhz(c.rx), c.duplex, off, c.tom_tx, c.tom_rx, c.potencia, c.modo,
                     c.largura, "Sim" if c.varredura else "Não"]
                if p.tem_zonas:
                    l = [str(z + 1)] + l
                g.append(l)
            linhas += g
            titulo = f"Zona {z + 1}" + (f": {nome}" if nome else "")
            grupos.append((titulo, [x[1:] for x in g] if p.tem_zonas else g))
        modelo = self.app.nome_radio()
        sub = (cr.INDICATIVO + "  ·  " if cr.INDICATIVO else "") + self.origem
        exportar.exporta(self.app, f"Canais_{self.chave}{cr.sufixo_arquivo()}", f"Canais do {modelo}", sub,
                         colunas, linhas, grupos=grupos if p.tem_zonas else None,
                         colunas_grupos=colunas[1:] if p.tem_zonas else None)

    def _clique_tx(self, ev):
        if self.arraste.arrastou:
            return
        if not self.prog or self.app.ocupado:
            return
        if self.tv.identify_region(ev.x, ev.y) != "cell" or self.tv.identify_column(ev.x) != COL_TX:
            return
        linha = self.tv.identify_row(ev.y)
        if not linha:
            return
        c = self.prog.canal(int(linha))
        if c.vazio:
            return
        if c.duplex == "Sem TX":
            erros = self.desbloqueia([c.numero])
            if erros:
                messagebox.showwarning("TX", "\n".join(erros))
            else:
                self.app.status.config(text=f"Canal {c.rotulo}: TX liberado.")
        else:
            self.bloqueia([c.numero])
            self.app.status.config(text=f"Canal {c.rotulo}: TX bloqueado (só recepção).")

    def _selecionados(self):
        return [int(i) for i in self.tv.selection()]

    def editar(self):
        if not self._exige_prog():
            return
        sel = self._selecionados()
        if not sel:
            messagebox.showinfo("Canais", "Selecione um canal na lista.")
            return
        EditorCanal(self, self.prog.canal(sel[0]))

    def apagar(self):
        if not self._exige_prog():
            return
        sel = self._selecionados()
        if sel and messagebox.askyesno("Canais", f"Apagar {len(sel)} canal(is)?"):
            for n in sel:
                self.prog.apaga(n)
            self.alterado()

    def copiar(self):
        if self.prog:
            self.copia = [self.prog.canal(n) for n in self._selecionados()]
            self.app.status.config(text=f"{len(self.copia)} canal(is) copiado(s).")

    def colar(self):
        if self.app.ocupado or not self.prog or not self.copia:
            return
        sel = self._selecionados()
        if not sel:
            return
        inicio = min(sel)
        if inicio + len(self.copia) - 1 > self.prog.perfil.total_canais:
            messagebox.showinfo("Canais", "Os canais copiados não cabem a partir do canal selecionado.")
            return
        if any(c.p is not self.prog.perfil for c in self.copia):
            messagebox.showinfo("Canais", "Os canais copiados são de outro modelo de rádio. Use Editar para "
                                          "criar o canal neste rádio.")
            return
        ocupados = [inicio + i for i in range(len(self.copia)) if not self.prog.canal(inicio + i).vazio]
        if ocupados and not messagebox.askyesno("Canais", f"Substituir {len(ocupados)} canal(is) já ocupado(s)?"):
            return
        for i, c in enumerate(self.copia):
            n = inicio + i
            novo = self.prog.decodifica(n, c.bruto)
            self.prog.define_canal(novo)
        self.alterado()

    # ------------------------------------------------------------------- zonas
    def _monta_zonas(self):
        for w in self.f_zonas.winfo_children():
            w.destroy()
        if not self.prog:
            ttk.Label(self.f_zonas, text="Leia o rádio ou abra um arquivo primeiro.").pack(padx=10, pady=10)
            return
        ttk.Label(self.f_zonas, text="O rádio tem 10 zonas fixas de 100 canais. Dê um nome a cada uma "
                                     "(até 16 letras, sem acento).", style="Suave.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w", padx=10, pady=8)
        for z in range(pg.TOTAL_ZONAS):
            ttk.Label(self.f_zonas, text=f"Zona {z + 1} (canais {z * 100 + 1} a {z * 100 + 100}):").grid(
                row=z + 1, column=0, sticky="w", padx=10, pady=3)
            v = tk.StringVar(value=pg.le_nome_zona(self.prog.img, z))
            e = ttk.Entry(self.f_zonas, textvariable=v, width=20)
            e.grid(row=z + 1, column=1, sticky="w", pady=3)
            v.trace_add("write", lambda *_a, zz=z, vv=v: self._muda_zona(zz, vv))

    def _muda_zona(self, z, v):
        try:
            pg.grava_nome_zona(self.prog.img, z, v.get().upper()[:16])
        except pg.ErroProgramacao as e:
            self.app.status.config(text=str(e))
            return
        self._registra_edicao()
        nomes = self._rotulos_zona()
        i = self.cb_zona.current()
        self.cb_zona["values"] = nomes
        if i >= 0:
            self.cb_zona.current(i)
        self._atualiza_origem()

    # -------------------------------------------------------------------- DTMF
    def _monta_dtmf(self):
        for w in self.f_dtmf.winfo_children():
            w.destroy()
        self._dtmf_atual = None
        if not self.prog or self.chave != "UV17ProGPS":
            ttk.Label(self.f_dtmf, text="Leia o rádio ou abra um arquivo primeiro.").pack(padx=10, pady=10)
            return
        topo = ttk.Frame(self.f_dtmf, padding=(16, 10, 16, 6))
        topo.pack(fill="x")
        ttk.Label(topo, text="Radio ID").pack(side="left")
        self.v_radio_id = tk.StringVar(value=pg.le_radio_id(self.prog.img))
        ttk.Entry(topo, textvariable=self.v_radio_id, width=18).pack(side="left", padx=(8, 6))
        ttk.Button(topo, text="Aplicar Radio ID", command=self._aplica_radio_id).pack(side="left")
        ttk.Label(topo, text="Só números. Usado para o GPS de um rádio se conectar a outro.",
                  style="Suave.TLabel").pack(side="left", padx=(12, 0))

        corpo = ttk.Frame(self.f_dtmf, padding=(16, 4, 16, 10))
        corpo.pack(fill="both", expand=True)
        self.tv_dtmf = ttk.Treeview(corpo, columns=("n", "cod", "nome"), show="headings", height=16,
                                    selectmode="browse")
        for c, rot, larg in (("n", "Nº", 60), ("cod", "Código", 180), ("nome", "Nome", 200)):
            self.tv_dtmf.heading(c, text=rot)
            self.tv_dtmf.column(c, width=larg, anchor="w")
        self.tv_dtmf.pack(side="left", fill="y")
        tema.zebra(self.tv_dtmf)
        self.tv_dtmf.bind("<<TreeviewSelect>>", self._seleciona_dtmf)

        form = ttk.Frame(corpo, padding=(20, 0, 0, 0))
        form.pack(side="left", fill="y")
        self.lb_dtmf = ttk.Label(form, text="Escolha uma entrada na lista.", style="Suave.TLabel")
        self.lb_dtmf.pack(anchor="w")
        ttk.Label(form, text="Código (0-9, A-D, * e #)").pack(anchor="w", pady=(12, 2))
        self.v_dtmf_cod = tk.StringVar()
        self.e_dtmf_cod = ttk.Entry(form, textvariable=self.v_dtmf_cod, width=22, state="disabled")
        self.e_dtmf_cod.pack(anchor="w")
        ttk.Label(form, text="Nome (sem acento, opcional)").pack(anchor="w", pady=(12, 2))
        self.v_dtmf_nome = tk.StringVar()
        self.e_dtmf_nome = ttk.Entry(form, textvariable=self.v_dtmf_nome, width=22, state="disabled")
        self.e_dtmf_nome.pack(anchor="w")
        ttk.Label(form, text="Código e nome juntos: até 16 caracteres.", style="Suave.TLabel").pack(anchor="w", pady=(4, 0))
        botoes = ttk.Frame(form)
        botoes.pack(anchor="w", pady=(14, 0))
        self.bt_dtmf_aplica = ttk.Button(botoes, text="Aplicar", command=self._aplica_dtmf, state="disabled")
        self.bt_dtmf_aplica.pack(side="left", padx=(0, 8))
        self.bt_dtmf_apaga = ttk.Button(botoes, text="Apagar entrada", command=self._apaga_dtmf, state="disabled")
        self.bt_dtmf_apaga.pack(side="left")
        self._preenche_dtmf()

    def _preenche_dtmf(self):
        if not self.prog or not hasattr(self, "tv_dtmf"):
            return
        self.tv_dtmf.delete(*self.tv_dtmf.get_children())
        for n in range(1, pg.TOTAL_DTMF + 1):
            cod, nome = pg.le_dtmf(self.prog.img, n)
            self.tv_dtmf.insert("", "end", iid=str(n), values=(n, cod, nome))

    def _seleciona_dtmf(self, _=None):
        sel = self.tv_dtmf.selection()
        if not sel:
            return
        n = int(sel[0])
        cod, nome = pg.le_dtmf(self.prog.img, n)
        self._dtmf_atual = n
        self.lb_dtmf.config(text=f"Entrada {n}")
        self.v_dtmf_cod.set(cod)
        self.v_dtmf_nome.set(nome)
        for w in (self.e_dtmf_cod, self.e_dtmf_nome, self.bt_dtmf_aplica, self.bt_dtmf_apaga):
            w.config(state="normal")

    def _aplica_dtmf(self):
        if not self.prog or self._dtmf_atual is None:
            return
        n = self._dtmf_atual
        try:
            pg.grava_dtmf(self.prog.img, n, self.v_dtmf_cod.get().strip().upper(), self.v_dtmf_nome.get().strip())
        except pg.ErroProgramacao as e:
            messagebox.showerror("DTMF", str(e), parent=self)
            return
        self._registra_edicao()
        self._preenche_dtmf()
        self.tv_dtmf.selection_set(str(n))
        self._atualiza_origem()

    def _apaga_dtmf(self):
        if not self.prog or self._dtmf_atual is None:
            return
        n = self._dtmf_atual
        if not messagebox.askyesno("DTMF", f"Apagar a entrada {n}?", parent=self):
            return
        pg.grava_dtmf(self.prog.img, n, "")
        self._registra_edicao()
        self._preenche_dtmf()
        self.tv_dtmf.selection_set(str(n))
        self._seleciona_dtmf()
        self._atualiza_origem()

    def _aplica_radio_id(self):
        if not self.prog:
            return
        try:
            pg.grava_radio_id(self.prog.img, self.v_radio_id.get().strip())
        except pg.ErroProgramacao as e:
            messagebox.showerror("DTMF", str(e), parent=self)
            return
        self._registra_edicao()
        self._atualiza_origem()

    # ----------------------------------------------------------------- ajustes
    def _monta_ajustes(self):
        for w in self.f_ajustes.winfo_children():
            w.destroy()
        self.vars_ajuste = {}
        if not self.prog:
            ttk.Label(self.f_ajustes, text="Leia o rádio ou abra um arquivo primeiro.").pack(padx=10, pady=10)
            return
        if self.chave == "UV5R":
            self._monta_ajustes_uv5r()
            return
        defs = pg.ajustes_do_modelo(self.chave)
        base = self.prog.perfil.pos_ajustes
        tela = tk.Canvas(self.f_ajustes, highlightthickness=0, bg=tema.C["fundo"])
        rol = ttk.Scrollbar(self.f_ajustes, orient="vertical", command=tela.yview)
        area = ttk.Frame(tela)
        area.bind("<Configure>", lambda e: tela.configure(scrollregion=tela.bbox("all")))
        tela.create_window((0, 0), window=area, anchor="nw")
        tela.configure(yscrollcommand=rol.set)
        tela.pack(side="left", fill="both", expand=True)
        rol.pack(side="right", fill="y")

        def roda(ev):
            tela.yview_scroll(int(-ev.delta / 120) if ev.delta else (1 if ev.num == 5 else -1), "units")
        tela.bind("<Enter>", lambda e: (tela.bind_all("<MouseWheel>", roda), tela.bind_all("<Button-4>", roda),
                                        tela.bind_all("<Button-5>", roda)))
        tela.bind("<Leave>", lambda e: (tela.unbind_all("<MouseWheel>"), tela.unbind_all("<Button-4>"),
                                        tela.unbind_all("<Button-5>")))
        grupos = []
        for a in defs:
            if a[4] not in grupos:
                grupos.append(a[4])
        quadros = {}
        for i, g in enumerate(grupos):
            lf = ttk.LabelFrame(area, text=g, padding=8)
            lf.grid(row=i // 2, column=i % 2, sticky="nsew", padx=8, pady=6)
            quadros[g] = lf
        contagem = {g: 0 for g in grupos}
        for a in defs:
            chave, _, rotulo, opcoes, grupo = a[:5]
            lf, r = quadros[grupo], contagem[grupo]
            contagem[grupo] += 1
            atual = pg.le_ajuste(self.prog.img, chave, defs, base=base)
            if isinstance(opcoes, tuple) and opcoes[0] == "texto":
                ttk.Label(lf, text=rotulo).grid(row=r, column=0, sticky="w", pady=2, padx=(0, 6))
                v = tk.StringVar(value=atual)
                n = opcoes[1]
                vc_ = (lf.register(lambda txt, n=n: len(txt) <= n), "%P")
                ttk.Entry(lf, textvariable=v, width=n + 4, validate="key", validatecommand=vc_).grid(
                    row=r, column=1, sticky="w", pady=2)
            elif opcoes == "bool":
                v = tk.BooleanVar(value=atual)
                ttk.Checkbutton(lf, text=rotulo, variable=v).grid(row=r, column=0, columnspan=2, sticky="w", pady=2)
            else:
                ttk.Label(lf, text=rotulo).grid(row=r, column=0, sticky="w", pady=2, padx=(0, 6))
                v = tk.StringVar(value=atual)
                lista = [n for n, _ in pg.TECLA2] if chave == "key2short" else list(opcoes)
                if atual not in lista:
                    lista = [atual] + lista
                ttk.Combobox(lf, textvariable=v, values=lista, state="readonly",
                             width=max(8, min(24, max(len(x) for x in lista) + 2))).grid(row=r, column=1, sticky="w", pady=2)
            ajuda.botao(lf, chave).grid(row=r, column=2, padx=(6, 0))
            v.trace_add("write", lambda *_a, k=chave, vv=v, d=defs, b=base: self._muda_ajuste(k, vv, d, b))
            self.vars_ajuste[chave] = v

    def _monta_ajustes_uv5r(self):
        """UV-5R: todos os ajustes do driver do CHIRP, em grupos e submenus."""
        self._vars_uv5r = []
        try:
            arv = aj5.arvore(self.prog.img)
        except Exception as e:
            ttk.Label(self.f_ajustes, text=f"Não foi possível ler os ajustes: {e}").pack(padx=10, pady=10)
            return
        tela = tk.Canvas(self.f_ajustes, highlightthickness=0, bg=tema.C["fundo"])
        rol = ttk.Scrollbar(self.f_ajustes, orient="vertical", command=tela.yview)
        area = ttk.Frame(tela)
        area.bind("<Configure>", lambda e: tela.configure(scrollregion=tela.bbox("all")))
        tela.create_window((0, 0), window=area, anchor="nw")
        tela.configure(yscrollcommand=rol.set)
        tela.pack(side="left", fill="both", expand=True)
        rol.pack(side="right", fill="y")

        def roda(ev):
            tela.yview_scroll(int(-ev.delta / 120) if ev.delta else (1 if ev.num == 5 else -1), "units")
        tela.bind("<Enter>", lambda e: (tela.bind_all("<MouseWheel>", roda), tela.bind_all("<Button-4>", roda),
                                        tela.bind_all("<Button-5>", roda)))
        tela.bind("<Leave>", lambda e: (tela.unbind_all("<MouseWheel>"), tela.unbind_all("<Button-4>"),
                                        tela.unbind_all("<Button-5>")))
        ttk.Label(area, text="Os nomes de alguns ajustes ainda estão em inglês, como no programa da Icom.",
                  style="Suave.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", padx=8, pady=(6, 0))
        for i, grupo in enumerate(arv):
            lf = ttk.LabelFrame(area, text=aj5.rotulo_grupo(grupo.get_name()), padding=8)
            lf.grid(row=1 + i // 2, column=i % 2, sticky="nsew", padx=8, pady=6)
            for _chave, rotulo, itens in aj5.submenus(grupo):
                sf = ttk.LabelFrame(lf, text=rotulo, padding=6)
                sf.pack(fill="x", pady=(0, 6))
                for r, el in enumerate(itens):
                    self._widget_uv5r(sf, r, el)

    def _widget_uv5r(self, lf, r, el):
        valor = el.value
        rot = el.get_shortname()
        ativo = valor.get_mutable()
        if isinstance(valor, cs.RadioSettingValueBoolean):
            v = tk.BooleanVar(value=bool(valor.get_value()))
            w = ttk.Checkbutton(lf, text=rot, variable=v)
            w.grid(row=r, column=0, columnspan=2, sticky="w", pady=2)
            if not ativo:
                w.state(["disabled"])
        else:
            ttk.Label(lf, text=rot).grid(row=r, column=0, sticky="w", pady=2, padx=(0, 6))
            if isinstance(valor, cs.RadioSettingValueList):
                opcoes = list(valor.get_options())
                v = tk.StringVar(value=str(valor.get_value()))
                w = ttk.Combobox(lf, textvariable=v, values=opcoes,
                                 state="readonly" if ativo else "disabled",
                                 width=max(6, min(30, max((len(o) for o in opcoes), default=6) + 2)))
            else:
                texto = str(valor.get_value())
                if isinstance(valor, cs.RadioSettingValueString):
                    texto = texto.rstrip()
                v = tk.StringVar(value=texto)
                w = ttk.Entry(lf, textvariable=v, width=max(14, min(30, len(texto) + 2)),
                              state="normal" if ativo else "disabled")
            w.grid(row=r, column=1, sticky="w", pady=2)
        self._vars_uv5r.append(v)          # sem referência, o Tk perde o valor dos campos
        if ativo:
            v.trace_add("write", lambda *_a, n=el.get_name(), vv=v, tipo=valor: self._muda_uv5r(n, vv, tipo))

    def _muda_uv5r(self, nome, v, tipo):
        x = v.get()
        try:
            if isinstance(tipo, cs.RadioSettingValueInteger):
                x = int(x)
            elif isinstance(tipo, cs.RadioSettingValueFloat):
                x = float(str(x).replace(",", "."))
            aj5.grava(self.prog.img, nome, x)
        except Exception as e:
            self.app.status.config(text=f"{nome}: valor não aceito ({e}).")
            return
        self._registra_edicao()
        self._atualiza_origem()

    def _muda_ajuste(self, chave, v, defs, base=pg.POS_AJUSTES):
        try:
            pg.grava_ajuste(self.prog.img, chave, v.get(), defs, base=base)
        except pg.ErroProgramacao as e:
            self.app.status.config(text=str(e))
            return
        self._registra_edicao()
        self._atualiza_origem()

    # ------------------------------------------------------------------ estado
    def _exige_prog(self):
        if self.app.ocupado:
            return False
        if not self.prog:
            messagebox.showinfo("Programação", "Primeiro clique em Ler rádio ou abra um arquivo .img.")
            return False
        return True

    def _atualiza_origem(self):
        if not self.prog:
            self.info.mostra("Nenhuma programação carregada.")
            return
        fora = self._fora_das_faixas()
        faixas = f"  ·  {fora} com TX fora das faixas liberadas" if fora else ""
        self.info.mostra(self.origem, f"{tema.plural(self.prog.usados(), 'canal', 'canais')} em uso{faixas}",
                         self.modificado, self.caminho)

    def alterado(self):
        self._registra_edicao()
        i = max(0, self.cb_zona.current())
        self.cb_zona["values"] = self._rotulos_zona()
        self.cb_zona.current(i)
        self._preenche_tabela()
        self._atualiza_origem()

    def _atualiza_tudo(self):
        # Zonas só existem no UV-17 (o UV-5R tem uma lista única de 128 canais)
        self.nb.tab(self.f_zonas, state="normal" if not self.prog or self.prog.perfil.tem_zonas else "hidden")
        tema.alterna_inicio(self.aviso, self._topo, self.tv.master, not self.prog)
        if self.prog:
            i = max(0, self.cb_zona.current())
            self.cb_zona["values"] = self._rotulos_zona()
            self.cb_zona.current(i)
        else:
            self.cb_zona["values"] = []
        self._preenche_tabela()
        self.nb.tab(self.f_dtmf, state="normal" if not self.prog or self.chave == "UV17ProGPS" else "hidden")
        self._monta_zonas()
        self._monta_ajustes()
        self._monta_dtmf()
        self._atualiza_origem()

    def carrega(self, dados, chave, origem, meta=None):
        self.prog = pg.Programacao(dados, chave)
        self.chave = chave
        self.origem = origem
        self.caminho = ""
        self.modificado = False
        guardados = dict(self.app.cfg.get("tx_bloqueados", {}).get(chave, {}))
        guardados.update((meta or {}).get("tx_bloqueados", {}))
        for k, o in guardados.items():
            c = self.prog.canal(int(k))
            if not c.vazio and c.duplex == "Sem TX" and o.get("rx") == c.rx:
                self.prog.tx_bloqueados[int(k)] = o
        self.base_gravacao = bytes(dados)
        self.historico = [(self.prog.imagem(), copy.deepcopy(self.prog.tx_bloqueados))]
        self.pos_historico = 0
        self.salvo_estado = self._assinatura_estado()
        self._atualiza_tudo()

    # ---------------------------------------------------------- bloqueio de TX
    def controle(self):
        """Preferência "Controlar as faixas de TX" (desligada por padrão)."""
        return bool(self.app.cfg.get("controle_faixas", False))

    def aplica_controle(self):
        """Mostra ou esconde o controle de faixas conforme a preferência."""
        if self.controle():
            self.bt_bloqueio.pack(side="right")
            self.legenda.pack(side="bottom", fill="x", padx=16, pady=(0, 6), before=self._topo)
        else:
            self.bt_bloqueio.pack_forget()
            self.legenda.pack_forget()
        self._preenche_tabela()

    def faixas(self, configuradas=False):
        if not configuradas and not self.controle():
            return [(0, 10 ** 12, "Todas")]        # sem controle: nenhuma frequência fica "fora da faixa"
        return [tuple(x) for x in self.app.cfg.get("faixas_tx", pg.FAIXAS_LIBERADAS_PADRAO)]

    def salva_faixas(self, fx):
        self.app.cfg["faixas_tx"] = [list(x) for x in fx]
        self.app._salva_cfg()
        self._preenche_tabela()

    def bloqueio_auto(self):
        return self.controle() and bool(self.app.cfg.get("bloqueio_tx_auto", True))

    def excecoes(self):
        if not self.chave:
            return set()
        return set(self.app.cfg.get("tx_excecoes", {}).get(self.chave, []))

    def salva_excecoes(self, exc):
        self.app.cfg.setdefault("tx_excecoes", {})[self.chave] = sorted(exc)
        self.app._salva_cfg()

    def salva_bloqueados(self):
        if self.prog:
            self.app.cfg.setdefault("tx_bloqueados", {})[self.chave] = {
                str(k): v for k, v in self.prog.tx_bloqueados.items()}
            self.app._salva_cfg()

    def meta_extra(self):
        return {"tx_bloqueados": {str(k): v for k, v in self.prog.tx_bloqueados.items()}} if self.prog else {}

    def pendentes(self):
        fx, exc = self.faixas(), self.excecoes()
        return [c.numero for c in self.prog.canais if pg.situacao_tx(self.prog, c, fx, exc) == "pendente"]

    def bloqueia(self, numeros):
        exc = self.excecoes()
        n = 0
        for num in numeros:
            if pg.bloqueia_tx(self.prog, num):
                n += 1
            exc.discard(pg.chave_excecao(self.prog.canal(num)))
        self.salva_excecoes(exc)
        self.salva_bloqueados()
        if n:
            self.alterado()
        return n

    def desbloqueia(self, numeros):
        exc, erros = self.excecoes(), []
        for num in numeros:
            try:
                pg.desbloqueia_tx(self.prog, num)
                c = self.prog.canal(num)
                if not pg.dentro_das_faixas(c.tx, self.faixas()):
                    exc.add(pg.chave_excecao(c))
            except pg.ErroProgramacao as e:
                erros.append(str(e))
        self.salva_excecoes(exc)
        self.salva_bloqueados()
        self.alterado()
        return erros

    def _fora_das_faixas(self):
        """Quantos canais transmitem fora das faixas liberadas (0 com o controle de faixas desligado).
        O número aparece na linha de situação e na confirmação da gravação, sem janela de aviso."""
        if not self.prog or not self.bloqueio_auto():
            return 0
        return len(self.pendentes())

    def janela_bloqueio(self):
        if self._exige_prog():
            JanelaBloqueio(self)

    def _confirma_descartar(self):
        return (not self.modificado or messagebox.askyesno(
            "Programação", "Há alterações não gravadas na programação atual. Descartar?"))

    # ------------------------------------------------------------ rádio/arquivo
    def ler(self):
        porta = self.app.porta.get().strip()
        if not porta:
            messagebox.showerror("Programação", "Escolha a porta COM do cabo de programação.")
            return
        if not self._confirma_descartar():
            return
        chave = self.app.modelo_radio
        res = {}

        def tarefa():
            dados, ident = cr.le_configuracao(porta, chave, progresso=self.app.progresso)
            carimbo = time.strftime("%Y-%m-%d_%H-%M-%S")
            destino = os.path.join(self.app.pasta_backup(), f"Config_{carimbo}_{chave}{cr.sufixo_arquivo()}.img")
            cr.salva_img(destino, chave, dados, ident)
            res.update(dados=dados, ident=cr.descreve_leitura(chave, dados, ident), arq=destino)

        def fim():
            self.carrega(res["dados"], chave, f"Lido do rádio às {time.strftime('%H:%M')} "
                                              f"({res['ident'] or 'sem identificação'})")
            self.app.status.config(text=f"Rádio lido. Backup automático: {os.path.basename(res['arq'])}")
            aviso = cr.confere_modelo(chave, res["dados"], res["ident"])
            if aviso:
                messagebox.showwarning("Modelo diferente", f"{aviso}\n\nO modelo escolhido no topo é o "
                                                           f"{self.app.nome_radio()}. Confira antes de editar ou gravar.")
        self.app.executa("Lendo o rádio...", tarefa, depois=fim)

    def gravar(self):
        if not self._exige_prog():
            return
        porta = self.app.porta.get().strip()
        if not porta:
            messagebox.showerror("Programação", "Escolha a porta COM do cabo de programação.")
            return
        if self.chave != self.app.modelo_radio:
            messagebox.showerror("Programação", "A programação carregada é de outro modelo de rádio. "
                                                "Ajuste o modelo no topo da janela.")
            return
        for c in self.prog.canais:
            try:
                c.valida()
            except pg.ErroProgramacao as e:
                messagebox.showerror("Programação", str(e))
                return
        fora = self._fora_das_faixas()
        if not messagebox.askyesno(
                "Gravar no rádio", f"Gravar no {self.app.nome_radio()} a programação atual "
                                   f"({tema.plural(self.prog.usados(), 'canal', 'canais')} em uso)? "
                                   "Ela substitui a que está no rádio."
                                   + self._resumo_comparacao()
                                   + (f"\n\nAtenção: {fora} canal(is) com TX fora das faixas liberadas."
                                      if fora else "")):
            return
        dados, chave, extra = self.prog.imagem(), self.chave, self.meta_extra()
        com_backup = bool(self.app.cfg.get("backup_antes_gravar", False))

        resultado = {}
        def tarefa():
            import uuid

            def salva_copia(atual, ident):
                # Cópia do rádio conectado, salva ANTES do primeiro bloco gravado.
                carimbo = time.strftime("%Y-%m-%d_%H-%M-%S") + "_" + uuid.uuid4().hex[:8]
                cr.salva_img(os.path.join(self.app.pasta_backup(), f"Antes_gravar_{carimbo}_{chave}.img"),
                             chave, atual, ident)

            registro = RegistroEnvio(self.app.pasta_backup(), "Programacao", chave, porta, ".img",
                                    lambda path: cr.salva_img(path, chave, dados, extra=extra))
            if com_backup:
                # Leitura de segurança e gravação na mesma conexão (uma só identificação).
                resultado["aviso"] = registro.executa(lambda: cr.le_e_grava(
                    porta, chave, dados, progresso=self.app.progresso, apos_leitura=salva_copia))
            else:
                resultado["aviso"] = registro.executa(lambda: cr.grava_configuracao(
                    porta, chave, dados, progresso=self.app.progresso, rotulo="Gravando no rádio"))

        def fim():
            self.base_gravacao = dados
            self.salvo_estado = self._assinatura_estado()
            self.modificado = False
            self._remove_rascunho()
            self._atualiza_origem()
            self.app.status.config(text=("Programação gravada no rádio. " + resultado.get("aviso", "")).strip())
        self.app.executa("Gravando no rádio...", tarefa, depois=fim, nota=tema.NOTA_GRAVACAO)

    def abrir(self):
        if not self._confirma_descartar():
            return
        caminho = filedialog.askopenfilename(title="Abrir programação", initialdir=self.app.pasta_backup(),
                                             filetypes=[("Programação do rádio (.img)", "*.img"), ("Todos", "*.*")])
        if not caminho:
            return
        try:
            chave, dados, meta = cr.abre_img(caminho)
        except Exception as e:
            messagebox.showerror("Programação", str(e))
            return
        chave = chave or self.app.modelo_radio
        sel = self.app.modelo_radio
        if (chave != sel and sel in cr.CLONE and chave in cr.CLONE and cr.CLONE[sel].get("magic")
                and cr.CLONE[sel].get("magic") == cr.CLONE[chave].get("magic")):
            # Mesmo protocolo e mapa de memória (ex.: UV-21 Pro salvo pelo CHIRP como UV-17Pro):
            # vale o modelo escolhido no topo
            chave = sel
        if chave != self.app.modelo_radio:
            if not self.app.seleciona_modelo(chave):
                return
        self.carrega(dados, chave, f"Arquivo: {os.path.basename(caminho)}", meta)
        self.caminho = caminho
        self._atualiza_origem()

    def salvar(self):
        if not self._exige_prog():
            return
        caminho = filedialog.asksaveasfilename(
            title="Salvar programação", defaultextension=".img",
            initialfile=f"Programacao_{self.chave}{cr.sufixo_arquivo()}.img",
            filetypes=[("Programação do rádio (.img)", "*.img")])
        if caminho:
            cr.salva_img(caminho, self.chave, self.prog.imagem(), extra=self.meta_extra())
            self.origem = f"Arquivo: {os.path.basename(caminho)}"
            self.caminho = caminho
            self.salvo_estado = self._assinatura_estado()
            self.modificado = False
            self._remove_rascunho()
            self._atualiza_origem()



    def tx_radioamador(self, acao):
        if not self._exige_prog():
            return
        numeros = pg.candidatos_radioamador(self.prog, acao)
        if not numeros:
            messagebox.showinfo("TX radioamador", "Nenhum canal precisa dessa alteração.")
            return
        texto = (f"Bloquear o TX de {len(numeros)} canais fora das faixas de radioamador? "
                 "Inclui canais que estavam liberados como exceção." if acao == "bloquear" else
                 f"Liberar o TX de {len(numeros)} canais nas faixas de radioamador? "
                 "Sem TX anterior guardado, o canal passa a simplex (TX igual ao RX).")
        if not messagebox.askyesno("TX radioamador", texto +
                "\n\nReferência de TX: 144 a 148, 220 a 225 e 430 a 440 MHz (radioamador) e 462 a 467 MHz (FRS). "
                + ("A ação alcança todas as dez zonas, independentemente da busca/filtro." if self.prog.perfil.tem_zonas
                   else "A ação alcança todos os canais, independentemente da busca/filtro.") +
                "\n\nA edição só será aplicada ao aparelho ao clicar em Gravar no rádio."):
            return
        erros = self.desbloqueia(numeros) if acao == "liberar" else []
        n = len(numeros) - len(erros) if acao == "liberar" else self.bloqueia(numeros)
        self.app.status.config(text=f"TX: {n} canal(is) alterado(s). Use Gravar no rádio para aplicar; Desfazer reverte a ação.")
        if erros:
            messagebox.showwarning("TX", "\n".join(erros[:10]))

    def tx_selecionados(self, liberar):
        if not self._exige_prog():
            return
        numeros = [n for n in self._selecionados() if not self.prog.canal(n).vazio
                   and ((self.prog.canal(n).duplex == "Sem TX") if liberar else (self.prog.canal(n).duplex != "Sem TX"))]
        if not numeros:
            messagebox.showinfo("TX individual", "Selecione um canal ocupado que precise ser " + ("liberado." if liberar else "bloqueado."))
            return
        msg = ("Liberar" if liberar else "Bloquear") + f" TX de {len(numeros)} canal(is) selecionado(s)?"
        if liberar:
            msg += "\nSem TX anterior guardado, usa simplex (TX igual ao RX). Frequências não aceitas pelo perfil continuam bloqueadas."
        if not messagebox.askyesno("TX individual", msg + "\n\nUse Gravar no rádio para aplicar as edições."):
            return
        if liberar:
            erros = self.desbloqueia(numeros)
            if erros:
                messagebox.showwarning("TX", "\n".join(erros[:10]))
        else:
            self.bloqueia(numeros)
        self.app.status.config(text="Edição individual de TX preparada. Use Gravar no rádio para aplicar.")

    def _estado(self):
        return self.prog.imagem(), copy.deepcopy(self.prog.tx_bloqueados)

    def _assinatura_estado(self):
        return assinatura(*self._estado()) if self.prog else None

    def _registra_edicao(self):
        if not self.prog:
            return
        estado = self._estado()
        if self.pos_historico < 0 or estado != self.historico[self.pos_historico]:
            self.historico = self.historico[:self.pos_historico + 1] + [estado]
            self.historico = self.historico[-51:]
            self.pos_historico = len(self.historico) - 1
        self.modificado = self._assinatura_estado() != self.salvo_estado

    def _historico_move(self, delta):
        if self.app.ocupado or not self.prog:
            return
        destino = self.pos_historico + delta
        if not 0 <= destino < len(self.historico):
            return
        self.pos_historico = destino
        dados, bloqueados = self.historico[destino]
        self.prog = pg.Programacao(dados, self.chave)
        self.prog.tx_bloqueados = copy.deepcopy(bloqueados)
        self.modificado = self._assinatura_estado() != self.salvo_estado
        self.salva_bloqueados()
        self._atualiza_tudo()

    def desfazer(self):
        self._historico_move(-1)

    def refazer(self):
        self._historico_move(1)

    def _resumo_comparacao(self):
        """Uma linha com o que mudou desde a leitura ou a abertura do arquivo ("" se nada mudou)."""
        if self.base_gravacao is None:
            return ""
        d = pg.compara_imagens(self.base_gravacao, self.prog.imagem(), self.chave)
        partes = [f"{d[k]} canal {um}" if d[k] == 1 else f"{d[k]} canais {um}s"
                  for k, um in (("incluidos", "incluído"), ("alterados", "alterado"), ("apagados", "apagado"))
                  if d[k]]
        if self.prog.perfil.tem_zonas and d["zonas"]:
            partes.append("1 zona alterada" if d["zonas"] == 1 else f"{d['zonas']} zonas alteradas")
        if d["ajustes"]:
            partes.append("ajustes alterados")
        return "\n\nMudanças: " + ", ".join(partes) + "." if partes else ""

    def _remove_rascunho(self):
        path = os.path.join(self.app.pasta_rascunhos(), f"Rascunho_programacao_{self.chave}.img")
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


class JanelaBloqueio(tk.Toplevel):
    """Faixas liberadas para TX e lista de canais fora delas (bloquear/desbloquear)."""

    SITUACOES = {"pendente": "TRANSMITE fora das faixas", "excecao": "Transmite (exceção liberada)",
                 "bloqueado": "Só recepção (TX bloqueado)"}

    def __init__(self, aba):
        super().__init__(aba.app.raiz)
        self.aba = aba
        self.title("Bloqueio de transmissão fora das faixas")
        self.transient(aba.app.raiz)
        r = aba.app.raiz
        larg, alt = min(1180, r.winfo_screenwidth() - 40), min(780, r.winfo_screenheight() - 80)
        self.geometry(f"{larg}x{alt}+{max(0, r.winfo_rootx() + (r.winfo_width() - larg) // 2)}"
                      f"+{max(0, r.winfo_rooty() + 10)}")
        f = ttk.Frame(self, padding=10)
        f.pack(fill="both", expand=True)

        lf = ttk.LabelFrame(f, text="Faixas liberadas para transmissão (MHz)", padding=8)
        lf.pack(fill="x")
        self.tv_f = ttk.Treeview(lf, columns=("ini", "fim", "desc"), show="headings", height=4)
        for c, t, w in (("ini", "Início", 10), ("fim", "Fim", 10), ("desc", "Descrição", 30)):
            self.tv_f.heading(c, text=t)
            self.tv_f.column(c, width=aba.app.largura_texto(w), anchor="w" if c == "desc" else "center")
        self.tv_f.grid(row=0, column=0, rowspan=4, sticky="nsew")
        ent = ttk.Frame(lf)
        ent.grid(row=0, column=1, sticky="nw", padx=10)
        self.n_ini, self.n_fim, self.n_desc = tk.StringVar(), tk.StringVar(), tk.StringVar()
        for i, (rot, v, w) in enumerate((("Início", self.n_ini, 9), ("Fim", self.n_fim, 9),
                                          ("Descrição", self.n_desc, 22))):
            ttk.Label(ent, text=rot).grid(row=0, column=i, sticky="w", padx=2)
            ttk.Entry(ent, textvariable=v, width=w).grid(row=1, column=i, padx=2)
        bts = ttk.Frame(lf)
        bts.grid(row=1, column=1, sticky="nw", padx=10, pady=6)
        ttk.Button(bts, text="Adicionar faixa", command=self.adiciona_faixa).pack(side="left", padx=2)
        ttk.Button(bts, text="Remover selecionada", command=self.remove_faixa).pack(side="left", padx=2)
        ttk.Button(bts, text="Restaurar padrão", command=self.padrao_faixas).pack(side="left", padx=2)
        self.auto = tk.BooleanVar(value=aba.bloqueio_auto())
        ttk.Checkbutton(lf, text="Verificar automaticamente ao ler, abrir, editar e gravar",
                        variable=self.auto, command=self._muda_auto).grid(row=2, column=1, sticky="w", padx=10)
        lf.columnconfigure(0, weight=1)

        ttk.Button(f, text="Fechar", command=self.destroy).pack(side="bottom", anchor="e", pady=(8, 0))
        lc = ttk.LabelFrame(f, text="Canais fora das faixas liberadas", padding=8)
        lc.pack(fill="both", expand=True, pady=(10, 0))
        bar = ttk.Frame(lc)
        bar.pack(fill="x", pady=(0, 6))
        ttk.Button(bar, text="Bloquear TX de TODOS que transmitem fora",
                   command=self.bloqueia_pendentes).pack(side="left", padx=2)
        ttk.Button(bar, text="Bloquear TX dos selecionados", command=self.bloqueia_sel).pack(side="left", padx=2)
        ttk.Button(bar, text="Desbloquear selecionados", command=self.desbloqueia_sel).pack(side="left", padx=2)
        # Ações em lote pela referência de radioamador/FRS (antes ficavam na aba Canais)
        bar2 = ttk.Frame(lc)
        bar2.pack(fill="x", pady=(0, 6))
        ttk.Label(bar2, text="Radioamador e FRS:").pack(side="left", padx=(2, 6))
        ttk.Button(bar2, text="Bloquear fora dessas faixas",
                   command=lambda: self._lote_radioamador("bloquear")).pack(side="left", padx=2)
        ttk.Button(bar2, text="Liberar dentro dessas faixas",
                   command=lambda: self._lote_radioamador("liberar")).pack(side="left", padx=2)
        ajuda.botao(bar2, "tx_radioamador").pack(side="left", padx=4)
        self.lbl_resumo = ttk.Label(lc, font=aba.app.fonte_negrito)
        self.lbl_resumo.pack(fill="x", pady=(0, 4))
        meio = ttk.Frame(lc)
        meio.pack(fill="both", expand=True)
        cols = (("num", "Nº", 5), ("zona", "Zona", 5), ("nome", "Nome", 13), ("rx", "RX (MHz)", 10),
                ("tx", "TX (MHz)", 10), ("sit", "Situação", 46))
        self.tv = ttk.Treeview(meio, columns=[c for c, _, _ in cols], show="headings", selectmode="extended")
        for c, t, w in cols:
            self.tv.heading(c, text=t)
            self.tv.column(c, width=aba.app.largura_texto(w), anchor="w" if c in ("nome", "sit") else "center")
        rol = ttk.Scrollbar(meio, orient="vertical", command=self.tv.yview)
        self.tv.configure(yscrollcommand=rol.set)
        self.tv.pack(side="left", fill="both", expand=True)
        rol.pack(side="right", fill="y")
        tema.configura_tags_tx(self.tv)
        tema.legenda_tx(lc, "TkDefaultFont").pack(fill="x", pady=(6, 0))
        ttk.Label(lc, style="Suave.TLabel", wraplength=940, text=(
            "Bloquear deixa o canal só para recepção (o rádio não transmite nele) e guarda o TX original. "
            "Desbloquear devolve o TX original e marca o canal como exceção, para não ser bloqueado de novo "
            "(útil para frequências comerciais autorizadas). As mudanças vão para o rádio ao clicar em "
            "Gravar no rádio.")).pack(fill="x", pady=(6, 0))

        self.atualiza()

    # faixas
    def _preenche_faixas(self):
        self.tv_f.delete(*self.tv_f.get_children())
        for a, b, d in self.aba.faixas(configuradas=True):
            self.tv_f.insert("", "end", values=(f"{a:g}", f"{b:g}", d))

    def adiciona_faixa(self):
        try:
            a = float(self.n_ini.get().replace(",", "."))
            b = float(self.n_fim.get().replace(",", "."))
            if b < a:
                a, b = b, a
        except ValueError:
            messagebox.showerror("Faixas", "Informe início e fim em MHz (ex.: 144 e 148).", parent=self)
            return
        fx = self.aba.faixas(configuradas=True) + [(a, b, self.n_desc.get().strip() or "Faixa adicional")]
        self.aba.salva_faixas(sorted(fx))
        self.n_ini.set("")
        self.n_fim.set("")
        self.n_desc.set("")
        self.atualiza()

    def remove_faixa(self):
        sel = self.tv_f.selection()
        if not sel:
            return
        i = self.tv_f.index(sel[0])
        fx = self.aba.faixas(configuradas=True)
        del fx[i]
        self.aba.salva_faixas(fx)
        self.atualiza()

    def padrao_faixas(self):
        self.aba.salva_faixas(list(pg.FAIXAS_LIBERADAS_PADRAO))
        self.atualiza()

    def _muda_auto(self):
        self.aba.app.cfg["bloqueio_tx_auto"] = self.auto.get()
        self.aba.app._salva_cfg()

    # canais
    def atualiza(self):
        self._preenche_faixas()
        self.tv.delete(*self.tv.get_children())
        cont = {"pendente": 0, "excecao": 0, "bloqueado": 0}
        prog, fx, exc = self.aba.prog, self.aba.faixas(configuradas=True), self.aba.excecoes()
        for c in prog.canais:
            s = pg.situacao_tx(prog, c, fx, exc)
            if not s:
                continue
            cont[s] += 1
            tx = c.tx if c.duplex != "Sem TX" else pg.tx_original(prog, c)
            txt_tx = pg.mhz(tx) if tx else "-"
            sit = self.SITUACOES[s]
            if s == "bloqueado" and pg.tx_original(prog, c):
                sit += " - TX original guardado"
            self.tv.insert("", "end", iid=str(c.numero), tags=(s,),
                           values=(c.rotulo, c.zona, c.nome, pg.mhz(c.rx), txt_tx, sit))
        self.lbl_resumo.config(text=f"{cont['pendente']} transmitindo fora, {cont['excecao']} exceções, "
                                    f"{cont['bloqueado']} bloqueados")

    def _sel(self):
        return [int(i) for i in self.tv.selection()]

    def bloqueia_sel(self):
        self.aba.bloqueia(self._sel())
        self.atualiza()

    def _lote_radioamador(self, acao):
        self.aba.tx_radioamador(acao)
        self.atualiza()

    def bloqueia_pendentes(self):
        n = self.aba.bloqueia(self.aba.pendentes())
        self.atualiza()
        messagebox.showinfo("Bloqueio", f"TX bloqueado em {n} canal(is).", parent=self)

    def desbloqueia_sel(self):
        erros = self.aba.desbloqueia(self._sel())
        self.atualiza()
        if erros:
            messagebox.showwarning("Desbloqueio", "\n".join(erros[:12]), parent=self)

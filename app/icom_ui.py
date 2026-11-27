# -*- coding: utf-8 -*-
"""Aba "Programação" dos rádios Icom (IC-2730A): canais, bancos, ajustes e ordenação.

'ic' aponta para o módulo do modelo escolhido (hoje só o icom2730). Um modelo novo entra com
um módulo que tenha as mesmas funções e uma linha em MODULOS."""
import os
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from chirp import chirp_common
from chirp import settings as cs

import arrastar
import configuracao_radio as cr
import exportar
import icom2730
import organiza as org
import tema


class _ModeloAtual:
    """Encaminha ic.X para o módulo do rádio Icom escolhido no topo."""
    mod = icom2730

    def __getattr__(self, nome):
        return getattr(self.mod, nome)


ic = _ModeloAtual()
MODULOS = {"IC2730A": icom2730}

COLUNAS = [("num", "Nº", 5), ("nome", "Nome", 10), ("rx", "RX (MHz)", 11), ("duplex", "Duplex", 9),
           ("offset", "Offset/TX", 10), ("tom", "Tom", 13), ("modo", "Modo", 6), ("banco", "Banco", 7),
           ("varr", "Varredura", 11)]
LIMITE_HISTORICO = 50

# Nomes em português dos grupos de ajustes do CHIRP e dos ajustes mais usados
GRUPOS = {"basic": "Básico", "disp": "Visor", "sound": "Sons", "mickey": "Teclas do microfone",
          "dtmf": "Códigos DTMF", "abset": "Bandas A e B", "bluet": "Bluetooth",
          "edges": "Limites de varredura programada", "pslnk": "Varredura vinculada", "other": "Outros"}
AJUSTES_PT = {
    "Squelch/ATT": "Squelch/atenuador", "Squelch Delay": "Atraso do squelch", "PTT Lockout": "Bloqueio do PTT",
    "Busy Channel Lockout": "Bloquear TX com canal ocupado (BCL)", "Tx Timeout": "Tempo máximo de TX",
    "Home VFO (Read-Only)": "VFO inicial (só leitura)", "Home Channel (Read-Only)": "Canal inicial (só leitura)",
    "Microphone Gain": "Ganho do microfone", "Left Bank Initial Mem Chan": "Canal inicial, banda esquerda",
    "Right Bank Initial Mem Chan": "Canal inicial, banda direita", "Comment (16 chars)": "Comentário (16 letras)",
    "Backlight Level": "Brilho da luz de fundo", "Auto Dimmer": "Redução automática do brilho",
    "Auto-Dimmer Timeout (Secs)": "Tempo para reduzir o brilho (s)", "LCD Contrast": "Contraste do visor",
    "Opening Message": "Mensagem ao ligar", "Memory Names": "Mostrar nomes dos canais",
    "Air Band Display": "Visor na banda aérea", "Beep Level": "Volume do bipe", "Home Chan Beep": "Bipe no canal inicial",
    "Key Touch Beep": "Bipe das teclas", "Band Edge Beep": "Bipe no limite da banda",
    "Scan Stop Beep": "Bipe ao parar a varredura", "Sub Band Mute": "Silenciar a banda secundária",
    "DTMF Speed (mSecs)": "Velocidade do DTMF (ms)", "Bluetooth": "Bluetooth", "Auto Connect": "Conectar automaticamente",
}


def _rotulo(nome):
    return AJUSTES_PT.get(nome, nome)


def _num(tv_iid):
    return int(tv_iid)


def _banco_txt(banco, pos):
    if not banco:
        return ""
    return f"{banco} {pos:02d}" if pos is not None else banco


class EditorCanalIcom(tk.Toplevel):
    def __init__(self, aba, numero):
        super().__init__(aba.app.raiz)
        self.aba, self.numero = aba, numero
        r = aba.radio
        rf = r.get_features()
        m = r.get_memory(numero)
        novo = m.empty
        if novo:
            m = chirp_common.Memory(number=numero)
            m.freq = 145000000
        self.m = m
        self.title(f"Canal {numero:03d} ({ic.NOME})")
        self.transient(aba.app.raiz)
        self.resizable(False, False)
        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)
        dup_txt = {k: v for k, v in ic.DUPLEX.items() if k in rf.valid_duplexes}
        if ic.TEM_SPLIT:
            dup_txt["split"] = ic.DUPLEX["split"]
        tom_txt = {k: v for k, v in ic.OPCOES_TOM
                   if k[0] in rf.valid_tmodes and (k[1] is None or k[1] in rf.valid_cross_modes)}
        banco, _ = ic.banco_de(r, numero) if not novo else (None, None)
        self.v = {
            "nome": tk.StringVar(value=m.name.strip()),
            "rx": tk.StringVar(value="" if novo else f"{m.freq / 1e6:.4f}".rstrip("0").rstrip(".")),
            "duplex": tk.StringVar(value=dup_txt.get(m.duplex, "Simplex")),
            "offset": tk.StringVar(value=f"{m.offset / 1e6:.3f}" if m.duplex in ("+", "-", "split") else ""),
            "tmode": tk.StringVar(value=tom_txt.get(ic.opcao_tom(m), "Nenhum")),
            # TSQL e TSQL-R usam o tom de recepção do rádio; na tela fica tudo no campo "Tom"
            "rtone": tk.StringVar(value=f"{(m.ctone if m.tmode in ('TSQL', 'TSQL-R') else m.rtone):.1f}"),
            "ctone": tk.StringVar(value=f"{m.ctone:.1f}"),
            "dtcs": tk.StringVar(value=f"{m.dtcs:03d}"),
            "pol": tk.StringVar(value=m.dtcs_polarity if m.dtcs_polarity in rf.valid_dtcs_pols else "NN"),
            "modo": tk.StringVar(value=m.mode),
            "passo": tk.StringVar(value=str(m.tuning_step)),
            "varr": tk.StringVar(value=ic.PULAR.get(m.skip, "Sim")),
            "banco": tk.StringVar(value=banco or "Nenhum"),
        }
        self._dup = {v: k for k, v in dup_txt.items()}
        self._tom = {v: k for k, v in tom_txt.items()}
        tons = [f"{t:.1f}" for t in chirp_common.TONES]
        linhas = [
            (f"Nome (até {ic.TAM_NOME} letras)", ttk.Entry(f, textvariable=self.v["nome"], width=12)),
            ("Frequência de recepção RX (MHz)", ttk.Entry(f, textvariable=self.v["rx"], width=12)),
            ("Duplex", ttk.Combobox(f, textvariable=self.v["duplex"], values=list(dup_txt.values()),
                                    state="readonly", width=14)),
            ("Offset (MHz) ou frequência de TX", ttk.Entry(f, textvariable=self.v["offset"], width=12)),
            ("Tipo de tom", ttk.Combobox(f, textvariable=self.v["tmode"], values=list(tom_txt.values()),
                                         state="readonly", width=26)),
            ("Tom (Hz)", ttk.Combobox(f, textvariable=self.v["rtone"], values=tons, state="readonly", width=8)),
            ("Tom de RX (Hz)", ttk.Combobox(f, textvariable=self.v["ctone"], values=tons, state="readonly",
                                            width=8)),
            ("Código DCS", ttk.Combobox(f, textvariable=self.v["dtcs"],
                                        values=[f"{c:03d}" for c in chirp_common.DTCS_CODES], state="readonly", width=8)),
            ("Polaridade DCS", ttk.Combobox(f, textvariable=self.v["pol"], values=rf.valid_dtcs_pols,
                                            state="readonly", width=8)),
            ("Modulação", ttk.Combobox(f, textvariable=self.v["modo"], values=rf.valid_modes, state="readonly", width=8)),
            ("Passo de sintonia (kHz)", ttk.Combobox(f, textvariable=self.v["passo"],
                                                     values=[str(x) for x in rf.valid_tuning_steps],
                                                     state="readonly", width=8)),
            ("Varredura", ttk.Combobox(f, textvariable=self.v["varr"],
                                       values=[t for k, t in ic.PULAR.items() if k in rf.valid_skips],
                                       state="readonly", width=14)),
            ("Banco", ttk.Combobox(f, textvariable=self.v["banco"], values=["Nenhum"] + list(ic.NOMES_BANCO),
                                   state="readonly", width=8)),
        ]
        for i, (rot, w) in enumerate(linhas):
            if i == 0 and not ic.TEM_NOME:
                continue                     # rádio sem nome de canal
            ttk.Label(f, text=rot).grid(row=i, column=0, sticky="w", pady=3, padx=(0, 10))
            w.grid(row=i, column=1, sticky="w", pady=3)
        linhas[2][1].bind("<<ComboboxSelected>>", self._sugere_offset)
        # Só ficam ativos os campos que valem para o tipo de tom escolhido
        self._campos_tom = {"rtone": linhas[5], "ctone": linhas[6], "dtcs": linhas[7], "pol": linhas[8]}
        linhas[4][1].bind("<<ComboboxSelected>>", lambda e: self._ajusta_tom())
        self._ajusta_tom()
        n = len(linhas)
        ttk.Label(f, text="Tom TX: o rádio transmite o tom. Tom TX e RX: também só abre o áudio com o tom.\n"
                          "DCS: escolha o código e a polaridade (NN é a normal).\n"
                          + ("Duplex + ou - usam o offset; \"TX separado\" usa o campo como frequência de TX."
                             if ic.TEM_SPLIT else "Duplex + ou - usam o offset."),
                  style="Suave.TLabel", justify="left").grid(row=n, column=0, columnspan=2, sticky="w", pady=(8, 4))
        bt = ttk.Frame(f)
        bt.grid(row=n + 1, column=0, columnspan=2, pady=(8, 0), sticky="e")
        if not novo:
            ttk.Button(bt, text="Apagar canal", command=self.apagar).pack(side="left", padx=4)
        ttk.Button(bt, text="Cancelar", command=self.destroy).pack(side="left", padx=4)
        ttk.Button(bt, text="Salvar", command=self.salvar).pack(side="left", padx=4)
        self.bind("<Return>", lambda e: self.salvar())
        self.bind("<Escape>", lambda e: self.destroy())
        linhas[0 if ic.TEM_NOME else 1][1].focus_set()
        self.update_idletasks()
        rz = aba.app.raiz
        x = rz.winfo_rootx() + (rz.winfo_width() - self.winfo_reqwidth()) // 2
        y = rz.winfo_rooty() + (rz.winfo_height() - self.winfo_reqheight()) // 3
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
        self.grab_set()

    def _ajusta_tom(self):
        ativos = ic.CAMPOS_TOM.get(self._tom.get(self.v["tmode"].get(), ("", None)), ())
        for chave, (rotulo, w) in self._campos_tom.items():
            w.state(["!disabled", "readonly"] if chave in ativos else ["disabled"])

    def _sugere_offset(self, *_):
        d = self._dup.get(self.v["duplex"].get(), "")
        if d in ("+", "-") and not self.v["offset"].get().strip():
            try:
                f = float(self.v["rx"].get().replace(",", "."))
            except ValueError:
                return
            self.v["offset"].set("0.600" if f < 300 else "5.000")

    @staticmethod
    def _hz(txt):
        txt = txt.strip().replace(",", ".")
        if not txt:
            raise ic.ErroIcom("Informe a frequência.")
        try:
            return chirp_common.parse_freq(txt)
        except Exception as e:
            raise ic.ErroIcom(f"Frequência inválida: {txt}") from e

    def salvar(self):
        r = self.aba.radio
        try:
            m = self.m.dupe()
            m.number = self.numero
            m.empty = False
            nome = self.v["nome"].get().strip().upper() if ic.TEM_NOME else ""
            if len(nome) > ic.TAM_NOME:
                raise ic.ErroIcom(f"O nome pode ter no máximo {ic.TAM_NOME} letras.")
            m.name = nome
            m.freq = self._hz(self.v["rx"].get())
            m.duplex = self._dup.get(self.v["duplex"].get(), "")
            if m.duplex in ("+", "-", "split"):
                m.offset = self._hz(self.v["offset"].get())
            m.tmode, cruzado = self._tom.get(self.v["tmode"].get(), ("", None))
            if cruzado:
                m.cross_mode = cruzado
            if m.tmode in ("TSQL", "TSQL-R"):
                m.ctone = float(self.v["rtone"].get())
            else:
                m.rtone = float(self.v["rtone"].get())
                m.ctone = float(self.v["ctone"].get())
            m.dtcs = int(self.v["dtcs"].get())
            m.dtcs_polarity = self.v["pol"].get()
            m.mode = self.v["modo"].get()
            m.tuning_step = float(self.v["passo"].get())
            m.skip = {v: k for k, v in ic.PULAR.items()}[self.v["varr"].get()]
            avisos = ic.valida(r, m)
            if m.duplex == "split" and m.offset and not any(a <= m.offset <= b for a, b in r.get_features().valid_bands):
                raise ic.ErroIcom("A frequência de TX está fora das faixas do rádio.")
        except (ic.ErroIcom, ValueError) as e:
            messagebox.showerror("Canal", str(e), parent=self)
            return
        if avisos and not messagebox.askyesno("Canal", "\n".join(avisos) + "\n\nSalvar assim mesmo?", parent=self):
            return
        try:
            r.set_memory(m)
            banco = self.v["banco"].get()
            atual, _ = ic.banco_de(r, self.numero)
            if banco == "Nenhum":
                ic.define_banco(r, self.numero, None)
            elif banco != atual:
                ic.define_banco(r, self.numero, banco)
        except Exception as e:           # recusa do driver: o canal não muda e o motivo aparece
            messagebox.showerror("Canal", f"O rádio não aceita este canal: {e}", parent=self)
            self.aba.alterado()
            return
        self.aba.alterado()
        self.destroy()

    def apagar(self):
        org.apaga(org.Icom(self.aba.radio, ic), [self.numero])
        self.aba.alterado()
        self.destroy()


class AbaIcom:
    def __init__(self, app, pai):
        self.app, self.pai = app, pai
        self.radio = None
        self.origem = ""
        self.modificado = False
        self.copia = None
        self.historico, self.pos_historico = [], -1
        self.base_gravacao = None
        self.salvo_estado = None
        self.cabecalho = dict(ic.CABECALHO_PADRAO)
        self._estados = {}

        barra = tema.barra_comandos(pai)
        self.bt_ler = tema.botao(barra, "Ler rádio", self.ler, "download", "TButton")
        self.bt_ler.pack(side="left", padx=(0, 8))
        self.bt_gravar = tema.botao(barra, "Gravar no rádio", self.gravar, "upload", "Gravar.TButton")
        self.bt_gravar.pack(side="left", padx=(0, 20))
        app.botoes_ocupado += [self.bt_ler, self.bt_gravar]
        self.mb_arquivo = ttk.Menubutton(barra, text="Arquivo", width=9)
        self.menu_arquivo = tema.MenuDesenhado(app.raiz)
        self._monta_menu_arquivo()
        self.menu_arquivo.anexa(self.mb_arquivo)
        self.mb_arquivo.pack(side="left")
        app.botoes_ocupado.append(self.mb_arquivo)
        app.botoes_ocupado += tema.botoes_historico(barra, self.desfazer, self.refazer)
        self.info = tema.LinhaArquivo(pai)
        self.caminho = ""

        self.nb = ttk.Notebook(pai, style="Semabas.TNotebook")
        self.nb.pack(fill="both", expand=True)
        tema.titulo_do_caderno(pai, self.nb, app.fonte_titulo)
        self.f_canais = ttk.Frame(self.nb)
        self.f_bancos = ttk.Frame(self.nb)
        self.f_ajustes = ttk.Frame(self.nb)
        self.nb.add(self.f_canais, text="Canais")
        self.nb.add(self.f_bancos, text="Bancos")
        self.nb.add(self.f_ajustes, text="Ajustes do rádio")
        self._monta_canais()
        self._atualiza_tudo()

    def _monta_menu_arquivo(self):
        m = self.menu_arquivo
        m.limpa()
        m.add_command(label=f"Abrir arquivo {ic.EXTENSAO}...", command=self.abrir)
        m.add_command(label=f"Salvar como {ic.EXTENSAO}...", command=self.salvar)
        m.add_separator()
        m.add_command(label="Exportar a lista de canais (PDF ou CSV)...", command=self.exportar)
        m.add_separator()
        m.add_command(label="Abrir a pasta de backups", command=self.app.abre_pasta_backup)

    _ESTADO = ("radio", "origem", "modificado", "historico", "pos_historico", "copia", "base_gravacao",
               "salvo_estado", "cabecalho")

    def _monta_menu_ordenar(self):
        org.monta_menu(self.menu_ordenar, self.ordenar, ic.TEM_NOME)

    def define_modelo(self, chave):
        """Troca o rádio Icom. A programação de cada modelo fica guardada
        e volta quando o modelo é escolhido de novo."""
        mod = MODULOS.get(chave, icom2730)
        if mod is ic.mod:
            return
        if self.modificado:
            self.salva_rascunho()            # alterações do outro modelo ficam também no rascunho
        self._estados[ic.CHAVE] = {k: getattr(self, k) for k in self._ESTADO}
        ic.mod = mod
        novo = self._estados.get(ic.CHAVE)
        if novo:
            for k, v in novo.items():
                setattr(self, k, v)
        else:
            self.radio, self.origem, self.modificado = None, "", False
            self.historico, self.pos_historico, self.copia = [], -1, None
            self.base_gravacao = self.salvo_estado = None
            self.cabecalho = dict(ic.CABECALHO_PADRAO)
        self._monta_menu_arquivo()
        self._monta_menu_ordenar()
        self.tv["displaycolumns"] = [c for c, _, _ in COLUNAS if c != "nome" or ic.TEM_NOME]
        self.nb.tab(self.f_ajustes, state="normal" if ic.TEM_AJUSTES else "hidden")
        self._atualiza_tudo()

    # ------------------------------------------------------------------ canais
    def _monta_canais(self):
        topo = ttk.Frame(self.f_canais, padding=(16, 10, 16, 10))
        topo.pack(fill="x")
        self._topo = topo
        self.busca = tk.StringVar()
        campo, _ent = tema.campo_busca(topo, self.busca, "Buscar nome, número ou frequência")
        campo.pack(side="left")
        self.busca.trace_add("write", lambda *_: self._preenche_tabela())
        self.so_ocupados = tk.BooleanVar(value=True)
        ttk.Checkbutton(topo, text="Somente canais preenchidos", variable=self.so_ocupados,
                        command=self._preenche_tabela).pack(side="left", padx=14)
        b = tema.botao(topo, "Novo canal", self.novo_canal, "plus")
        b.pack(side="left", padx=(0, 8))
        self.app.botoes_ocupado.append(b)
        self.mb_ordenar = ttk.Menubutton(topo, text="Ordenar canais")
        self.menu_ordenar = tema.MenuDesenhado(self.app.raiz)
        self._monta_menu_ordenar()
        self.menu_ordenar.anexa(self.mb_ordenar)
        self.mb_ordenar.pack(side="left", padx=(4, 0))
        self.app.botoes_ocupado.append(self.mb_ordenar)
        ttk.Label(self.f_canais, text="Arraste um canal para mudar a ordem  ·  botão direito: mais opções",
                  style="Suave.TLabel").pack(side="bottom", anchor="w", padx=16, pady=(0, 8), before=topo)
        tema.fluxo(topo)
        meio = ttk.Frame(self.f_canais)
        meio.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        self.tv = ttk.Treeview(meio, columns=[c for c, _, _ in COLUNAS], show="headings", selectmode="extended")
        for c, t, w in COLUNAS:
            self.tv.heading(c, text=t, anchor="w" if c == "nome" else "center")
            self.tv.column(c, width=self.app.largura_texto(w), minwidth=self.app.largura_texto(w),
                           anchor="w" if c == "nome" else "center", stretch=c == "varr")
        rol = ttk.Scrollbar(meio, orient="vertical", command=self.tv.yview)
        rolh = ttk.Scrollbar(meio, orient="horizontal", command=self.tv.xview)
        self.tv.configure(yscrollcommand=rol.set, xscrollcommand=tema.rolagem_automatica(rolh))
        self.tv.grid(row=0, column=0, sticky="nsew")
        rol.grid(row=0, column=1, sticky="ns")
        rolh.grid(row=1, column=0, sticky="ew")
        meio.rowconfigure(0, weight=1)
        meio.columnconfigure(0, weight=1)
        tema.configura_tags_tx(self.tv)
        tema.memoriza_colunas(self.tv, self.app.cfg, "icom", self.app._salva_cfg)
        self.arraste = arrastar.ArrastaLinhas(
            self.tv, self._soltou, pode=lambda: bool(self.radio) and not self.app.ocupado
            and not self.busca.get().strip(),
            aviso=lambda: self.app.status.config(text="Para arrastar canais, limpe a busca (Esc)."))
        arrastar.liga_setas(self.tv, self._soltou, pode=lambda: bool(self.radio) and not self.app.ocupado
                            and not self.busca.get().strip())
        self.menu_canal = tema.MenuDesenhado(self.app.raiz)
        for rot, fn in [("Editar...", self.editar), ("Copiar", self.copiar), ("Recortar", self.recortar),
                        ("Colar", self.colar), (None, None), ("Apagar", self.apagar)]:
            if rot is None:
                self.menu_canal.add_separator()
            else:
                self.menu_canal.add_command(label=rot, command=fn)
        for botao in ("<Button-3>", "<Button-2>"):
            self.tv.bind(botao, self._menu)
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
        """Abre o editor no canal vazio selecionado ou, sem um, no primeiro canal vazio."""
        if not self._exige():
            return
        sel = [n for n in self._selecionados() if self.radio.get_memory(n).empty]
        n = sel[0] if sel else next((k for k in range(ic.TOTAL_CANAIS) if self.radio.get_memory(k).empty), None)
        if n is None:
            messagebox.showinfo("Canais", "Não há canal vazio. Apague um canal para criar outro.")
            return
        EditorCanalIcom(self, n)

    def ajusta_colunas(self):
        for c, _, w in COLUNAS:
            self.tv.column(c, width=self.app.largura_texto(w), minwidth=self.app.largura_texto(w))

    def _menu(self, ev):
        if not self.radio or self.app.ocupado:
            return
        linha = self.tv.identify_row(ev.y)
        if linha and linha not in self.tv.selection():
            self.tv.selection_set(linha)
        self.tv.focus_set()
        self.menu_canal.tk_popup(ev.x_root, ev.y_root)

    def _preenche_tabela(self):
        sel = self.tv.selection()
        self.tv.delete(*self.tv.get_children())
        if not self.radio:
            return
        termo = self.busca.get().strip().casefold().replace(",", ".")
        for n in range(ic.TOTAL_CANAIS):
            m = self.radio.get_memory(n)
            zebra = ("zebra",) if n % 2 else ()
            if m.empty:
                if self.so_ocupados.get():
                    continue
                if termo and termo not in f"{n:03d}":
                    continue
                self.tv.insert("", "end", iid=str(n), values=(f"{n:03d}", "(vazio)") + ("",) * 7,
                               tags=("vazio",) + zebra)
                continue
            rx = f"{m.freq / 1e6:.4f}"[:-1] if m.freq % 1000 == 0 else f"{m.freq / 1e6:.4f}"
            if m.duplex in ("+", "-"):
                off = f"{m.offset / 1e6:.3f}"
            elif m.duplex == "split":
                off = f"{m.offset / 1e6:.3f}"
            else:
                off = ""
            if termo and termo not in f"{n:03d} {m.name} {rx} {off}".casefold():
                continue
            banco, pos = ic.banco_de(self.radio, n)
            self.tv.insert("", "end", iid=str(n), tags=zebra, values=(
                f"{n:03d}", m.name.strip(), rx, ic.DUPLEX.get(m.duplex, m.duplex), off, ic.descreve_tom(m),
                m.mode, _banco_txt(banco, pos), ic.PULAR.get(m.skip, m.skip)))
        tema.zebra(self.tv)
        sel = [s for s in sel if self.tv.exists(s)]
        if sel:
            self.tv.selection_set(sel)

    def _selecionados(self):
        return [_num(i) for i in self.tv.selection()]

    def _exige(self):
        if self.app.ocupado:
            return False
        if not self.radio:
            messagebox.showinfo("Programação", f"Primeiro clique em Ler rádio ou abra um arquivo {ic.EXTENSAO}.")
            return False
        return True

    def editar(self):
        if not self._exige():
            return
        sel = self._selecionados()
        if not sel:
            messagebox.showinfo("Canais", "Selecione um canal na lista.")
            return
        EditorCanalIcom(self, sel[0])

    def apagar(self):
        if not self._exige():
            return
        sel = [n for n in self._selecionados() if not self.radio.get_memory(n).empty]
        if sel and messagebox.askyesno("Canais", f"Apagar {len(sel)} canal(is)?"):
            org.apaga(org.Icom(self.radio, ic), sel)
            self.alterado()

    def recortar(self):
        if not self._exige():
            return
        sel = [n for n in self._selecionados() if not self.radio.get_memory(n).empty]
        if not sel:
            return
        self.copiar()
        org.apaga(org.Icom(self.radio, ic), sel)
        self.alterado()
        self.app.status.config(text=f"{len(sel)} canal(is) recortado(s). Use Colar para colocá-los em outro lugar.")

    def copiar(self):
        if self.radio:
            self.copia = [(self.radio.get_memory(n), ic.banco_de(self.radio, n)[0])
                          for n in self._selecionados() if not self.radio.get_memory(n).empty]
            self.app.status.config(text=f"{len(self.copia)} canal(is) copiado(s).")

    def colar(self):
        if self.app.ocupado or not self.radio or not self.copia:
            return
        sel = self._selecionados()
        if not sel:
            return
        inicio = min(sel)
        if inicio + len(self.copia) > ic.TOTAL_CANAIS:
            messagebox.showinfo("Canais", "Os canais copiados não cabem a partir do canal selecionado.")
            return
        ocupados = [inicio + i for i in range(len(self.copia)) if not self.radio.get_memory(inicio + i).empty]
        if ocupados and not messagebox.askyesno("Canais", f"Substituir {len(ocupados)} canal(is) já ocupado(s)?"):
            return
        for i, (m, banco) in enumerate(self.copia):
            novo = m.dupe()
            novo.number = inicio + i
            self.radio.set_memory(novo)
            ic.define_banco(self.radio, novo.number, banco)
        self.alterado()

    def _soltou(self, sel, alvo, depois):
        nums = [int(i) for i in sel]
        mapa = ic.move(self.radio, nums, int(alvo), depois)
        if not mapa:
            return
        self.alterado()
        novos = [str(mapa[n]) for n in nums if n in mapa and self.tv.exists(str(mapa[n]))]
        if novos:
            self.tv.selection_set(novos)
            self.tv.see(novos[0])
        self.app.status.config(text=f"{len(nums)} canal(is) movido(s) para a posição {mapa[nums[0]]:03d}.")

    def exportar(self):
        if not self._exige():
            return
        colunas = ["Nº", "Nome", "RX (MHz)", "Duplex", "Offset/TX", "Tom", "Modo", "Banco", "Varredura"]
        linhas = []
        for n in range(ic.TOTAL_CANAIS):
            m = self.radio.get_memory(n)
            if m.empty:
                continue
            off = f"{m.offset / 1e6:.3f}" if m.duplex in ("+", "-", "split") else ""
            banco, pos = ic.banco_de(self.radio, n)
            linhas.append([f"{n:03d}", m.name.strip(), f"{m.freq / 1e6:.4f}".rstrip("0").rstrip(".")
                           if m.freq % 1000 else f"{m.freq / 1e6:.3f}", ic.DUPLEX.get(m.duplex, m.duplex), off,
                           ic.descreve_tom(m), m.mode, _banco_txt(banco, pos),
                           ic.PULAR.get(m.skip, m.skip)])
        sub = (cr.INDICATIVO + "  ·  " if cr.INDICATIVO else "") + self.origem
        if not ic.TEM_NOME:
            colunas.pop(1)
            linhas = [l[:1] + l[2:] for l in linhas]
        exportar.exporta(self.app, f"Canais_{ic.CHAVE}{cr.sufixo_arquivo()}", f"Canais do Icom {ic.NOME}", sub,
                         colunas, linhas)

    def ordenar(self, por):
        if not self._exige():
            return
        ad = org.Icom(self.radio, ic)
        if not org.ordena(ad, ad.faixas()[0], por):
            self.app.status.config(text="Os canais já estavam nessa ordem.")
            return
        self.alterado()
        self.tv.yview_moveto(0)
        self.app.status.config(text="Canais ordenados por " + ("nome." if por == org.POR_NOME else "frequência."))

    # ------------------------------------------------------------------ bancos
    def _monta_bancos(self):
        for w in self.f_bancos.winfo_children():
            w.destroy()
        if not self.radio:
            ttk.Label(self.f_bancos, text="Leia o rádio ou abra um arquivo primeiro.").pack(padx=10, pady=10)
            return
        ttk.Label(self.f_bancos, text="O rádio tem 10 bancos (A a J)."
                  + (" Dê um nome a cada um (até 6 letras)." if ic.BANCO_COM_NOME else "")
                  + " Para pôr um canal num banco, edite o canal.",
                  style="Suave.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", padx=10, pady=8)
        nomes = ic.nomes_bancos(self.radio) if ic.BANCO_COM_NOME else None
        contagem = {l: 0 for l in ic.NOMES_BANCO}
        for n in range(ic.TOTAL_CANAIS):
            b, _ = ic.banco_de(self.radio, n)
            if b and not self.radio.get_memory(n).empty:
                contagem[b] += 1
        for i, letra in enumerate(ic.NOMES_BANCO):
            ttk.Label(self.f_bancos, text=f"Banco {letra}:").grid(row=i + 1, column=0, sticky="w", padx=10, pady=3)
            if nomes is None:
                ttk.Label(self.f_bancos, text=f"{contagem[letra]} canal(is)", style="Suave.TLabel").grid(
                    row=i + 1, column=1, sticky="w", padx=10)
                continue
            v = tk.StringVar(value=nomes[i])
            vc_ = (self.f_bancos.register(lambda t: len(t) <= 6), "%P")
            ttk.Entry(self.f_bancos, textvariable=v, width=10, validate="key", validatecommand=vc_).grid(
                row=i + 1, column=1, sticky="w", pady=3)
            ttk.Label(self.f_bancos, text=f"{contagem[letra]} canal(is)", style="Suave.TLabel").grid(
                row=i + 1, column=2, sticky="w", padx=10)
            v.trace_add("write", lambda *_a, ii=i, vv=v: self._muda_banco(ii, vv))

    def _muda_banco(self, i, v):
        ic.define_nome_banco(self.radio, i, v.get())
        self._registra_edicao()
        self._atualiza_origem()

    # ----------------------------------------------------------------- ajustes
    def _monta_ajustes(self):
        for w in self.f_ajustes.winfo_children():
            w.destroy()
        if not self.radio:
            ttk.Label(self.f_ajustes, text="Leia o rádio ou abra um arquivo primeiro.").pack(padx=10, pady=10)
            return
        self._vars_ajuste = []
        try:
            self.ajustes = self.radio.get_settings()
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
        ttk.Label(area, text="Alguns nomes de ajustes ainda estão em inglês.",
                  style="Suave.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", padx=8, pady=(6, 0))
        for i, grupo in enumerate(self.ajustes):
            lf = ttk.LabelFrame(area, text=GRUPOS.get(grupo.get_name(), grupo.get_shortname()), padding=8)
            lf.grid(row=1 + i // 2, column=i % 2, sticky="nsew", padx=8, pady=6)
            for r, el in enumerate(self._itens(grupo)):
                self._widget_ajuste(lf, r, el)

    def _itens(self, grupo):
        for el in grupo:
            if isinstance(el, cs.RadioSetting):
                yield el
            elif isinstance(el, cs.RadioSettingGroup):
                yield from self._itens(el)

    def _widget_ajuste(self, lf, r, el):
        valor = el.value
        rot = _rotulo(el.get_shortname())
        ativo = valor.get_mutable()
        estado = "normal" if ativo else "disabled"
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
                w = ttk.Combobox(lf, textvariable=v, values=opcoes, state="readonly" if ativo else "disabled",
                                 width=max(6, min(22, max((len(o) for o in opcoes), default=6) + 2)))
            else:
                v = tk.StringVar(value=str(valor.get_value()).rstrip() if isinstance(
                    valor, cs.RadioSettingValueString) else str(valor.get_value()))
                w = ttk.Entry(lf, textvariable=v, width=14, state=estado)
                w.bind("<Return>", lambda e: self.app.raiz.focus_set())
            w.grid(row=r, column=1, sticky="w", pady=2)
        self._vars_ajuste.append(v)          # sem referência, o Tk perde o valor dos campos só de leitura
        if ativo:
            v.trace_add("write", lambda *_a, e=el, vv=v: self._muda_ajuste(e, vv))

    def _muda_ajuste(self, el, v):
        valor = el.value
        try:
            x = v.get()
            if isinstance(valor, cs.RadioSettingValueInteger):
                x = int(x)
            elif isinstance(valor, cs.RadioSettingValueFloat):
                x = float(str(x).replace(",", "."))
            valor.set_value(x)
            self.radio.set_settings(self.ajustes)
        except Exception as e:
            self.app.status.config(text=f"{_rotulo(el.get_shortname())}: valor não aceito ({e}).")
            return
        self._registra_edicao()
        self._atualiza_origem()

    # ------------------------------------------------------------------ estado
    def _atualiza_origem(self):
        if not self.radio:
            self.info.mostra("Nenhuma programação carregada.")
            return
        self.info.mostra(self.origem, f"{tema.plural(len(ic.usados(self.radio)), 'canal', 'canais')} em uso de {ic.TOTAL_CANAIS}",
                         self.modificado, self.caminho)

    def alterado(self):
        self._registra_edicao()
        self._preenche_tabela()
        self._monta_bancos()
        self._atualiza_origem()

    def _atualiza_tudo(self):
        tema.alterna_inicio(self.aviso, self._topo, self.tv.master, not self.radio)
        self._preenche_tabela()
        self._monta_bancos()
        self._monta_ajustes()
        self._atualiza_origem()

    def carrega(self, radio, origem):
        self.radio = radio
        self.cabecalho = dict(getattr(radio, "_icf_data", ic.CABECALHO_PADRAO))
        self.origem = origem
        self.caminho = ""
        self.modificado = False
        dados = ic.imagem(radio)
        self.base_gravacao = dados
        self.historico = [dados]
        self.pos_historico = 0
        self.salvo_estado = dados
        self._atualiza_tudo()

    def _registra_edicao(self):
        if not self.radio:
            return
        dados = ic.imagem(self.radio)
        if self.pos_historico < 0 or dados != self.historico[self.pos_historico]:
            self.historico = self.historico[:self.pos_historico + 1] + [dados]
            self.historico = self.historico[-(LIMITE_HISTORICO + 1):]
            self.pos_historico = len(self.historico) - 1
        self.modificado = dados != self.salvo_estado

    def _historico_move(self, d):
        if self.app.ocupado or not self.radio:
            return
        destino = self.pos_historico + d
        if not 0 <= destino < len(self.historico):
            return
        self.pos_historico = destino
        self.radio = ic.radio_de_bytes(self.historico[destino], self.cabecalho)
        self.modificado = self.historico[destino] != self.salvo_estado
        self._atualiza_tudo()

    def desfazer(self):
        self._historico_move(-1)

    def refazer(self):
        self._historico_move(1)

    def _confirma_descartar(self):
        return (not self.modificado or messagebox.askyesno(
            "Programação", "Há alterações não gravadas na programação atual. Descartar?"))

    def arquivo_rascunho(self):
        return os.path.join(self.app.pasta_rascunhos(), f"Rascunho_programacao_{ic.CHAVE}{ic.EXTENSAO}")

    def salva_rascunho(self):
        if self.radio and self.modificado:
            ic.salva_arquivo(self.radio, self.arquivo_rascunho())

    def remove_rascunho(self):
        try:
            os.unlink(self.arquivo_rascunho())
        except FileNotFoundError:
            pass

    # ------------------------------------------------------------ rádio/arquivo
    def _nome_backup(self, prefixo):
        return os.path.join(self.app.pasta_backup(),
                            f"{prefixo}_{time.strftime('%Y-%m-%d_%H-%M-%S')}_{ic.CHAVE}{cr.sufixo_arquivo()}"
                            f"{ic.EXTENSAO}")

    def ler(self):
        porta = self.app.porta.get().strip()
        if not porta:
            messagebox.showerror("Programação", "Escolha a porta COM do cabo de programação.")
            return
        if not self._confirma_descartar():
            return
        res = {}
        cab = dict(self.cabecalho)

        def tarefa():
            r = ic.le(porta, progresso=self.app.progresso, cabecalho=cab)
            destino = self._nome_backup("Config")
            ic.salva_arquivo(r, destino)
            res.update(radio=r, arq=destino)

        def fim():
            self.carrega(res["radio"], f"Lido do rádio às {time.strftime('%H:%M')}")
            self.app.status.config(text=f"Rádio lido. Backup automático: {os.path.basename(res['arq'])}")
        self.app.executa("Lendo o rádio...", tarefa, depois=fim)

    def gravar(self):
        if not self._exige():
            return
        porta = self.app.porta.get().strip()
        if not porta:
            messagebox.showerror("Programação", "Escolha a porta COM do cabo de programação.")
            return
        com_backup = bool(self.app.cfg.get("backup_antes_gravar", False))
        if not messagebox.askyesno(
                "Gravar no rádio", f"Gravar no {ic.NOME} a programação atual ({tema.plural(len(ic.usados(self.radio)), 'canal', 'canais')} "
                                   "em uso)? Ela substitui a que está no rádio."):
            return
        radio = ic.radio_de_bytes(ic.imagem(self.radio), self.cabecalho)
        res = {}
        # registro da conversa com o rádio, na pasta de backups (para diagnóstico)
        registro = os.path.splitext(self._nome_backup("Registro_gravacao"))[0] + ".txt"

        def tarefa():
            def salva_copia(atual):
                destino = self._nome_backup("Antes_gravar")
                ic.salva_arquivo(atual, destino)
                res["bkp"] = destino
            if com_backup:
                ic.le_e_grava(porta, radio, progresso=self.app.progresso, apos_leitura=salva_copia,
                              registro=registro)
            else:
                ic.grava(porta, radio, progresso=self.app.progresso, registro=registro)

        def fim():
            self.base_gravacao = ic.imagem(radio)
            self.salvo_estado = self.base_gravacao
            self.modificado = False
            self.remove_rascunho()
            self._atualiza_origem()
            self.app.status.config(text="Programação gravada no rádio." + (
                f" Cópia de antes da gravação: {os.path.basename(res['bkp'])}" if res.get("bkp") else ""))
        self.app.executa("Gravando no rádio...", tarefa, depois=fim, nota=tema.NOTA_GRAVACAO)

    def abrir(self, caminho=None):
        if not self._confirma_descartar():
            return
        caminho = caminho or filedialog.askopenfilename(
            title=f"Abrir programação do {ic.NOME}", initialdir=self.app.pasta_backup(),
            filetypes=[ic.TIPO_ARQUIVO, ("Todos", "*.*")])
        if not caminho:
            return
        try:
            r = ic.abre_arquivo(caminho)
        except Exception as e:
            messagebox.showerror("Programação", str(e))
            return
        self.carrega(r, f"Arquivo: {os.path.basename(caminho)}")
        self.caminho = caminho
        self._atualiza_origem()

    def salvar(self):
        if not self._exige():
            return
        caminho = filedialog.asksaveasfilename(
            title=f"Salvar programação do {ic.NOME}", defaultextension=ic.EXTENSAO,
            initialfile=f"{ic.CHAVE}{cr.sufixo_arquivo()}{ic.EXTENSAO}",
            filetypes=[ic.TIPO_ARQUIVO])
        if not caminho:
            return
        try:
            ic.salva_arquivo(self.radio, caminho)
        except Exception as e:
            messagebox.showerror("Programação", f"Não foi possível salvar: {e}")
            return
        self.origem = f"Arquivo: {os.path.basename(caminho)}"
        self.caminho = caminho
        self.salvo_estado = ic.imagem(self.radio)
        self.modificado = False
        self.remove_rascunho()
        self._atualiza_origem()
        return True

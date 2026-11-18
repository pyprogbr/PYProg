# -*- coding: utf-8 -*-
"""Página "Imagem de abertura"."""
import os

from arquivos import RegistroEnvio
import tkinter as tk
import ajuda
from tkinter import colorchooser, filedialog, messagebox, ttk

import configuracao_radio as cr
import imagem_abertura as ia
import tema

ESCALA = 2


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(rgb)


class AbaImagem:
    def __init__(self, app, pai):
        self.app = app
        self.origem = None      # imagem original escolhida (PIL)
        self.final = None       # no tamanho da tela do modelo, pronta para enviar
        self._de_texto = False
        self._modelo = "UV17ProGPS"
        self.foto = None
        self.cores = {"fundo": (0, 32, 96), "texto": (255, 255, 255), "destaque": (255, 210, 0)}

        pagina = ttk.Frame(pai)
        pagina.pack(fill="both", expand=True)
        pagina.rowconfigure(0, weight=1)
        pagina.columnconfigure(0, weight=1)
        self.area = tk.Canvas(pagina, highlightthickness=0, bd=0,
                              bg=tema.C["fundo"])
        self.area.grid(row=0, column=0, sticky="nsew")
        rol = ttk.Scrollbar(pagina, orient="vertical", command=self.area.yview)
        rol.grid(row=0, column=1, sticky="ns")
        self.rol_horizontal = ttk.Scrollbar(pagina, orient="horizontal", command=self.area.xview)
        self.rol_horizontal.grid(row=1, column=0, sticky="ew")
        self.rol_horizontal.grid_remove()
        self.area.configure(yscrollcommand=rol.set, xscrollcommand=self.rol_horizontal.set)
        self.corpo = corpo = ttk.Frame(self.area, padding=(16, 12))
        self.janela_conteudo = self.area.create_window((0, 0), window=corpo, anchor="nw")
        self._empilhado = None
        self._horizontal_visivel = False
        corpo.bind("<Configure>", self._sincroniza_rolagem)
        self.area.bind("<Configure>", self._ajusta_pagina)
        ttk.Label(corpo, text="Imagem exibida ao ligar o rádio", style="Titulo.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w")
        self.descricao = ttk.Label(corpo, style="Suave.TLabel", text=self._texto_descricao(), wraplength=1100)
        self.descricao.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 12))

        # Prévia
        self.painel_previa = esq = ttk.LabelFrame(corpo, text="Prévia no visor", padding=14)
        esq.grid(row=2, column=0, sticky="nw", padx=(0, 16))
        moldura = tk.Frame(esq, bg=tema.C["lateral"], padx=10, pady=10)
        moldura.pack()
        self.tela = tk.Canvas(moldura, width=ia.LARGURA * ESCALA, height=ia.ALTURA * ESCALA,
                              highlightthickness=0, bg="#000000")
        self.tela.pack()
        ttk.Label(esq, style="Suave.TLabel", text="Mostrada em tamanho duplo, já com as\ncores reduzidas "
                                                   "como no rádio.").pack(pady=(8, 0))
        bts = ttk.Frame(esq)
        bts.pack(fill="x", pady=(12, 0))
        self.bt_enviar = ttk.Button(bts, text="Enviar imagem ao rádio", style="Gravar.TButton", command=self.enviar)
        self.bt_enviar.pack(fill="x")
        app.botoes_ocupado.append(self.bt_enviar)
        ttk.Button(bts, text="Salvar como BMP...", command=self.salvar_bmp).pack(fill="x", pady=(6, 0))
        ajuda.botao(bts, "imagem").pack(anchor="e", pady=(6, 0))

        # Opções
        self.painel_opcoes = dir_ = ttk.Frame(corpo)
        dir_.grid(row=2, column=1, sticky="nsew")
        corpo.columnconfigure(1, weight=1)

        self.opcoes_arquivo = o1 = ttk.LabelFrame(dir_, text="1. Imagem do computador", padding=12)
        o1.pack(fill="x")
        ttk.Button(o1, text="Abrir imagem do computador...", command=self.abrir).grid(row=0, column=0, sticky="w")
        ttk.Label(o1, text="Encaixe:").grid(row=1, column=0, sticky="w", pady=(10, 0))
        self.modo = tk.StringVar(value=ia.MODOS[0])
        cb = ttk.Combobox(o1, textvariable=self.modo, values=ia.MODOS, state="readonly", width=22)
        cb.grid(row=1, column=1, sticky="w", padx=(16, 6), pady=(10, 0))
        cb.bind("<<ComboboxSelected>>", lambda e: self._aplica())
        ajuda.botao(o1, "encaixe").grid(row=1, column=2, sticky="w", pady=(10, 0))

        self.opcoes_texto = o2 = ttk.LabelFrame(dir_, text="2. Ou crie uma tela com texto", padding=12)
        o2.pack(fill="x", pady=(12, 0))
        self.linhas = [tk.StringVar(value=cr.INDICATIVO), tk.StringVar(), tk.StringVar()]
        for i, (rot, v) in enumerate(zip(("Linha 1 (destaque)", "Linha 2", "Linha 3"), self.linhas)):
            ttk.Label(o2, text=rot).grid(row=i, column=0, sticky="w", pady=3)
            ttk.Entry(o2, textvariable=v, width=28).grid(row=i, column=1, sticky="w", padx=(16, 0), pady=3)
        cores = ttk.Frame(o2)
        cores.grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.amostras = {}
        for chave, rot in (("fundo", "Cor do fundo"), ("destaque", "Cor da linha 1"), ("texto", "Cor das outras")):
            b = tk.Label(cores, width=3, bg=_hex(self.cores[chave]), relief="solid", bd=1, cursor="hand2")
            b.pack(side="left")
            b.bind("<Button-1>", lambda e, k=chave: self.escolhe_cor(k))
            self.amostras[chave] = b
            ttk.Label(cores, text=rot).pack(side="left", padx=(4, 14))
        ttk.Button(o2, text="Criar imagem", command=self.criar_texto).grid(row=4, column=0, sticky="w", pady=(10, 0))

        o3 = ttk.LabelFrame(dir_, text="Observações", padding=12)
        o3.pack(fill="x", pady=(12, 0))
        self.observacoes = ttk.Label(o3, wraplength=560, justify="left", anchor="nw", text=(
            "Em Programação > Ajustes do rádio > Visor, deixe \"Tela ao ligar\" em \"Logotipo\". "
            "O tempo de exibição da imagem é fixo no firmware e não pode ser alterado pelo cabo.\n\n"
            "O programa não extrai a imagem atual do rádio. Antes de enviar, guarda uma cópia da imagem "
            "preparada e um registro da transferência; guarde a imagem que estiver usando."))
        self.observacoes.pack(fill="x", anchor="w")
        self.observacoes.bind("<Configure>", self._ajusta_observacoes)

        self.lbl_aviso = ttk.Label(dir_, style="Suave.TLabel")
        self.lbl_aviso.pack(anchor="w", pady=(10, 0))
        self.criar_texto()
        self._instala_roda()

    def novo_indicativo(self, antigo, novo):
        """Troca o indicativo da linha 1 se ela ainda tinha o indicativo anterior (ou estava vazia)."""
        atual = self.linhas[0].get().strip().upper()
        if novo == atual or atual not in ("", (antigo or "").strip().upper()):
            return
        self.linhas[0].set(novo)
        if self._de_texto:
            self.criar_texto()

    def _texto_descricao(self):
        w, h = ia.tamanho(self._modelo)
        nome = {"UV17ProGPS": "O UV-17 Pro GPS", "UV21Pro": "O UV-21 Pro",
                "UV21ProGPS": "O UV-21 Pro GPS"}.get(self._modelo, "Este rádio")
        return (f"{nome} usa uma imagem de {w} x {h} pixels. Escolha um arquivo (PNG, JPG ou BMP de "
                "qualquer tamanho) ou crie uma tela com o seu indicativo.")

    def atualiza_modelo(self, chave):
        """Ajusta a prévia e a imagem ao tamanho da tela do rádio escolhido."""
        if chave not in ia.PERFIS or chave == self._modelo:
            return
        antigo = ia.tamanho(self._modelo)
        self._modelo = chave
        w, h = ia.tamanho(chave)
        self.tela.configure(width=w * ESCALA, height=h * ESCALA)
        self.descricao.configure(text=self._texto_descricao())
        if self._de_texto:
            self.criar_texto()
        elif self.origem is not None:
            self._aplica()
            if antigo != (w, h):
                self.lbl_aviso.config(text=f"Imagem ajustada para {w} x {h} pixels.")

    def _sincroniza_rolagem(self, evento=None):
        self.area.configure(scrollregion=self.area.bbox("all"))

    def _ajusta_observacoes(self, evento):
        largura = max(160, evento.width - 2)
        if int(float(self.observacoes.cget("wraplength"))) != largura:
            self.observacoes.configure(wraplength=largura)

    def _ajusta_pagina(self, evento):
        if not hasattr(self, "opcoes_texto"):
            return
        minimo_opcoes = max(self.opcoes_arquivo.winfo_reqwidth(), self.opcoes_texto.winfo_reqwidth())
        minimo_previa = self.painel_previa.winfo_reqwidth()
        empilhar = evento.width < minimo_previa + minimo_opcoes + 48
        if self._empilhado != empilhar:
            self._empilhado = empilhar
            if empilhar:
                self.painel_previa.grid_configure(row=2, column=0, columnspan=2,
                                                 sticky="nw", padx=0, pady=(0, 12))
                self.painel_opcoes.grid_configure(row=3, column=0, columnspan=2, sticky="new")
                self.corpo.columnconfigure(0, weight=1)
                self.corpo.columnconfigure(1, weight=0)
            else:
                self.painel_previa.grid_configure(row=2, column=0, columnspan=1,
                                                 sticky="nw", padx=(0, 16), pady=0)
                self.painel_opcoes.grid_configure(row=2, column=1, columnspan=1, sticky="new")
                self.corpo.columnconfigure(0, weight=0)
                self.corpo.columnconfigure(1, weight=1)
        largura = max(evento.width, max(minimo_previa, minimo_opcoes) + 32)
        if int(float(self.area.itemcget(self.janela_conteudo, "width"))) != largura:
            self.area.itemconfigure(self.janela_conteudo, width=largura)
        self.descricao.configure(wraplength=max(250, largura - 32))
        horizontal = largura > evento.width
        if horizontal != self._horizontal_visivel:
            self._horizontal_visivel = horizontal
            if horizontal:
                self.rol_horizontal.grid()
            else:
                self.rol_horizontal.grid_remove()
                self.area.xview_moveto(0)
        self._sincroniza_rolagem()

    def _instala_roda(self):
        # Tag local: não troca os bindings globais das outras abas.
        tag = f"RolagemImagem{id(self)}"
        def roda(evento):
            delta = getattr(evento, "delta", 0)
            passos = (-int(delta / 120) or (-1 if delta > 0 else 1)) if delta else (-1 if evento.num == 4 else 1)
            self.area.yview_scroll(passos, "units")
            return "break"
        for evento in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.area.bind_class(tag, evento, roda)
        def visita(w):
            tags = w.bindtags()
            w.bindtags((tags[0], tag) + tags[1:])
            for filho in w.winfo_children():
                visita(filho)
        visita(self.corpo)
        tags = self.area.bindtags()
        self.area.bindtags((tags[0], tag) + tags[1:])

    # ----------------------------------------------------------------- imagem
    def _mostra(self):
        from PIL import ImageTk  # type: ignore
        w, h = ia.tamanho(self._modelo)
        prev = ia.previa(self.final, self._modelo).resize((w * ESCALA, h * ESCALA), 0)
        self.foto = ImageTk.PhotoImage(prev)
        self.tela.delete("all")
        self.tela.create_image(0, 0, image=self.foto, anchor="nw")

    def _aplica(self):
        if self.origem is None:
            return
        self.final = ia.ajusta(self.origem, self.modo.get(), modelo=self._modelo)
        self._mostra()

    def abrir(self):
        caminho = filedialog.askopenfilename(
            title="Escolher imagem", initialdir=self.app.pasta_backup(),
            filetypes=[("Imagens", "*.png *.jpg *.jpeg *.bmp *.gif"), ("Todos", "*.*")])
        if not caminho:
            return
        try:
            self.origem = ia.abre(caminho)
        except ia.ErroImagem as e:
            messagebox.showerror("Imagem", str(e))
            return
        self._de_texto = False
        self._aplica()
        w, h = self.origem.size
        lw, lh = ia.tamanho(self._modelo)
        self.lbl_aviso.config(text=f"{os.path.basename(caminho)}: {w} x {h} pixels"
                                   + ("" if (w, h) == (lw, lh) else f", ajustada para {lw} x {lh}"))

    def escolhe_cor(self, chave):
        r = colorchooser.askcolor(color=_hex(self.cores[chave]), title="Escolher cor")
        if r and r[0]:
            self.cores[chave] = tuple(int(x) for x in r[0])
            self.amostras[chave].config(bg=_hex(self.cores[chave]))
            self.criar_texto()

    def criar_texto(self):
        self.origem = ia.com_texto([v.get() for v in self.linhas], self.cores["fundo"],
                                   self.cores["texto"], self.cores["destaque"], modelo=self._modelo)
        self._de_texto = True
        self._aplica()
        self.lbl_aviso.config(text="Tela criada com texto.")

    def salvar_bmp(self):
        if self.final is None:
            return
        caminho = filedialog.asksaveasfilename(title="Salvar imagem", defaultextension=".bmp",
                                               initialfile=f"Abertura{cr.sufixo_arquivo() or '_radio'}.bmp",
                                               filetypes=[("BMP 24 bits", "*.bmp"), ("PNG", "*.png")])
        if caminho:
            self.final.save(caminho)

    def enviar(self):
        chave = self.app.modelo_radio
        if chave not in ia.PERFIS:
            messagebox.showinfo("Imagem", "Este rádio não permite trocar a imagem de abertura pelo PYProg.")
            return
        if chave != self._modelo:
            self.atualiza_modelo(chave)
        porta = self.app.porta.get().strip()
        if not porta:
            messagebox.showerror("Imagem", "Escolha a porta COM do cabo de programação.")
            return
        if not messagebox.askyesno("Enviar imagem ao rádio", f"Enviar esta imagem de abertura ao "
                                                             f"{self.app.nome_radio()}?"):
            return
        img = self.final.copy()

        resultado = {}

        def tarefa():
            registro = RegistroEnvio(self.app.pasta_backup(), "Imagem", chave, porta, ".bmp",
                                    lambda caminho: img.save(caminho, format="BMP"))
            resultado["aviso"] = registro.executa(lambda: ia.envia(porta, img, progresso=self.app.progresso,
                                                                      modelo=chave))

        def fim():
            self.app.status.config(text=("Imagem de abertura enviada. Desligue e ligue o rádio para ver. "
                                         + resultado.get("aviso", "")).strip())
        self.app.executa("Enviando a imagem ao rádio...", tarefa, depois=fim, nota=tema.NOTA_GRAVACAO)

# -*- coding: utf-8 -*-
"""Tema visual do PYProg: paleta única, estilos ttk (base 'clam'), botões de cantos arredondados,
ícones e os componentes desenhados pelo programa (menus, dicas, campo de busca, painel inicial).

Todas as cores da interface saem do dicionário C. Nenhuma tela define cor por conta própria."""
import os
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

# Linha fixa do painel de andamento enquanto o PYProg grava no rádio
NOTA_GRAVACAO = "Não desligue o rádio nem desconecte o cabo."

C = {
    # menu lateral (carvão quente, no tom do Claude)
    "lateral": "#FFFFFF", "lateral_texto": "#3D3C38", "lateral_titulo": "#8A877E",
    "lateral_ativo": "#F4F2EC", "lateral_ativo_texto": "#262624", "lateral_hover": "#FAF9F5",
    # áreas (creme e marfim)
    "fundo": "#FAF9F5",          # área principal
    "cabecalho": "#FFFFFF", "comandos": "#FFFFFF", "rodape": "#FFFFFF",
    "cartao": "#FFFFFF",         # tabelas, menus e painéis claros
    # comandos
    "primario": "#3D3C38", "primario_h": "#2F2E2B", "primario_p": "#22211F",      # Ler rádio (carvão)
    "gravar": "#C4623F", "gravar_h": "#B85A36", "gravar_p": "#A34E2D",            # Gravar no rádio (terracota)
    "secundario": "#FFFFFF", "secundario_h": "#EFEDE5", "secundario_p": "#E6E3D8",
    "secundario_texto": "#3D3C38",
    "desabilitado": "#A9A69C", "desabilitado_fundo": "#F0EEE6", "desabilitado_forte": "#C9C5B9",
    # controles e texto
    "borda": "#D6D2C4", "borda_suave": "#E6E3D8", "campo": "#FFFFFF", "foco": "#C96442",
    "texto": "#262624", "suave": "#6B6A64", "exemplo": "#97958C",
    # tabela
    "tabela_cab": "#F0EEE6", "zebra": "#FDFCFA", "selecao": "#F7EEE7",
    # situações (sempre acompanhadas de texto ou ícone)
    "aviso": "#8A5A00", "aviso_fundo": "#FBF0D9", "erro": "#B3261E", "ok": "#1E6B45",
    "dica_fundo": "#262624", "dica_texto": "#FAF9F5",
}
# nomes antigos, mantidos para o código que ainda os usa
C.update(pagina=C["fundo"], azul=C["primario"], azul_h=C["primario_h"])

# Situação de TX nas listas de canais: só a cor do texto (a linha não é pintada)
TX_CORES = {
    "pendente": C["erro"],       # transmite fora das faixas
    "bloqueado": C["suave"],     # só recepção
    "excecao": C["aviso"],       # exceção liberada
}
TX_LEGENDA = [
    (None, "Liberado"),
    ("pendente", "Transmite fora das faixas liberadas"),
    ("bloqueado", "Só recepção (TX bloqueado)"),
    ("excecao", "Exceção liberada"),
]
# Texto da coluna TX, com o marcador colorido
TX_TEXTO = {None: "●  Liberado", "pendente": "●  Fora da faixa", "bloqueado": "●  Só recepção",
            "excecao": "●  Exceção liberada"}

PASTA_ICONES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados", "icones")
_ICONES = {}
_IMAGENS = {}        # imagens dos botões (o Tk descarta a imagem que ficar sem referência)


def plural(n, um, varios):
    """'1 canal', '2 canais'."""
    return f"{n} {um if n == 1 else varios}"


def _rgb(cor):
    return int(cor[1:3], 16), int(cor[3:5], 16), int(cor[5:7], 16)


def _foto(im):
    """Imagem do Pillow como PhotoImage do Tk (em PNG, sem depender da ponte ImageTk)."""
    import base64
    import io
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return tk.PhotoImage(data=base64.b64encode(buf.getvalue()))


def icone(nome, px, cor):
    """Ícone (família Lucide) no tamanho e na cor pedidos. Os arquivos são máscaras brancas."""
    chave = (nome, px, cor)
    if chave not in _ICONES:
        try:
            from PIL import Image
            im = Image.open(os.path.join(PASTA_ICONES, nome + ".png")).convert("RGBA").resize((px, px), Image.LANCZOS)
            colorido = Image.new("RGBA", im.size, _rgb(cor) + (255,))
            colorido.putalpha(im.getchannel("A"))
            _ICONES[chave] = _foto(colorido)
        except Exception:
            # Sem o arquivo do ícone, fica um espaço vazio do mesmo tamanho (o rótulo e a dica continuam)
            _ICONES[chave] = tk.PhotoImage(width=px, height=px)
    return _ICONES[chave]


def tam_icone():
    """Tamanho dos ícones dos botões, proporcional à letra (acompanha a escala do Windows)."""
    return max(14, round(tkfont.nametofont("TkDefaultFont").metrics("linespace") * 0.9))


def _arredondado(fundo, borda, raio=5, tam=26, espessura=1):
    """Retângulo de cantos arredondados (desenhado 4x maior e reduzido, para a borda sair suave)."""
    from PIL import Image, ImageDraw
    n = 4
    im = Image.new("RGBA", (tam * n, tam * n), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, tam * n - 1, tam * n - 1], radius=raio * n, fill=borda)
    e = espessura * n
    d.rounded_rectangle([e, e, tam * n - 1 - e, tam * n - 1 - e], radius=max(1, raio * n - e), fill=fundo)
    return _foto(im.resize((tam, tam), Image.LANCZOS))


def _cria_elementos(s):
    """Elementos de imagem dos botões: normal, mouse em cima, pressionado, foco e desabilitado."""
    if _IMAGENS:
        return
    familias = {
        "sec": dict(n=(C["secundario"], C["borda"]), h=(C["secundario_h"], C["borda"]),
                    p=(C["secundario_p"], C["primario"]), d=(C["desabilitado_fundo"], C["borda_suave"])),
        "prim": dict(n=(C["primario"], C["primario"]), h=(C["primario_h"], C["primario_h"]),
                     p=(C["primario_p"], C["primario_p"]), d=(C["desabilitado_forte"], C["desabilitado_forte"])),
        "grav": dict(n=(C["gravar"], C["gravar"]), h=(C["gravar_h"], C["gravar_h"]),
                     p=(C["gravar_p"], C["gravar_p"]), d=(C["desabilitado_forte"], C["desabilitado_forte"])),
    }
    for nome, f in familias.items():
        im = {k: _arredondado(*v) for k, v in f.items()}
        # foco pelo teclado: contorno mais grosso (escuro nos botões coloridos, azul nos claros)
        im["f"] = _arredondado(f["n"][0], C["foco"] if nome == "sec" else C["lateral"], espessura=2)
        _IMAGENS[nome] = im
        s.element_create(f"PY.{nome}", "image", im["n"], ("disabled", im["d"]), ("pressed", im["p"]),
                         ("active", im["h"]), ("focus", im["f"]), border=7, padding=0, sticky="nsew")


def _layout_botao(elemento):
    return [(elemento, {"sticky": "nsew", "children": [
        ("Button.padding", {"sticky": "nsew", "children": [("Button.label", {"sticky": "nsew"})]})]})]


def _caixa(fundo, borda, marca=None, tam=18, espessura=1):
    """Caixa de seleção: quadrado de cantos arredondados, com um V (ícone de check) quando marcada."""
    from PIL import Image, ImageDraw
    n = 4
    im = Image.new("RGBA", (tam * n, tam * n), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, tam * n - 1, tam * n - 1], radius=3 * n, fill=borda)
    e = espessura * n
    d.rounded_rectangle([e, e, tam * n - 1 - e, tam * n - 1 - e], radius=max(1, 3 * n - e), fill=fundo)
    if marca is not None:
        # a máscara do check é branca: basta colocá-la no centro da caixa
        m = round(tam * 0.72) * n
        v = marca.resize((m, m), Image.LANCZOS)
        off = (tam * n - m) // 2
        im.alpha_composite(v, (off, off))
    return _foto(im.resize((tam, tam), Image.LANCZOS))


def _troca_indicador(layout, novo):
    """Troca o indicador padrão do Tk (um X no clam) pelo elemento de imagem, mantendo o resto do layout."""
    saida = []
    for nome, opts in layout:
        opts = dict(opts) if opts else {}
        if nome == "Checkbutton.indicator":
            saida.append((novo, opts))
            continue
        if "children" in opts:
            opts["children"] = _troca_indicador(opts["children"], novo)
        saida.append((nome, opts))
    return saida


def _cria_caixas(s, tam):
    """Caixas de seleção com V: normal, marcada, desabilitada e marcada e desabilitada."""
    from PIL import Image
    if "PY.caixa" in s.element_names():
        return
    marca = Image.open(os.path.join(PASTA_ICONES, "check.png")).convert("RGBA")
    off = _caixa(C["campo"], C["borda"], None, tam)
    on = _caixa(C["primario"], C["primario"], marca, tam)
    off_d = _caixa(C["desabilitado_fundo"], C["borda_suave"], None, tam)
    on_d = _caixa(C["desabilitado_forte"], C["desabilitado_forte"], marca, tam)
    _IMAGENS["caixa"] = (off, on, off_d, on_d)
    s.element_create("PY.caixa", "image", off, ("disabled selected", on_d), ("disabled", off_d),
                     ("selected", on), sticky="w", padding=0)
    s.layout("TCheckbutton", _troca_indicador(s.layout("TCheckbutton"), "PY.caixa"))


def aplica(raiz, fonte_destaque, fonte_negrito):
    s = ttk.Style(raiz)
    s.theme_use("clam")
    _inicia_fonte_menu()
    try:
        _cria_elementos(s)
        arredondado = True
    except Exception:
        # Se as imagens dos botões não puderem ser criadas, o programa abre com botões retos nas mesmas cores
        arredondado = False
    base = tkfont.nametofont("TkDefaultFont")
    linha = base.metrics("linespace")
    v = max(6, round(linha * 0.52))          # respiro vertical dos botões (altura final perto de 36 px)
    try:
        _cria_caixas(s, max(16, round(linha * 0.95)))
    except Exception:
        pass                                 # sem as imagens, as caixas voltam ao desenho padrão do Tk
    raiz.configure(background=C["fundo"])
    s.configure(".", background=C["fundo"], foreground=C["texto"], bordercolor=C["borda"],
                lightcolor=C["fundo"], darkcolor=C["borda"], troughcolor=C["fundo"],
                focuscolor=C["foco"], selectbackground=C["selecao"], selectforeground=C["texto"])
    for nome, cor in (("TFrame", "fundo"), ("Pagina.TFrame", "fundo"), ("Comandos.TFrame", "comandos"),
                      ("Cartao.TFrame", "cartao"), ("Rodape.TFrame", "rodape"), ("Cabecalho.TFrame", "cabecalho")):
        s.configure(nome, background=C[cor])
    s.configure("TLabel", background=C["fundo"], foreground=C["texto"])
    s.configure("Suave.TLabel", foreground=C["suave"])
    s.configure("Pagina.TLabel", background=C["fundo"], foreground=C["suave"])
    s.configure("Titulo.TLabel", font=fonte_destaque, foreground=C["texto"])
    s.configure("Comandos.TLabel", background=C["comandos"], foreground=C["texto"])
    s.configure("ComandosSuave.TLabel", background=C["comandos"], foreground=C["suave"])
    s.configure("Aviso.TLabel", background=C["comandos"], foreground=C["aviso"], font=fonte_negrito)
    s.configure("Cartao.TLabel", background=C["cartao"], foreground=C["texto"])
    s.configure("CartaoSuave.TLabel", background=C["cartao"], foreground=C["suave"])
    s.configure("Rodape.TLabel", background=C["rodape"], foreground=C["texto"])
    s.configure("RodapeSuave.TLabel", background=C["rodape"], foreground=C["suave"])
    for w in ("TCheckbutton", "TRadiobutton"):
        s.configure(w, background=C["fundo"], foreground=C["texto"], indicatorbackground=C["campo"],
                    indicatorforeground="#FFFFFF", upperbordercolor=C["borda"], lowerbordercolor=C["borda"])
        s.map(w, background=[("active", C["fundo"])], foreground=[("disabled", C["desabilitado"])],
              indicatorbackground=[("disabled", C["desabilitado_fundo"]), ("selected", C["primario"]),
                                   ("!selected", C["campo"])],
              indicatorcolor=[("disabled", C["desabilitado_fundo"]), ("selected", C["primario"]),
                              ("!selected", C["campo"])])
    # Botões: secundário (claro), principal (azul sóbrio) e de gravação (azul-petróleo), todos com
    # cantos arredondados, cor sólida e os estados normal, foco, mouse em cima, pressionado e desabilitado
    s.configure("TButton", padding=(14, v), background=C["fundo"], foreground=C["secundario_texto"],
                anchor="center", borderwidth=0, width=0)
    s.map("TButton", foreground=[("disabled", C["desabilitado"])])
    s.configure("Icone.TButton", padding=(10, v), width=0)
    # Neutro e Gravar usam o mesmo contorno dos demais botões (sem preenchimento colorido)
    for estilo, elemento, cor in (("Neutro.TButton", "PY.sec", "secundario"), ("Gravar.TButton", "PY.sec", "secundario")):
        s.configure(estilo, padding=(18, v), foreground=C["secundario_texto"], width=0)
        s.map(estilo, foreground=[("disabled", C["desabilitado"])])
        if arredondado:
            s.layout(estilo, _layout_botao(elemento))
        else:
            s.configure(estilo, background=C[cor], bordercolor=C["borda"], lightcolor=C[cor], darkcolor=C[cor],
                        borderwidth=1, relief="flat")
            s.map(estilo, background=[("disabled", C["desabilitado_forte"]), ("pressed", C[cor + "_p"]),
                                      ("active", C[cor + "_h"])])
    if arredondado:
        s.layout("TButton", _layout_botao("PY.sec"))
        s.layout("Icone.TButton", _layout_botao("PY.sec"))
    else:
        for estilo in ("TButton", "TMenubutton"):
            s.configure(estilo, background=C["secundario"], bordercolor=C["borda"], lightcolor=C["secundario"],
                        darkcolor=C["secundario"], borderwidth=1, relief="flat")
            s.map(estilo, background=[("disabled", C["desabilitado_fundo"]), ("pressed", C["secundario_p"]),
                                      ("active", C["secundario_h"])])
    FONTE_MENU.configure(family=base.actual()["family"], size=base.actual()["size"] + 1)
    if arredondado:
        s.layout("TMenubutton", [("PY.sec", {"sticky": "nsew", "children": [
            ("Menubutton.padding", {"sticky": "nsew", "children": [
                ("Menubutton.indicator", {"side": "right", "sticky": ""}),
                ("Menubutton.label", {"side": "left", "sticky": ""})]})]})])
        s.configure("TMenubutton", background=C["fundo"], borderwidth=0)
    s.configure("TMenubutton", padding=(14, v, 10, v), foreground=C["secundario_texto"],
                arrowcolor=C["secundario_texto"], width=0)
    s.map("TMenubutton", foreground=[("disabled", C["desabilitado"])],
          arrowcolor=[("disabled", C["desabilitado"])])
    for w in ("TEntry", "TCombobox"):
        s.configure(w, fieldbackground=C["campo"], bordercolor=C["borda"], lightcolor=C["campo"],
                    darkcolor=C["campo"], padding=4, arrowcolor=C["secundario_texto"],
                    background=C["secundario"], insertcolor=C["texto"])
        # Cores do texto definidas para todos os estados: no Windows, o texto escolhido numa lista
        # fica "selecionado" e podia sair com a cor de seleção do sistema (invisível no fundo branco)
        s.map(w, bordercolor=[("focus", C["foco"])], lightcolor=[("focus", C["foco"])],
              darkcolor=[("focus", C["foco"])],
              fieldbackground=[("disabled", C["desabilitado_fundo"]), ("readonly", C["campo"])],
              foreground=[("disabled", C["desabilitado"]), ("!disabled", C["texto"])],
              selectbackground=[("readonly", C["campo"]), ("focus", C["selecao"]), ("!focus", C["campo"])],
              selectforeground=[("disabled", C["desabilitado"]), ("!disabled", C["texto"])])
    # Caixa de escolha da mesma altura dos botões (cabeçalho e barras de comandos)
    s.configure("Alto.TCombobox", padding=(6, max(3, v - 3)))
    # Lista suspensa das caixas de escolha (é um Listbox do Tk, fora do ttk)
    raiz.option_add("*TCombobox*Listbox.background", C["campo"])
    raiz.option_add("*TCombobox*Listbox.foreground", C["texto"])
    raiz.option_add("*TCombobox*Listbox.selectBackground", C["selecao"])
    raiz.option_add("*TCombobox*Listbox.selectForeground", C["texto"])
    # Depois de escolher na lista, o texto fica sem seleção (sempre visível)
    if not getattr(raiz, "_pyprog_combo", False):
        raiz._pyprog_combo = True
        raiz.bind_class("TCombobox", "<<ComboboxSelected>>",
                        lambda e: e.widget.selection_clear() if hasattr(e.widget, "selection_clear") else None,
                        add="+")
    # Abas: as seções das telas principais são escolhidas no menu lateral (abas escondidas);
    # as abas visíveis ficam só nas janelas de edição
    s.configure("TNotebook", background=C["fundo"], borderwidth=0, tabmargins=(0, 4, 0, 0))
    s.configure("TNotebook.Tab", padding=(14, 6), background=C["comandos"], foreground=C["suave"],
                bordercolor=C["borda_suave"], lightcolor=C["comandos"], borderwidth=1)
    s.map("TNotebook.Tab", background=[("selected", C["fundo"]), ("active", C["secundario_h"])],
          foreground=[("selected", C["primario"])], lightcolor=[("selected", C["fundo"])],
          font=[("selected", fonte_negrito)])
    s.configure("Interno.TNotebook", background=C["fundo"])
    s.configure("Semabas.TNotebook", background=C["fundo"], borderwidth=0, tabmargins=0, padding=0,
                bordercolor=C["fundo"], lightcolor=C["fundo"], darkcolor=C["fundo"])
    s.layout("Semabas.TNotebook", [("Notebook.client", {"sticky": "nsew"})])
    s.layout("Semabas.TNotebook.Tab", [])
    s.configure("Treeview", background=C["cartao"], fieldbackground=C["cartao"], foreground=C["texto"],
                bordercolor=C["borda_suave"], lightcolor=C["cartao"], darkcolor=C["cartao"],
                rowheight=linha + 9, relief="flat", borderwidth=1)
    s.map("Treeview", background=[("selected", C["selecao"])], foreground=[("selected", C["texto"])])
    s.configure("Treeview.Heading", background=C["tabela_cab"], foreground=C["texto"], font=fonte_negrito,
                relief="flat", bordercolor=C["borda_suave"], lightcolor=C["tabela_cab"],
                darkcolor=C["tabela_cab"], padding=(6, 7))
    s.map("Treeview.Heading", background=[("active", C["secundario_p"])])
    s.configure("TLabelframe", background=C["fundo"], bordercolor=C["borda_suave"], relief="solid", borderwidth=1)
    s.configure("TLabelframe.Label", background=C["fundo"], foreground=C["secundario_texto"], font=fonte_negrito)
    s.configure("TSeparator", background=C["borda_suave"])
    s.configure("TProgressbar", background=C["primario"], troughcolor=C["borda_suave"],
                bordercolor=C["borda_suave"], lightcolor=C["primario"], darkcolor=C["primario"])
    s.configure("TScale", background=C["fundo"], troughcolor=C["borda_suave"])
    for o in ("Vertical", "Horizontal"):
        s.configure(f"{o}.TScrollbar", background=C["borda"], troughcolor=C["fundo"], bordercolor=C["fundo"],
                    arrowcolor=C["suave"], lightcolor=C["borda"], darkcolor=C["borda"], relief="flat")
        s.map(f"{o}.TScrollbar", background=[("active", C["desabilitado"]), ("disabled", C["fundo"])],
              arrowcolor=[("disabled", C["fundo"])])
    return s


def botao(pai, texto, comando, icone_nome=None, estilo="TButton", **kw):
    """Botão com ícone e texto. O ícone muda de cor com o botão desabilitado."""
    b = ttk.Button(pai, text=texto, command=comando, style=estilo, **kw)
    if icone_nome:
        px = tam_icone()
        normal = icone(icone_nome, px, C["secundario_texto"])
        apagado = icone(icone_nome, px, C["desabilitado"])
        b.configure(image=(normal, "disabled", apagado), compound="left" if texto else "image")
    return b


def campo_busca(pai, var, exemplo, largura=34):
    """Campo de busca com lupa e texto de exemplo. Devolve (moldura, entrada)."""
    f = tk.Frame(pai, bg=C["campo"], highlightthickness=1, highlightbackground=C["borda"],
                 highlightcolor=C["foco"])
    tk.Label(f, image=icone("search", tam_icone(), C["suave"]), bg=C["campo"]).pack(side="left", padx=(8, 4))
    ent = tk.Entry(f, textvariable=var, width=largura, relief="flat", bd=0, bg=C["campo"], fg=C["texto"],
                   insertbackground=C["texto"], highlightthickness=0, disabledbackground=C["campo"],
                   selectbackground=C["selecao"], selectforeground=C["texto"])
    ent.pack(side="left", fill="x", expand=True, ipady=max(5, round(tam_icone() * 0.45)), padx=(0, 8))
    lbl = tk.Label(ent, text=exemplo, fg=C["exemplo"], bg=C["campo"], font="TkTextFont", cursor="xterm", bd=0)

    def atualiza(*_):
        if var.get() or ent.focus_get() is ent:
            lbl.place_forget()
        else:
            lbl.place(x=0, rely=0.5, anchor="w")
    lbl.bind("<Button-1>", lambda e: ent.focus_set())
    ent.bind("<FocusIn>", atualiza, add="+")
    ent.bind("<FocusOut>", atualiza, add="+")
    ent.bind("<Escape>", lambda e: var.set(""))
    var.trace_add("write", atualiza)
    ent.after_idle(atualiza)
    return f, ent


def painel_inicial(pai, fonte_titulo, ler, abrir, texto_abrir="Abrir arquivo"):
    """Estado inicial: nada carregado ainda."""
    f = ttk.Frame(pai)
    meio = ttk.Frame(f)
    meio.place(relx=0.5, rely=0.42, anchor="center")
    tk.Label(meio, image=icone("radio", tam_icone() * 3, C["borda"]), bg=C["fundo"]).pack(pady=(0, 10))
    ttk.Label(meio, text="Comece uma programação", font=fonte_titulo).pack()
    ttk.Label(meio, text="Leia os dados do rádio ou abra um arquivo salvo.", style="Suave.TLabel").pack(pady=(4, 16))
    bts = ttk.Frame(meio)
    bts.pack()
    b1 = botao(bts, "Ler rádio", ler, "download", "TButton")
    b1.pack(side="left", padx=(0, 8))
    b2 = botao(bts, texto_abrir, abrir, "folder-open")
    b2.pack(side="left")
    f.botoes = (b1, b2)
    return f


def rolagem_automatica(barra):
    """A barra de rolagem (posta com grid) só aparece quando há o que rolar."""
    def define(a, b):
        if float(a) <= 0.0 and float(b) >= 1.0:
            barra.grid_remove()
        else:
            barra.grid()
        barra.set(a, b)
    return define


def zebra(tv):
    """Linhas alternadas pela posição na tela (e não pelo número do canal), mantendo as outras marcas."""
    for i, iid in enumerate(tv.get_children("")):
        marcas = [m for m in tv.item(iid, "tags") if m != "zebra"]
        tv.item(iid, tags=marcas + ["zebra"] if i % 2 else marcas)


def memoriza_colunas(tv, cfg, chave, salva):
    """Larguras de coluna ajustadas pelo usuário, guardadas por tabela nas preferências."""
    colunas = [c for c in tv["columns"] if not c.startswith("_")]
    for c in colunas:
        tv.column(c, minwidth=36)
    guardadas = cfg.get("colunas", {}).get(chave, {})
    for c in colunas:
        if isinstance(guardadas.get(c), int):
            tv.column(c, width=guardadas[c])

    def solta(_e):
        atuais = {c: int(tv.column(c, "width")) for c in colunas}
        if atuais != cfg.get("colunas", {}).get(chave) and getattr(tv, "_larguras_padrao", None) != atuais:
            cfg.setdefault("colunas", {})[chave] = atuais
            salva()
    tv._larguras_padrao = {c: int(tv.column(c, "width")) for c in colunas} if not guardadas else None
    tv.bind("<ButtonRelease-1>", solta, add="+")


FONTE_MENU = None   # criada em _inicia_fonte_menu (precisa de uma janela Tk)


def _inicia_fonte_menu():
    global FONTE_MENU
    if FONTE_MENU is None:
        FONTE_MENU = tkfont.Font(family="TkDefaultFont", size=12)


class MenuDesenhado:
    """Menu desenhado pelo programa (no lugar do menu do Windows), com letra um pouco maior
    que a do resto da janela e que acompanha o A+/A-."""

    def __init__(self, pai):
        self.pai = pai
        self.itens = []          # (tipo, texto, comando, ativo)
        self.janela = None

    def add_command(self, label, command=None, state="normal"):
        self.itens.append(("cmd", label, command, state != "disabled"))

    def add_separator(self):
        self.itens.append(("sep", None, None, False))

    def add_nota(self, texto):
        self.itens.append(("nota", texto, None, False))

    def add_titulo(self, texto):
        self.itens.append(("titulo", texto, None, False))

    def limpa(self):
        self.itens = []

    def anexa(self, botao):
        """Abre o menu ao clicar no botão (ttk.Menubutton ou outro widget)."""
        def abre(_e=None):
            if str(botao.cget("state")) == "disabled" if "state" in botao.keys() else False:
                return "break"
            try:
                if botao.instate(["disabled"]):
                    return "break"
            except Exception:
                pass
            self.popup(botao.winfo_rootx(), botao.winfo_rooty() + botao.winfo_height() + 2, botao)
            return "break"
        botao.bind("<Button-1>", abre)
        botao.bind("<space>", abre)
        botao.bind("<Return>", abre)

    def tk_popup(self, x, y):
        self.popup(x, y)

    def grab_release(self):
        pass

    def fecha(self, _e=None):
        if self.janela is not None:
            try:
                self.janela.grab_release()
                self.janela.destroy()
            except Exception:
                pass
            self.janela = None

    def popup(self, x, y, alinha=None):
        self.fecha()
        _inicia_fonte_menu()
        j = tk.Toplevel(self.pai)
        j.withdraw()
        j.wm_overrideredirect(True)
        try:
            j.attributes("-topmost", True)
        except tk.TclError:
            pass
        borda = tk.Frame(j, bg=C["borda"], padx=1, pady=1)
        borda.pack(fill="both", expand=True)
        dentro = tk.Frame(borda, bg=C["cartao"], pady=4)
        dentro.pack(fill="both", expand=True)
        pequena = tkfont.nametofont("TkDefaultFont")
        self._linhas = []
        for tipo, texto, cmd, ativo in self.itens:
            if tipo == "sep":
                tk.Frame(dentro, bg=C["borda_suave"], height=1).pack(fill="x", padx=8, pady=4)
            elif tipo == "nota":
                tk.Label(dentro, text=texto, bg=C["cartao"], fg=C["suave"], font=pequena, justify="left",
                         anchor="w", padx=16, pady=2).pack(fill="x")
            elif tipo == "titulo":
                tk.Label(dentro, text=texto, bg=C["cartao"], fg=C["suave"], font=FONTE_MENU, anchor="w",
                         padx=16, pady=4).pack(fill="x")
            else:
                l = tk.Label(dentro, text=texto, bg=C["cartao"], fg=C["texto"] if ativo else C["desabilitado"],
                             font=FONTE_MENU, anchor="w", padx=16, pady=5, cursor="hand2" if ativo else "")
                l.pack(fill="x")
                if ativo:
                    self._linhas.append((l, cmd))
                    l.bind("<Enter>", lambda e, w=l: self._destaca(w))
                    l.bind("<ButtonRelease-1>", lambda e, c=cmd: self._executa(c))
        j.update_idletasks()
        w, h = j.winfo_reqwidth(), j.winfo_reqheight()
        if alinha is not None:
            w = max(w, alinha.winfo_width())
        sw, sh = j.winfo_screenwidth(), j.winfo_screenheight()
        x = max(0, min(x, sw - w - 4))
        if y + h > sh - 4:
            y = max(0, (alinha.winfo_rooty() - h - 2) if alinha is not None else sh - h - 4)
        j.geometry(f"{w}x{h}+{x}+{y}")
        j.deiconify()
        self.janela = j
        self._atual = None
        j.bind("<Escape>", self.fecha)
        j.bind("<Up>", lambda e: self._move(-1))
        j.bind("<Down>", lambda e: self._move(1))
        j.bind("<Return>", lambda e: self._executa(self._atual[1]) if self._atual else None)
        j.bind("<ButtonPress>", self._clique_fora, add="+")
        j.bind("<FocusOut>", lambda e: j.after(150, self._perdeu_foco))
        # Sem grab_set: com ele, o X da janela principal ficava sem efeito enquanto o menu estava aberto.
        # Cliques na janela principal (ou movê-la) fecham o menu.
        top = self.pai.winfo_toplevel()
        if not getattr(self, "_ligado", False):
            top.bind("<ButtonPress>", lambda e: self._clique_fora(e) if self.janela is not None else None, add="+")
            top.bind("<Configure>", lambda e: self.fecha() if e.widget is top and self.janela is not None
                     else None, add="+")
            self._ligado = True
        try:
            j.focus_force()
        except tk.TclError:
            pass

    def _perdeu_foco(self):
        """Fecha o menu quando outra janela (ou outro programa) recebe o foco."""
        j = self.janela
        if j is None:
            return
        try:
            if j.focus_get() is None:
                self.fecha()
        except Exception:
            self.fecha()

    def _clique_fora(self, e):
        j = self.janela
        if j is None:
            return
        x, y = e.x_root, e.y_root
        if not (j.winfo_rootx() <= x < j.winfo_rootx() + j.winfo_width()
                and j.winfo_rooty() <= y < j.winfo_rooty() + j.winfo_height()):
            self.fecha()

    def _destaca(self, w):
        for l, c in self._linhas:
            l.configure(bg=C["selecao"] if l is w else C["cartao"])
            if l is w:
                self._atual = (l, c)

    def _move(self, d):
        if not self._linhas:
            return
        i = [l for l, _ in self._linhas].index(self._atual[0]) if self._atual else (-1 if d > 0 else 0)
        self._destaca(self._linhas[(i + d) % len(self._linhas)][0])

    def _executa(self, cmd):
        self.fecha()
        if cmd:
            self.pai.after_idle(cmd)


def configura_tags_tx(tv):
    tv.tag_configure("zebra", background=C["zebra"])
    for tag, fg in TX_CORES.items():
        tv.tag_configure(tag, foreground=fg)
    tv.tag_configure("vazio", foreground=C["exemplo"])


def legenda_tx(pai, fonte):
    f = ttk.Frame(pai)
    for tag, txt in TX_LEGENDA:
        tk.Label(f, text="●", fg=TX_CORES.get(tag, C["texto"]), bg=C["fundo"], font=fonte).pack(side="left")
        tk.Label(f, text=txt, fg=C["suave"], bg=C["fundo"], font=fonte).pack(side="left", padx=(2, 16))
    return f


def dica_ao_parar(widget, texto, espera=500):
    """Mostra uma dica pequena quando o ponteiro do mouse para sobre o widget."""
    import tkinter as _tk
    estado = {"id": None, "jan": None, "clicou": False}   # depois do clique, só volta ao sair e entrar

    def esconde(_=None):
        if estado["id"]:
            widget.after_cancel(estado["id"])
            estado["id"] = None
        if estado["jan"]:
            estado["jan"].destroy()
            estado["jan"] = None

    def mostra():
        estado["id"] = None
        txt = texto() if callable(texto) else texto
        if not txt:
            return
        j = _tk.Toplevel(widget)
        j.wm_overrideredirect(True)
        _tk.Label(j, text=txt, bg=C["dica_fundo"], fg=C["dica_texto"], padx=8, pady=3,
                 font="TkDefaultFont").pack()
        j.update_idletasks()
        # Dentro da tela: perto da borda direita (janela maximizada), a dica é puxada para a esquerda
        x = max(0, min(widget.winfo_rootx(), widget.winfo_screenwidth() - j.winfo_reqwidth() - 4))
        y = widget.winfo_rooty() + widget.winfo_height() + 6
        j.wm_geometry(f"+{x}+{y}")
        estado["jan"] = j

    def agenda(_=None):
        esconde()
        if not estado["clicou"]:
            estado["id"] = widget.after(espera, mostra)

    def sai(_=None):
        estado["clicou"] = False
        esconde()

    def clique(_=None):
        estado["clicou"] = True
        esconde()

    widget.bind("<Enter>", agenda, add="+")
    widget.bind("<Motion>", lambda e: None if estado["jan"] else agenda(), add="+")
    widget.bind("<Leave>", sai, add="+")
    widget.bind("<ButtonPress>", clique, add="+")
    return clique       # para quem trata <Button-1> no widget (esse evento tem precedência sobre <ButtonPress>)
    widget.bind("<KeyPress>", esconde, add="+")


def imagem_engrenagem(px, cor="#2C435B", dentes=8, furo=0.21, topo=0.16):
    """Engrenagem desenhada com dentes retos e furo no meio, suavizada (desenho 8x maior e reduzido)."""
    import math
    from PIL import Image, ImageDraw, ImageTk
    n = px * 8
    c = n / 2
    r_ext, r_int, r_furo = n * 0.48, n * 0.36, n * furo
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    passo = 2 * math.pi / dentes
    pts = []
    for i in range(dentes):
        a = i * passo - math.pi / 2
        for da, r in ((-0.32, r_int), (-topo, r_ext), (topo, r_ext), (0.32, r_int)):
            pts.append((c + r * math.cos(a + da * passo), c + r * math.sin(a + da * passo)))
    d.polygon(pts, fill=cor)
    d.ellipse([c - r_int, c - r_int, c + r_int, c + r_int], fill=cor)
    d.ellipse([c - r_furo, c - r_furo, c + r_furo, c + r_furo], fill=(0, 0, 0, 0))
    return ImageTk.PhotoImage(im.resize((px, px), Image.LANCZOS))



class MenuLateral(tk.Frame):
    """Menu lateral escuro com as seções do rádio escolhido (no lugar das abas horizontais).

    define(grupos) recebe [(título, [(chave, texto, ícone), ...]), ...]; ao_escolher(chave) é chamada
    no clique, em Enter ou em Espaço. Recolhido, mostra só os ícones, com o nome da seção na dica."""

    def __init__(self, pai, ao_escolher, ao_recolher=None, recolhido=False, fonte_negrito=None):
        super().__init__(pai, bg=C["lateral"])
        self.ao_escolher, self.ao_recolher = ao_escolher, ao_recolher
        self.recolhido = recolhido
        self.fonte_negrito = fonte_negrito
        self.grupos, self.linhas, self.ativa = [], {}, None
        topo = tk.Frame(self, bg=C["lateral"])
        topo.pack(fill="x", pady=(10, 2))
        self.bt = tk.Label(topo, bg=C["lateral"], cursor="hand2", takefocus=1, highlightthickness=1,
                           highlightbackground=C["lateral"], highlightcolor=C["lateral_texto"])
        self.bt.bind("<Button-1>", lambda e: self.alterna())
        self.bt.bind("<Return>", lambda e: self.alterna())
        self.bt.bind("<space>", lambda e: self.alterna())
        dica_ao_parar(self.bt, lambda: "Expandir o menu" if self.recolhido else "Recolher o menu")
        self.bt.pack(side="right", padx=12)
        # A lista rola sozinha quando falta altura
        self.tela = tk.Canvas(self, bg=C["lateral"], highlightthickness=0, bd=0)
        self.tela.pack(fill="both", expand=True)
        self.dentro = tk.Frame(self.tela, bg=C["lateral"])
        self._jan = self.tela.create_window((0, 0), window=self.dentro, anchor="nw")
        self.dentro.bind("<Configure>", lambda e: self._ajusta())
        self.tela.bind("<Configure>", lambda e: self.tela.itemconfigure(self._jan, width=e.width))
        for w in (self.tela, self.dentro):
            w.bind("<Enter>", lambda e: self.tela.bind_all("<MouseWheel>", self._roda), add="+")
            w.bind("<Leave>", lambda e: self.tela.unbind_all("<MouseWheel>"), add="+")

    def _roda(self, ev):
        if self.dentro.winfo_reqheight() > self.tela.winfo_height():
            self.tela.yview_scroll(int(-ev.delta / 120) if ev.delta else 0, "units")

    def _ajusta(self):
        self.tela.configure(scrollregion=(0, 0, self.dentro.winfo_reqwidth(), self.dentro.winfo_reqheight()),
                            width=self.dentro.winfo_reqwidth())

    def alterna(self):
        self.recolhido = not self.recolhido
        self._monta()
        if self.ao_recolher:
            self.ao_recolher(self.recolhido)

    def define(self, grupos):
        if grupos != self.grupos:
            self.grupos = grupos
            self._monta()

    def atualiza(self):
        """Refaz o desenho (mudança do tamanho da letra)."""
        self._monta()

    def _monta(self):
        for w in self.dentro.winfo_children():
            w.destroy()
        self.linhas = {}
        px = tam_icone() + 2
        self.bt.configure(image=icone("chevrons-right" if self.recolhido else "chevrons-left", px,
                                      C["lateral_texto"]))
        fonte = tkfont.nametofont("TkDefaultFont")
        largura = max([fonte.measure("Contatos e TGs")]
                      + [fonte.measure(t) for _, itens in self.grupos for _, t, _ in itens])
        for titulo, itens in self.grupos:
            if not itens:
                continue
            if self.recolhido:
                tk.Frame(self.dentro, bg=C["lateral_hover"], height=1).pack(fill="x", padx=10, pady=6)
            else:
                tk.Label(self.dentro, text=titulo.upper(), bg=C["lateral"], fg=C["lateral_titulo"],
                         font=self.fonte_negrito, anchor="w").pack(fill="x", padx=18, pady=(10, 4))
            for chave, texto, nome_icone in itens:
                self._linha(chave, texto, nome_icone, px)
        if not self.recolhido:
            tk.Frame(self.dentro, bg=C["lateral"], width=largura + px + 84, height=1).pack()
        self.dentro.update_idletasks()
        self._ajusta()
        self._pinta()

    def _linha(self, chave, texto, nome_icone, px):
        f = tk.Frame(self.dentro, bg=C["lateral"], cursor="hand2", takefocus=1, highlightthickness=1,
                     highlightbackground=C["lateral"], highlightcolor=C["lateral_texto"])
        f.pack(fill="x", padx=8, pady=1)
        ic = tk.Label(f, bg=C["lateral"])
        ic.pack(side="left", padx=(10, 10), pady=max(5, px // 3))
        tx = tk.Label(f, text=texto, bg=C["lateral"], fg=C["lateral_texto"], anchor="w")
        if not self.recolhido:
            tx.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.linhas[chave] = (f, ic, tx, nome_icone, px)
        for w in (f, ic, tx):
            w.bind("<Button-1>", lambda e, k=chave: self.ao_escolher(k))
            w.bind("<Enter>", lambda e, k=chave: self._pinta(k), add="+")
            w.bind("<Leave>", lambda e: self._pinta(), add="+")
        f.bind("<Return>", lambda e, k=chave: self.ao_escolher(k))
        f.bind("<space>", lambda e, k=chave: self.ao_escolher(k))
        f.bind("<Down>", lambda e: (e.widget.tk_focusNext().focus_set(), "break")[1])
        f.bind("<Up>", lambda e: (e.widget.tk_focusPrev().focus_set(), "break")[1])
        dica_ao_parar(f, lambda t=texto: t if self.recolhido else "")

    def seleciona(self, chave):
        self.ativa = chave
        self._pinta()

    def _pinta(self, sobre=None):
        for chave, (f, ic, tx, nome_icone, px) in self.linhas.items():
            ativo = chave == self.ativa
            fundo = C["lateral_ativo"] if ativo else C["lateral_hover"] if chave == sobre else C["lateral"]
            cor = C["lateral_ativo_texto"] if ativo else C["lateral_texto"]
            f.configure(bg=fundo, highlightbackground=fundo)
            ic.configure(bg=fundo, image=icone(nome_icone, px, cor))
            tx.configure(bg=fundo, fg=cor, font=self.fonte_negrito if ativo else "TkDefaultFont")


FAIXA_TOPO = None      # faixa do cabeçalho, onde ficam os comandos do rádio (definida pelo programa)
_BARRAS_TOPO = []      # (página, barra): a barra só aparece com a página dela aberta


def barra_comandos(pai):
    """Comandos principais (Ler rádio, Gravar no rádio, Arquivo...). Ficam na faixa do topo, na mesma
    linha dos controles da porta; sem faixa definida, a barra vai para o topo da própria página."""
    if FAIXA_TOPO is None:
        f = ttk.Frame(pai, padding=(16, 12, 16, 8), style="Comandos.TFrame")
        f.pack(fill="x")
        return f
    f = ttk.Frame(FAIXA_TOPO, style="Comandos.TFrame")
    _BARRAS_TOPO.append((pai, f))
    return f


def atualiza_comandos():
    """Mostra no topo só os comandos da página que está aberta."""
    for pai, f in _BARRAS_TOPO:
        if pai.winfo_ismapped():
            f.pack(side="left")
        else:
            f.pack_forget()


def botoes_historico(barra, desfazer, refazer):
    """Desfazer e refazer: botões só com ícone, com dica."""
    out = []
    for nome, fn, dica, esq in (("undo-2", desfazer, "Desfazer (Ctrl+Z)", 10), ("redo-2", refazer, "Refazer (Ctrl+Y)", 4)):
        b = botao(barra, "", fn, nome, "Icone.TButton")
        b.pack(side="left", padx=(esq, 0))
        dica_ao_parar(b, dica)
        out.append(b)
    return out


class LinhaArquivo(ttk.Frame):
    """Linha abaixo dos comandos: de onde veio a programação, aviso de alterações não salvas e contagens."""

    def __init__(self, pai):
        super().__init__(pai, padding=(16, 0, 16, 10), style="Comandos.TFrame")
        self.pack(fill="x")
        self.nome = ttk.Label(self, style="ComandosSuave.TLabel")
        self.nome.pack(side="left")
        self.mod = ttk.Label(self, style="Aviso.TLabel")
        self.mod.pack(side="left", padx=(14, 0))
        self.cont = ttk.Label(self, style="ComandosSuave.TLabel")
        self.cont.pack(side="right")
        self._dica = ""
        dica_ao_parar(self.nome, lambda: self._dica)
        tk.Frame(pai, bg=C["borda_suave"], height=1).pack(fill="x")

    def mostra(self, origem, contagens="", modificado=False, caminho=""):
        curto = origem if len(origem) <= 72 else origem[:36] + "…" + origem[-34:]
        self.nome.config(text=curto)
        self.mod.config(text="●  Alterações não salvas" if modificado else "")
        self.cont.config(text=contagens)
        self._dica = caminho or (origem if curto != origem else "")


def titulo_do_caderno(pai, nb, fonte):
    """Título da seção em exibição, acima do conteúdo (acompanha a escolha feita no menu lateral)."""
    lbl = ttk.Label(pai, font=fonte)
    lbl.pack(anchor="w", padx=16, pady=(12, 0), before=nb)

    def atualiza(_e=None):
        try:
            lbl.config(text=nb.tab(nb.select(), "text"))
        except tk.TclError:
            pass
    nb.bind("<<NotebookTabChanged>>", atualiza, add="+")
    nb.after_idle(atualiza)
    return lbl


def alterna_inicio(painel, topo, tabela, vazio):
    """Sem programação carregada, o painel inicial ocupa o lugar da tabela."""
    if vazio:
        tabela.pack_forget()
        painel.pack(after=topo, fill="both", expand=True)
    else:
        painel.pack_forget()
        tabela.pack(after=topo, fill="both", expand=True, padx=16, pady=(0, 6))


def fluxo(frame, espaco=10, margem=(16, 10), entre_linhas=8):
    """Põe os controles de uma barra lado a lado e passa para a linha de baixo os que não couberem
    (janelas estreitas), sem sobrepor nem esconder nenhum. Chamar depois de criar os controles."""
    filhos = frame.pack_slaves()
    for w in filhos:
        w.pack_forget()
    frame.configure(padding=0)
    mx, my = margem

    def arruma(_e=None):
        largura = frame.winfo_width()
        if largura <= 1:
            return
        linhas, atual, x = [], [], mx
        for w in filhos:
            lw = w.winfo_reqwidth()
            if atual and x + lw > largura - mx:
                linhas.append(atual)
                atual, x = [], mx
            atual.append((w, x))
            x += lw + espaco
        linhas.append(atual)
        y = my
        for linha in linhas:
            alt = max(w.winfo_reqheight() for w, _ in linha)
            for w, x in linha:
                w.place(x=x, y=y + (alt - w.winfo_reqheight()) // 2)
            y += alt + entre_linhas
        altura = y - entre_linhas + my
        if int(frame.cget("height") or 0) != altura:
            frame.configure(height=altura)
    frame.bind("<Configure>", arruma, add="+")
    frame.after_idle(arruma)
    return arruma

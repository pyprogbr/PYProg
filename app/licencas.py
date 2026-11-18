# -*- coding: utf-8 -*-
"""Janela "Sobre o PYProg" e as licenças do programa e das bibliotecas que o acompanham."""
import os
import sys
import tkinter as tk
import webbrowser
from tkinter import ttk

import tema

PASTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "licencas")
URL_PROJETO = "https://github.com/pyprogbr/PYProg"
EMAIL = "pu2keu@gmail.com"
URL_CHIRP = "https://www.chirpmyradio.com"
URL_GPL = "https://www.gnu.org/licenses/gpl-3.0.html"

AVISO_BETA = ("Esta é uma versão de testes (beta), distribuída gratuitamente e sem garantia de qualquer tipo, "
              "podendo conter falhas. Antes de gravar alterações, confira o modelo selecionado e guarde uma "
              "cópia da programação. As vozes e a imagem de abertura gravadas no rádio não podem ser lidas de "
              "volta pelo computador: depois de trocadas, as originais não podem ser restauradas. O uso é de "
              "responsabilidade exclusiva do usuário e deve observar as normas da Anatel.")


def _texto(caminho):
    for cod in ("utf-8", "latin-1"):
        try:
            with open(caminho, encoding=cod) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
        except OSError:
            return ""
    return ""


def lista_licencas():
    """[(título, texto)]: PYProg e CHIRP, Python e cada biblioteca instalada."""
    out = []
    gpl = _texto(os.path.join(PASTA, "COPYING-GPL-3.0.txt"))
    out.append(("PYProg e CHIRP (GNU GPL versão 3)", gpl))
    terceiros = _texto(os.path.join(PASTA, "TERCEIROS.txt"))
    if terceiros:
        out.append(("Resumo: componentes de terceiros", terceiros))
    py = os.path.join(sys.base_prefix, "LICENSE.txt")
    if os.path.exists(py):
        out.append((f"Python {sys.version.split()[0]} (PSF)", _texto(py)))
    try:
        from importlib import metadata
        dists = sorted(metadata.distributions(), key=lambda d: (d.metadata.get("Name") or "").casefold())
    except Exception:
        dists = []
    vistos = set()
    for d in dists:
        nome = d.metadata.get("Name") or "?"
        if nome.casefold() in vistos or nome.casefold() in ("pip", "setuptools", "wheel"):
            continue
        vistos.add(nome.casefold())
        textos = []
        for f in d.files or []:
            base = os.path.basename(str(f)).upper()
            if base.startswith(("LICENSE", "LICENCE", "COPYING", "NOTICE", "AUTHORS")) or "/licenses/" in str(f):
                try:
                    t = f.read_text()
                except Exception:
                    t = None
                if t:
                    textos.append(f"--- {f} ---\n{t}")
        lic = d.metadata.get("License-Expression") or d.metadata.get("License") or ""
        if len(lic) > 80:
            lic = ""
        titulo = f"{nome} {d.version}" + (f" ({lic})" if lic else "")
        out.append((titulo, "\n\n".join(textos) or f"Licença declarada: {lic or 'consulte o pacote'}"))
    return out


def janela_licencas(app):
    j = tk.Toplevel(app.raiz)
    j.title("Licenças")
    j.transient(app.raiz)
    larg = min(980, max(480, j.winfo_screenwidth() - 80))
    alt = min(680, max(360, j.winfo_screenheight() - 120))
    j.geometry(f"{larg}x{alt}")
    corpo = ttk.Frame(j, padding=12)
    corpo.pack(fill="both", expand=True)
    itens = lista_licencas()
    lista = tk.Listbox(corpo, width=34, activestyle="none", exportselection=False, font="TkDefaultFont",
                       relief="solid", bd=1, highlightthickness=0, selectbackground=tema.C["selecao"],
                       selectforeground=tema.C["texto"])
    for t, _ in itens:
        lista.insert("end", t)
    lista.pack(side="left", fill="y")
    txt = tk.Text(corpo, wrap="word", font="TkFixedFont", relief="solid", bd=1, padx=10, pady=8)
    rol = ttk.Scrollbar(corpo, orient="vertical", command=txt.yview)
    txt.configure(yscrollcommand=rol.set)
    rol.pack(side="right", fill="y")
    txt.pack(side="left", fill="both", expand=True, padx=(10, 0))

    def mostra(_e=None):
        sel = lista.curselection()
        if not sel:
            return
        txt.configure(state="normal")
        txt.delete("1.0", "end")
        txt.insert("1.0", itens[sel[0]][1] or "(texto não encontrado)")
        txt.configure(state="disabled")
    lista.bind("<<ListboxSelect>>", mostra)
    lista.selection_set(0)
    mostra()
    ttk.Button(j, text="Fechar", command=j.destroy).pack(pady=(0, 12))
    j.bind("<Escape>", lambda e: j.destroy())


def janela_sobre(app, nome, versao):
    j = tk.Toplevel(app.raiz)
    j.withdraw()
    j.title(f"Sobre o {nome}")
    j.transient(app.raiz)
    j.resizable(False, False)
    f = ttk.Frame(j, padding=(24, 20, 24, 16))
    f.pack(fill="both", expand=True)
    larg = 560
    topo = ttk.Frame(f)
    topo.pack(fill="x")
    try:
        import vozes_core as vc
        j._ic = tk.PhotoImage(file=os.path.join(vc.pasta_dados(), "icone_40.png"))
        ttk.Label(topo, image=j._ic).pack(side="left", padx=(0, 12))
    except Exception:
        pass
    nomes = ttk.Frame(topo)
    nomes.pack(side="left")
    ttk.Label(nomes, text=nome, font=app.fonte_titulo).pack(anchor="w")
    ttk.Label(nomes, text=f"Versão {versao}", style="Suave.TLabel").pack(anchor="w")

    def link(pai, texto, url):
        l = tk.Label(pai, text=texto, fg=tema.C["primario"], bg=tema.C["fundo"], cursor="hand2", font="TkDefaultFont")
        l.bind("<Button-1>", lambda e: webbrowser.open(url))
        return l

    def bloco(titulo, texto):
        ttk.Label(f, text=titulo, font=app.fonte_negrito).pack(anchor="w", pady=(14, 2))
        ttk.Label(f, text=texto, wraplength=larg, justify="left").pack(anchor="w")

    ttk.Label(f, text="Programação de rádios: canais, ajustes, vozes e imagem de abertura.",
              wraplength=larg, justify="left").pack(anchor="w", pady=(12, 0))
    autor = ttk.Frame(f)
    autor.pack(anchor="w", pady=(10, 0))
    ttk.Label(autor, text="Desenvolvido por PU2KEU.  Contato: ").pack(side="left")
    link(autor, EMAIL, f"mailto:{EMAIL}").pack(side="left")

    bloco("CHIRP", "O PYProg usa código e informações do CHIRP, programa livre de programação de rádios, "
                   "distribuído sob a licença GNU GPL versão 3, sem garantia de qualquer tipo. Por isso o PYProg "
                   "também é distribuído sob a GPL 3, e o código-fonte acompanha cada versão.")
    l2 = ttk.Frame(f)
    l2.pack(anchor="w", pady=(4, 0))
    link(l2, "chirpmyradio.com", URL_CHIRP).pack(side="left")
    ttk.Label(l2, text="   ").pack(side="left")
    link(l2, "Licença GPL 3", URL_GPL).pack(side="left")

    bloco("Referências", "Também foram usados como referência o BFVoicePackEditor e o dmrconfig, de Serge "
                         "Vakulenko, para os arquivos dos rádios DMR. "
                         "A geração de vozes usa um serviço on-line de terceiros (vozes neurais "
                         "da Microsoft), sujeito aos termos desse serviço.")
    ttk.Label(f, text="Projeto independente, sem vínculo com fabricantes de rádios ou com o projeto CHIRP.",
              wraplength=larg, justify="left", font=app.fonte_negrito).pack(anchor="w", pady=(14, 0))
    bloco("AVISO", AVISO_BETA)

    bt = ttk.Frame(f)
    bt.pack(fill="x", pady=(18, 0))
    ttk.Button(bt, text="Fechar", command=j.destroy).pack(side="right")
    ttk.Button(bt, text="Ver licenças completas", command=lambda: janela_licencas(app)).pack(side="right", padx=8)
    j.bind("<Escape>", lambda e: j.destroy())
    j.update_idletasks()
    r = app.raiz
    j.geometry(f"+{max(0, r.winfo_rootx() + (r.winfo_width() - j.winfo_reqwidth()) // 2)}"
               f"+{r.winfo_rooty() + max(0, (r.winfo_height() - j.winfo_reqheight()) // 3)}")
    j.deiconify()

# -*- coding: utf-8 -*-
"""Exportar a lista de canais em PDF (para imprimir) ou CSV (planilha)."""
import csv
import os
import sys
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk



def grava_csv(caminho, colunas, linhas):
    """CSV com ponto e vírgula e BOM, como o Excel em português espera."""
    with open(caminho, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(colunas)
        for l in linhas:
            w.writerow(["" if v is None else str(v) for v in l])


def _fonte_pdf():
    """Fonte com acentos: Segoe UI/Arial no Windows, DejaVu no Linux; senão Helvetica."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    pares = [(r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\segoeuib.ttf"),
             (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf"),
             ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")]
    windir = os.environ.get("WINDIR")
    if windir:
        pares.insert(0, (os.path.join(windir, "Fonts", "segoeui.ttf"), os.path.join(windir, "Fonts", "segoeuib.ttf")))
    for n, b in pares:
        if os.path.exists(n) and os.path.exists(b):
            try:
                pdfmetrics.registerFont(TTFont("PYProg", n))
                pdfmetrics.registerFont(TTFont("PYProg-Negrito", b))
                return "PYProg", "PYProg-Negrito"
            except Exception:
                continue
    return "Helvetica", "Helvetica-Bold"


def grava_pdf(caminho, titulo, subtitulo, colunas, linhas, grupos=None):
    """Relatório em A4 retrato. grupos: lista de (título, linhas) para separar por zona/banco."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    normal, negrito = _fonte_pdf()
    larg_pag, alt_pag = A4
    marg = 14 * mm
    util = larg_pag - 2 * marg
    azul, escuro, suave = colors.HexColor("#365D80"), colors.HexColor("#243247"), colors.HexColor("#596579")
    zebra, linha = colors.HexColor("#F3F6F9"), colors.HexColor("#D3DCE5")
    tam = 7.8 if len(colunas) <= 9 else 7.0
    st_cel = ParagraphStyle("c", fontName=normal, fontSize=tam, leading=tam + 2, textColor=escuro)
    st_cab = ParagraphStyle("h", fontName=negrito, fontSize=tam, leading=tam + 2, textColor=colors.white)
    st_grp = ParagraphStyle("g", fontName=negrito, fontSize=10.5, leading=13, textColor=azul)
    st_grp_n = ParagraphStyle("gn", fontName=normal, fontSize=8, leading=13, textColor=suave)

    # largura das colunas: proporcional ao conteúdo, ocupando toda a largura útil
    todas = [l for _, ls in (grupos or [(None, linhas)]) for l in ls]
    larg = []
    for i, c in enumerate(colunas):
        w = max([stringWidth(str(c), negrito, tam)] +
                [stringWidth(str(l[i]) if i < len(l) else "", normal, tam) for l in todas[:3000]])
        larg.append(min(w + 8, 140))
    sobra = util - sum(larg)
    largas = [i for i, w in enumerate(larg) if w > 60] or list(range(len(larg)))
    soma = sum(larg[i] for i in largas)
    for i in largas:                      # só as colunas largas (nome, contato...) encolhem ou crescem
        larg[i] = max(40, larg[i] + sobra * larg[i] / soma)
    if sum(larg) > util:
        larg = [w * util / sum(larg) for w in larg]
    centro = [i for i, c in enumerate(colunas)
              if all(len(str(l[i]) if i < len(l) else "") <= 9 for l in todas[:3000])
              and c not in ("Nome", "Contato", "Zonas")]

    def tabela(ls, grupo=None):
        topo = 1 if grupo else 0
        dados = ([[Paragraph(f"{grupo}", st_grp)] + [""] * (len(colunas) - 3)
                  + [Paragraph(f"{len(ls)} canais", ParagraphStyle("gn2", parent=st_grp_n, alignment=2)), ""]]
                 if grupo else [])
        dados.append([Paragraph(str(c), st_cab) for c in colunas])
        for l in ls:
            dados.append([Paragraph("" if v is None else str(v).replace("&", "&amp;").replace("<", "&lt;"), st_cel)
                          for v in l])
        t = Table(dados, colWidths=larg, repeatRows=1 + topo, hAlign="LEFT")
        estilo = [("BACKGROUND", (0, topo), (-1, topo), azul),
                  ("TOPPADDING", (0, 0), (-1, -1), 2.4), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.4),
                  ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                  ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                  ("LINEBELOW", (0, 1 + topo), (-1, -1), 0.3, linha)]
        if grupo:
            estilo += [("SPAN", (0, 0), (-3, 0)), ("SPAN", (-2, 0), (-1, 0)), ("LINEBEFORE", (0, 0), (0, 0), 3, azul),
                       ("LEFTPADDING", (0, 0), (0, 0), 6), ("BOTTOMPADDING", (0, 0), (-1, 0), 4)]
        for r in range(2 + topo, len(dados), 2):
            estilo.append(("BACKGROUND", (0, r), (-1, r), zebra))
        t.setStyle(TableStyle(estilo))
        for c in centro:
            for r in range(topo, len(dados)):
                dados[r][c].style = ParagraphStyle("cc", parent=dados[r][c].style, alignment=1)
        return t

    hist = []
    total = len(todas) if not grupos else len({tuple(l) for l in todas})
    hist.append(Spacer(1, 20 * mm))
    if grupos:
        for nome, ls in grupos:
            if ls:
                hist += [Spacer(1, 4 * mm), tabela(ls, nome)]
    else:
        hist.append(tabela(linhas))

    try:
        import vozes_core as vc
        icone = os.path.join(vc.pasta_dados(), "icone.png")
        if not os.path.exists(icone):
            icone = None
    except Exception:
        icone = None
    gerado = time.strftime("%d/%m/%Y %H:%M")

    class Canvas(rl_canvas.Canvas):            # "Página X de Y"
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._paginas = []

        def showPage(self):
            self._paginas.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            n = len(self._paginas)
            for estado in self._paginas:
                self.__dict__.update(estado)
                self._moldura(n)
                super().showPage()
            super().save()

        def _moldura(self, n):
            self.saveState()
            if self._pageNumber == 1:
                self.setFillColor(escuro)
                self.rect(0, alt_pag - 30 * mm, larg_pag, 30 * mm, stroke=0, fill=1)
                x = marg
                if icone:
                    self.drawImage(icone, marg, alt_pag - 23 * mm, 14 * mm, 14 * mm, mask="auto")
                    x = marg + 18 * mm
                self.setFillColor(colors.white)
                self.setFont(negrito, 17)
                self.drawString(x, alt_pag - 14 * mm, titulo)
                self.setFont(normal, 8.5)
                self.setFillColor(colors.HexColor("#B8C7D5"))
                self.drawString(x, alt_pag - 20 * mm, subtitulo[:150])
                self.setFont(normal, 8)
                self.drawRightString(larg_pag - marg, alt_pag - 14 * mm, f"{total} canais")
                self.drawRightString(larg_pag - marg, alt_pag - 20 * mm, f"Gerado em {gerado}")
            else:
                self.setFont(negrito, 9)
                self.setFillColor(escuro)
                self.drawString(marg, alt_pag - 10 * mm, titulo)
                self.setStrokeColor(linha)
                self.setLineWidth(0.6)
                self.line(marg, alt_pag - 12 * mm, larg_pag - marg, alt_pag - 12 * mm)
            self.setFont(normal, 7.5)
            self.setFillColor(suave)
            self.drawString(marg, 8 * mm, "PYProg  ·  programação de rádios")
            self.drawRightString(larg_pag - marg, 8 * mm, f"Página {self._pageNumber} de {n}")
            self.restoreState()

    doc = SimpleDocTemplate(caminho, pagesize=A4, leftMargin=marg, rightMargin=marg, topMargin=16 * mm,
                            bottomMargin=15 * mm, title=titulo, author="PYProg")
    doc.build(hist, canvasmaker=Canvas)


def abre_arquivo(caminho):
    try:
        if sys.platform == "win32":
            os.startfile(caminho)
    except Exception:
        pass


def exporta(app, nome_base, titulo, subtitulo_extra, colunas, linhas, grupos=None, colunas_grupos=None):
    """Pergunta o formato (PDF ou CSV), o local, e grava. linhas: todas, na ordem; grupos: para o PDF."""
    if not linhas:
        messagebox.showinfo("Exportar", "Não há canais em uso para exportar.")
        return
    j = tk.Toplevel(app.raiz)
    j.title("Exportar a lista de canais")
    j.transient(app.raiz)
    j.resizable(False, False)
    f = ttk.Frame(j, padding=(22, 18, 22, 16))
    f.pack(fill="both", expand=True)
    ttk.Label(f, text="Exportar a lista de canais", font=app.fonte_titulo).pack(anchor="w")
    ttk.Label(f, text=f"{len(linhas)} canais em uso. Escolha o formato:", style="Suave.TLabel").pack(
        anchor="w", pady=(2, 12))
    fmt = tk.StringVar(value=app.cfg.get("exportar_formato", "pdf"))
    ttk.Radiobutton(f, text="PDF, para ver e imprimir", value="pdf", variable=fmt).pack(anchor="w", pady=2)
    ttk.Radiobutton(f, text="CSV, para abrir no Excel ou em outra planilha", value="csv",
                    variable=fmt).pack(anchor="w", pady=2)
    abrir = tk.BooleanVar(value=True)
    ttk.Checkbutton(f, text="Abrir o arquivo depois de exportar", variable=abrir).pack(anchor="w", pady=(10, 0))
    bt = ttk.Frame(f)
    bt.pack(fill="x", pady=(16, 0))

    def ok():
        formato = fmt.get()
        app.cfg["exportar_formato"] = formato
        j.destroy()
        ext = "." + formato
        caminho = filedialog.asksaveasfilename(
            title="Exportar a lista de canais", defaultextension=ext,
            initialdir=app.cfg.get("pasta_exportar") or os.path.expanduser("~"),
            initialfile=f"{nome_base}{ext}",
            filetypes=[("PDF", "*.pdf")] if formato == "pdf" else [("CSV (planilha)", "*.csv")])
        if not caminho:
            return
        app.cfg["pasta_exportar"] = os.path.dirname(caminho)
        sub = f"{subtitulo_extra}  ·  {len(linhas)} canais  ·  exportado em {time.strftime('%d/%m/%Y %H:%M')}"
        try:
            if formato == "pdf":
                if grupos:
                    grava_pdf(caminho, titulo, sub, colunas_grupos or colunas, linhas, grupos)
                else:
                    grava_pdf(caminho, titulo, sub, colunas, linhas)
            else:
                grava_csv(caminho, colunas, linhas)
        except PermissionError:
            messagebox.showerror("Exportar", "Não foi possível gravar o arquivo. Se ele estiver aberto em outro "
                                             "programa, feche-o e tente de novo.")
            return
        except Exception as e:
            messagebox.showerror("Exportar", f"Não foi possível exportar: {e}")
            return
        app.status.config(text=f"Lista exportada: {os.path.basename(caminho)}")
        if abrir.get():
            abre_arquivo(caminho)
    ttk.Button(bt, text="Cancelar", command=j.destroy).pack(side="right")
    ttk.Button(bt, text="Exportar...", command=ok, style="Neutro.TButton").pack(side="right", padx=8)
    j.bind("<Escape>", lambda e: j.destroy())
    j.bind("<Return>", lambda e: ok())
    j.update_idletasks()
    r = app.raiz
    j.geometry(f"+{r.winfo_rootx() + (r.winfo_width() - j.winfo_reqwidth()) // 2}"
               f"+{r.winfo_rooty() + max(0, (r.winfo_height() - j.winfo_reqheight()) // 3)}")
    j.grab_set()

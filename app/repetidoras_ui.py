"""Janela de busca de repetidoras (consulta direta à RepeaterBook) e entrada dos canais escolhidos."""
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

import conversao as cv
import conversao_ui as cu
import organiza as org
import repetidoras_api as api
import programacao as pg
import repetidoras as rep
import tema


URL_LOGIN = "https://www.repeaterbook.com/argus/login.php?return=%2Fuser%2Fapi_apps.php"
URL_DOC = "https://www.repeaterbook.com/wiki/doku.php?id=api"


class JanelaRepetidoras(tk.Toplevel):
    def __init__(self, app, perfil, aba=None):
        """app: janela principal. perfil: perfil do rádio escolhido (para conferir os canais).
        aba: tela de programação, só quando há um arquivo de rádio aberto (necessário para adicionar)."""
        super().__init__(app.raiz)
        self.app = app
        self.aba = aba
        self.prog = aba.prog if aba is not None else None
        self.perfil = perfil
        self.title("Buscar repetidoras")
        self.transient(app.raiz)
        self.resizable(True, True)
        self.regs, self.tem_coord = [], False
        self.marcadas = set()
        self.resultado = []   # (registro, distância, canal ou None, situação)

        f = ttk.Frame(self, padding=16)
        f.pack(fill="both", expand=True)

        topo = ttk.Frame(f)
        topo.pack(fill="x")
        self.bt_token = ttk.Menubutton(topo, text="Token da RepeaterBook")
        self.bt_token.pack(side="left")
        self.menu_token = tk.Menu(self.bt_token, tearoff=0)
        self.bt_token["menu"] = self.menu_token
        self._monta_menu_token()

        grade = ttk.Frame(f, padding=(0, 12, 0, 0))
        grade.pack(fill="x")
        bandas = ttk.Frame(grade)
        bandas.grid(row=0, column=0, columnspan=3, sticky="w", pady=3)
        ttk.Label(bandas, text="Banda").pack(side="left", padx=(0, 10))
        self.bandas_vars = []
        for _, _, nome in rep.BANDAS_REPETIDORAS:
            v = tk.BooleanVar(value=False)
            self.bandas_vars.append(v)
            ttk.Checkbutton(bandas, text=nome, variable=v).pack(side="left", padx=(0, 14))
        self.bt_buscar = ttk.Button(bandas, text="Buscar repetidoras", command=self._consulta)
        self.bt_buscar.pack(side="left", padx=(18, 0))
        tema.dica_ao_parar(self.bt_buscar, self._texto_dica_busca)
        self.so_an = tk.BooleanVar(value=True)
        ttk.Checkbutton(grade, text="Só modos analógicos (FM)", variable=self.so_an
                        ).grid(row=1, column=1, sticky="w", padx=8, pady=3)
        self.so_abertas = tk.BooleanVar(value=False)
        ttk.Checkbutton(grade, text="Só repetidoras de uso aberto", variable=self.so_abertas
                        ).grid(row=1, column=2, sticky="w", padx=(18, 0), pady=3)
        ttk.Label(grade, text="Ponto de referência").grid(row=2, column=0, sticky="w", pady=(10, 3))
        pt = ttk.Frame(grade)
        pt.grid(row=2, column=1, sticky="w", padx=8, pady=(10, 3))
        self.lat, self.lon, self.km = tk.StringVar(), tk.StringVar(), tk.StringVar()
        salvo = app.cfg.get("ponto_referencia") or {}
        if salvo:
            self.lat.set(f"{salvo['lat']:.4f}".replace(".", ","))
            self.lon.set(f"{salvo['lon']:.4f}".replace(".", ","))
        ttk.Label(pt, text="Latitude").pack(side="left")
        self.e_lat = ttk.Entry(pt, textvariable=self.lat, width=11)
        self.e_lat.pack(side="left", padx=(4, 10))
        ttk.Label(pt, text="Longitude").pack(side="left")
        self.e_lon = ttk.Entry(pt, textvariable=self.lon, width=11)
        self.e_lon.pack(side="left", padx=(4, 10))
        ttk.Label(pt, text="Raio (km)").pack(side="left")
        self.e_km = ttk.Entry(pt, textvariable=self.km, width=7)
        self.e_km.pack(side="left", padx=(4, 0))
        ttk.Button(pt, text="Usar minha localização", command=self._localiza).pack(side="left", padx=(12, 0))
        ttk.Button(pt, text="Ver ponto no mapa", command=self._mapa).pack(side="left", padx=(8, 0))
        self.lb_coord = ttk.Label(grade, text="", foreground="#666")
        self.lb_coord.grid(row=3, column=1, sticky="w", padx=8)

        ttk.Button(f, text="Buscar", command=self._busca).pack(anchor="w", pady=(12, 8))

        cols = ("marca", "freq", "desloc", "tom", "nome", "cidade", "aberta", "dist", "situacao")
        self.tv = ttk.Treeview(f, columns=cols, show="headings", selectmode="none", height=14)
        titulos = {"marca": "", "freq": "Frequência (MHz)", "desloc": "Deslocamento", "tom": "Tom",
                   "nome": "Nome", "cidade": "Cidade", "aberta": "Aberta", "dist": "Distância (km)",
                   "situacao": "Situação"}
        larguras = {"marca": 40, "freq": 120, "desloc": 110, "tom": 110, "nome": 110, "cidade": 170,
                    "aberta": 70, "dist": 100, "situacao": 240}
        for c in cols:
            self.tv.heading(c, text=titulos[c])
            self.tv.column(c, width=larguras[c], anchor="w")
        self.tv.pack(fill="both", expand=True)
        self.tv.bind("<Button-1>", self._clique_marca)
        self.tv.tag_configure("ok", foreground="#1a7f37")
        self.tv.tag_configure("nao", foreground="#888888")

        barra = ttk.Frame(f, padding=(0, 10, 0, 0))
        barra.pack(fill="x")
        ttk.Button(barra, text="Marcar todas as prontas", command=self._marca_prontas).pack(side="left")
        ttk.Button(barra, text="Desmarcar todas", command=self._desmarca_todas).pack(side="left", padx=(8, 0))
        ttk.Button(barra, text="Adicionar selecionadas...", command=self._adiciona).pack(side="right")
        self.status = ttk.Label(f, text="Informe o token no menu Token da RepeaterBook e clique em Buscar repetidoras.")
        self.status.pack(anchor="w", pady=(8, 0))
        rodape = ttk.Frame(f)
        rodape.pack(fill="x", pady=(4, 0))
        ttk.Label(rodape, text=api.ATRIBUICAO, foreground="#666").pack(side="left")
        ttk.Button(rodape, text="Copiar amostra da resposta (diagnóstico)",
                   command=self._copia_amostra).pack(side="right")

        if self.prog is None:
            self.status.config(text="Busca sem rádio aberto. Para adicionar canais, abra ou leia um rádio antes.")
        self.bind("<Escape>", lambda e: self.destroy())
        self._ajusta_coord()

    # ------------------------------------------------------------ consulta
    # ------------------------------------------------------------ token
    def _token_salvo(self):
        return (self.app.cfg.get("repeaterbook_token") or "").strip()

    def _monta_menu_token(self):
        m = self.menu_token
        m.delete(0, "end")
        salvo = bool(self._token_salvo())
        self.bt_token.config(text="Token salvo" if salvo else "Token da RepeaterBook: não informado")
        m.add_command(label="Colar token da área de transferência", command=self._cola_token)
        m.add_command(label="Como obter o token (passo a passo)...", command=self._instrucao_token)
        m.add_separator()
        m.add_command(label="Entrar no painel API Apps", command=lambda: webbrowser.open(URL_LOGIN))
        m.add_command(label="Documentação da API", command=lambda: webbrowser.open(URL_DOC))

    def _texto_dica_busca(self):
        if self._token_salvo():
            return ""
        return "Antes da busca, insira o token da RepeaterBook no menu Token da RepeaterBook."

    def _cola_token(self, janela=None):
        try:
            texto = self.clipboard_get().strip()
        except tk.TclError:
            texto = ""
        if not texto.startswith("rbuapp_"):
            messagebox.showwarning("Token da RepeaterBook",
                                   "A área de transferência não tem um token do PYProg (ele começa com "
                                   "\"rbuapp_\"). Copie o token no painel e tente de novo.", parent=janela or self)
            return
        self.app.cfg["repeaterbook_token"] = texto
        self.app._salva_cfg()
        if janela is not None:
            janela.destroy()
        self._monta_menu_token()
        self.status.config(text="Token salvo. Clique em Buscar repetidoras.")

    def _instrucao_token(self):
        """Explica o cadastro e a geração do token, com os links, e cola o token da área de transferência."""
        j = tk.Toplevel(self)
        j.title("Token da RepeaterBook")
        j.transient(self)
        j.resizable(False, False)
        f = ttk.Frame(j, padding=18)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="A busca de repetidoras exige cadastro na RepeaterBook e um token pessoal.",
                  wraplength=520, justify="left").pack(anchor="w")
        passos = [
            ("1. Entre na sua conta da RepeaterBook (ou crie uma) pelo link abaixo. Ele leva direto ao painel de API Apps.",
             None),
            ("2. Na lista de aplicativos, escolha o PYProg (ID 160) e gere o token.", None),
            ("3. Copie a chave completa logo após gerar: ela aparece só uma vez.", None),
            ("4. Volte a este programa, abra o menu Token da RepeaterBook e escolha Colar token da área de transferência.", None),
        ]
        for texto, _ in passos:
            ttk.Label(f, text=texto, wraplength=520, justify="left").pack(anchor="w", pady=(8, 0))
        links = [
            ("Entrar na RepeaterBook e abrir o painel de API Apps",
             "https://www.repeaterbook.com/argus/login.php?return=%2Fuser%2Fapi_apps.php"),
            ("Instruções da API na RepeaterBook",
             "https://www.repeaterbook.com/wiki/doku.php?id=api"),
        ]
        for texto, url in links:
            l = tk.Label(f, text=texto, fg="#1a5fb4", cursor="hand2", font=("Segoe UI", 9, "underline"))
            l.pack(anchor="w", pady=(6, 0))
            l.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))
        ttk.Label(f, text="O token dá acesso à sua conta. Não o compartilhe com ninguém.",
                  foreground="#666", wraplength=520, justify="left").pack(anchor="w", pady=(12, 0))
        linha = ttk.Frame(f, padding=(0, 14, 0, 0))
        linha.pack(fill="x")

        ttk.Button(linha, text="Colar token da área de transferência",
                   command=lambda: self._cola_token(j)).pack(side="left")
        ttk.Button(linha, text="Fechar", command=j.destroy).pack(side="right")
        j.bind("<Escape>", lambda e: j.destroy())
        j.grab_set()

    def _consulta(self):
        token = self._token_salvo()
        if not token:
            self._instrucao_token()
            return
        self.config(cursor="watch")
        self.status.config(text="Consultando a RepeaterBook...")
        self.update_idletasks()
        try:
            brutos = api.consulta(token, api.PARAMETROS_BRASIL)
        except api.ErroAPI as e:
            self.status.config(text="A consulta não foi concluída.")
            messagebox.showerror("Buscar repetidoras", str(e), parent=self)
            return
        finally:
            self.config(cursor="")
        self.brutos = brutos
        self.regs, self.tem_coord = api.normaliza_lista(brutos)
        if not brutos:
            self.status.config(text="A RepeaterBook não devolveu repetidoras para esta consulta.")
        elif not self.regs:
            campos = ", ".join(sorted(brutos[0].keys())) if isinstance(brutos[0], dict) else "(formato inesperado)"
            self.status.config(text=f"Recebidos {len(brutos)} registros, mas nenhum com frequência reconhecida. "
                                    f"Campos recebidos: {campos}")
        else:
            self.status.config(text=f"{len(self.regs)} repetidoras recebidas da RepeaterBook.")
        self._ajusta_coord()
        self._busca()

    def _ajusta_coord(self):
        self.lb_coord.config(text="" if self.tem_coord else
                             "Sem coordenadas nas repetidoras recebidas, então o raio não filtra.")

    def _localiza(self):
        """Preenche o ponto de referência com a localização do Windows, ou com o ponto salvo."""
        try:
            lat, lon = rep.localizacao_windows()
        except RuntimeError as e:
            salvo = self.app.cfg.get("ponto_referencia")
            if salvo:
                self._mostra_ponto(salvo["lat"], salvo["lon"])
                self.status.config(text=f"Não foi possível usar a localização ({e}). Usei o ponto salvo.")
            else:
                messagebox.showinfo(
                    "Buscar repetidoras",
                    f"Não foi possível obter a localização: {e}.\n\nDigite a latitude e a longitude do seu ponto, "
                    "ou ative a localização do Windows em Configurações, Privacidade e segurança, Localização.",
                    parent=self)
            return
        self._mostra_ponto(lat, lon)
        self.status.config(text="Localização obtida do Windows e salva como ponto de referência.")

    def _mapa(self):
        """Abre o ponto de referência num mapa no navegador (OpenStreetMap)."""
        try:
            lat, lon = self._ponto()
        except ValueError as e:
            messagebox.showerror("Buscar repetidoras", str(e), parent=self)
            return
        if lat is None:
            messagebox.showinfo("Buscar repetidoras", "Informe a latitude e a longitude do ponto.", parent=self)
            return
        webbrowser.open(f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=13/{lat}/{lon}")

    def _mostra_ponto(self, lat, lon):
        self.lat.set(f"{lat:.4f}".replace(".", ","))
        self.lon.set(f"{lon:.4f}".replace(".", ","))
        self._salva_ponto(lat, lon)

    def _salva_ponto(self, lat, lon):
        self.app.cfg["ponto_referencia"] = {"lat": lat, "lon": lon}
        self.app._salva_cfg()

    # ------------------------------------------------------------ busca
    def _faixas(self):
        """Faixas (MHz) das bandas marcadas; None se nenhuma marcada (sem filtro de banda)."""
        sel = [(a, b) for v, (a, b, _) in zip(self.bandas_vars, rep.BANDAS_REPETIDORAS) if v.get()]
        return sel or None

    def _ponto(self):
        if not (self.lat.get().strip() and self.lon.get().strip()):
            return None, None
        try:
            return (float(self.lat.get().replace(",", ".")), float(self.lon.get().replace(",", ".")))
        except ValueError:
            raise ValueError("Latitude e longitude devem ser números (ex.: -21,2 e -48,5).")

    def _raio(self):
        txt = self.km.get().strip().replace(",", ".")
        if not txt:
            return None
        try:
            return float(txt)
        except ValueError:
            raise ValueError("O raio deve ser um número, em quilômetros.")

    def _busca(self):
        if not self.regs:
            return
        try:
            ponto = self._ponto()
            ponto = ponto if ponto[0] is not None else None
            km = self._raio() if ponto else None
        except ValueError as e:
            messagebox.showerror("Buscar repetidoras", str(e), parent=self)
            return
        if ponto and not self.tem_coord:
            ponto, km = None, None
        if ponto:
            self._salva_ponto(*ponto)
        achados = rep.filtra(self.regs, faixas=self._faixas(), so_analogicas=self.so_an.get(),
                             texto="", ponto=ponto, km=km, so_abertas=self.so_abertas.get())
        self.tv.delete(*self.tv.get_children())
        self.resultado = []
        prontas = 0
        for i, (r, dist) in enumerate(achados):
            canal, motivo = rep.para_canal(r)
            if canal is None:
                situacao, tag = f"Não usada: {motivo}", "nao"
            else:
                situacao, tag = "Pronta para adicionar", "ok"
                prontas += 1
            self.resultado.append((r, dist, canal, situacao))
            tom = r["r_tone"] if r["tom"] in ("Tone", "TSQL") else ""
            if r["tom"] == "DTCS":
                tom = f"D{r['dtcs']} {r['dtcs_pol']}"
            desloc = f"{r['offset_mhz']:.3f}" if r["duplex"] in ("+", "-") else ""
            self.tv.insert("", "end", iid=str(i), tags=(tag,), values=(
                "☐", f"{r['freq_mhz']:.4f}", (r["duplex"] + " " + desloc).strip(), tom, r["nome"] or r["comentario"],
                r["cidade"], "sim" if r["aberta"] else "não",
                f"{dist:.1f}" if dist is not None else "", situacao))
        self._marca_prontas()
        self.status.config(text=f"{len(achados)} repetidoras encontradas, {prontas} prontas para adicionar."
                                + self._resumo_filtros())

    def _resumo_filtros(self):
        """Quantas repetidoras restaram em cada filtro, para achar onde a lista esvazia."""
        if not self.regs:
            return " A RepeaterBook não devolveu repetidoras para esta consulta."
        faixas = self._faixas()
        na_banda = [r for r in self.regs if not faixas or any(a <= r["freq_mhz"] <= b for a, b in faixas)]
        analogicas = [r for r in na_banda if r["modo"] in rep.MODOS_ANALOGICOS]
        modos = sorted({r["modo"] or "(vazio)" for r in self.regs})[:8]
        return (f" (Recebidas: {len(self.regs)}; na banda: {len(na_banda)}; "
                f"analógicas: {len(analogicas)}; valores de modo: {', '.join(modos)}.)")

    def _copia_amostra(self):
        """Copia dois registros da resposta (sem o token) para a área de transferência, para diagnóstico."""
        if not getattr(self, "brutos", None):
            messagebox.showinfo("Buscar repetidoras", "Faça uma consulta antes de copiar a amostra.", parent=self)
            return
        import json
        self.clipboard_clear()
        self.clipboard_append(json.dumps(self.brutos[:2], ensure_ascii=False, indent=1))
        self.status.config(text="Amostra copiada. Cole-a na conversa para o diagnóstico.")

    def _atualiza_marca(self, iid):
        self.tv.set(iid, "marca", "☑" if iid in self.marcadas else "☐")

    def _clique_marca(self, e):
        """Clique na coluna da caixa: marca ou desmarca a linha (só as prontas podem ser marcadas)."""
        if self.tv.identify_region(e.x, e.y) != "cell" or self.tv.identify_column(e.x) != "#1":
            return None
        iid = self.tv.identify_row(e.y)
        if not iid or self.resultado[int(iid)][2] is None:
            return "break"
        if iid in self.marcadas:
            self.marcadas.discard(iid)
        else:
            self.marcadas.add(iid)
        self._atualiza_marca(iid)
        return "break"

    def _marca_prontas(self):
        self.marcadas = {iid for iid in self.tv.get_children() if self.resultado[int(iid)][2] is not None}
        for iid in self.tv.get_children():
            self._atualiza_marca(iid)

    def _desmarca_todas(self):
        self.marcadas = set()
        for iid in self.tv.get_children():
            self._atualiza_marca(iid)

    # ------------------------------------------------------------ adicionar
    def _adiciona(self):
        if self.prog is None:
            messagebox.showinfo("Buscar repetidoras",
                                "Para adicionar canais, abra ou leia um rádio antes. A busca funciona sem isso.",
                                parent=self)
            return
        escolhidos = [self.resultado[int(i)][2] for i in sorted(self.marcadas, key=int)
                      if self.resultado[int(i)][2] is not None]
        if not escolhidos:
            messagebox.showinfo("Buscar repetidoras", "Nenhuma repetidora pronta está marcada.", parent=self)
            return
        destino = self.prog.perfil
        linhas = cv.converte(escolhidos, destino)
        cu.JanelaRevisao(self.app, linhas, destino, ao_importar=self._coloca,
                         origem_nome="RepeaterBook")

    def _coloca(self, canais):
        """Coloca as repetidoras nas posições livres da zona visível (ou da lista, sem zonas)."""
        ad = org.Uv(self.prog)
        faixas = ad.faixas()
        faixa = faixas[max(0, self.aba.cb_zona.current())] if self.prog.perfil.tem_zonas else faixas[0]
        livres = [n for n in faixa if self.prog.canal(n).vazio]
        if len(canais) > len(livres):
            messagebox.showinfo(
                "Buscar repetidoras",
                f"Há só {len(livres)} posições livres nesta zona ou lista, e {len(canais)} canais para colocar. "
                "Escolha outra zona ou apague canais antes.", parent=self)
            return False
        for c, n in zip(canais, livres):
            c.numero = n
            self.prog.define_canal(c)
        self.aba._registra_edicao()
        self.aba._atualiza_tudo()
        self.app.status.config(text=f"{len(canais)} repetidoras adicionadas. Confira e use Gravar no rádio.")
        self.destroy()
        return True

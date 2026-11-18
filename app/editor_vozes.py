# -*- coding: utf-8 -*-
"""
PYProg: programação de rádios.

Janela principal: escolha do rádio, programação (Baofeng e Icom), vozes e
imagem de abertura dos Baofeng compatíveis.
"""
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import traceback
from tkinter import filedialog, messagebox, ttk

import ajuda
import atualizacao
from arquivos import RegistroEnvio, grava_json
import configuracao_radio as cr
import deteccao_porta as dp
import dmr_ui
import icom_ui
import imagem_ui
import interrupcao
import licencas
import programacao_ui
import tema
import vozes_core as vc

interrupcao.instala()          # registra as portas seriais para poder interromper operações

NOME_APP = "PYProg"
SUBTITULO_APP = "Programação de rádios"
TITULO = f"{NOME_APP} {vc.VERSAO}"
# Rádios conhecidos, na ordem da lista. A janela "Rádios" (engrenagem) escolhe quais aparecem.
NOMES_RADIO = {
    "UV17ProGPS": "UV-17 Pro GPS",
    "UV17Pro": vc.MODELOS["UV17Pro"].nome,
    "UV17RPlus": "UV-17R Plus",
    "UV21Pro": "UV-21 Pro",
    "UV21ProGPS": "UV-21 Pro GPS",
    "UV5R": "UV-5R",
    "IC2730A": "Icom IC-2730A",
    "RT3S": "Retevis RT3S GPS",
}
# O Baofeng DM-1701 (mesmo formato do RT3S) fica fora da lista até haver um rádio com o
# firmware original para testar; o código continua em dmr380/dmr_usb.
RADIOS_ICOM = {"IC2730A"}
RADIOS_DMR = {"RT3S"}           # só o arquivo .rdt do CPS
GRUPOS_RADIO = [
    ("Baofeng, família UV-17", ["UV17ProGPS", "UV17Pro", "UV17RPlus", "UV21Pro", "UV21ProGPS"]),
    ("Baofeng, família UV-5R", ["UV5R"]),
    ("Icom", ["IC2730A"]),
    ("DMR (organiza o arquivo .rdt do programa oficial)", ["RT3S"]),
]
NOMES_MEUS_RADIOS = {"UV5R": "UV-5R (UV-5RA, UV-5RE, UV-5X, Retevis RT5R...)",
                     "UV17Pro": "UV-17 Pro, UV-17R e UV-17L",
                     "RT3S": "Retevis RT3S GPS (TYT MD-UV380 e MD-UV390)"}
# Tabela da janela "Rádios": programação, vozes, imagem, detalhes
TABELA_RADIOS = {
    "UV17ProGPS": ("sim", "sim", "sim", "Programação, vozes e imagem de abertura (150 x 128)."),
    "UV17Pro": ("sim", "sim", "não", "Vale para UV-17 Pro, UV-17R e UV-17L. Programação e vozes."),
    "UV17RPlus": ("sim", "não", "não", "Mesma comunicação e mesmo mapa de memória do UV-17 Pro."),
    "UV21Pro": ("sim", "não", "sim", "UV-21 Pro V2, sem GPS. Imagem de abertura de 128 x 160. O primeiro "
                                           "UV-21 Pro (V1) não é suportado."),
    "UV21ProGPS": ("sim", "não", "sim", "Mesma comunicação do UV-17 Pro GPS, com as faixas do UV-21 Pro. "
                                              "Imagem de abertura de 128 x 160."),
    "UV5R": ("sim", "não", "não", "Vale também para UV-5RA, UV-5RE, UV-5R Plus, UV-5X, Retevis RT5R, RT5RV "
                                        "e RT5, Rugged RH5R, Radioddity UV-5R EX e Ansoko A-5R. Não use para "
                                        "BF-F8HP, UV-82, UV-5X3 ou UV-6."),
    "IC2730A": ("sim", "não", "não", "Canais, bancos e ajustes, com arquivos .icf do programa da Icom "
                                           "(CS-2730)."),
    "RT3S": ("sim", "não", "não", "TYT MD-UV380/UV390. Também edita o arquivo .rdt. "
                                         "Com firmware OpenGD77, não é suportado."),
}
ESCOLHER_RADIOS = "Escolher rádios..."
# Ícone de cada seção do menu lateral (pelo nome da seção)
ICONES_SECAO = {
    "Geral": "sliders-horizontal", "Menu": "square-menu", "Botões": "pointer", "Mensagens": "message-circle",
    "Privacidade": "shield-check", "Emergência": "siren", "Contatos e TGs": "users", "Grupos de RX": "layers",
    "Zonas": "map-pin", "Varredura": "scan-search", "Canais": "radio", "DTMF": "grip", "VFO": "activity",
    "GPS": "satellite", "Bancos": "library", "Ajustes do rádio": "settings",
}
TESTADOS = {"UV17ProGPS", "UV5R", "IC2730A", "RT3S"}          # lidos e gravados com sucesso num rádio real
MEUS_RADIOS_PADRAO = ["UV17ProGPS", "UV21Pro", "UV5R", "IC2730A", "RT3S"]
# Linha do rodapé ao escolher o modelo
RECURSOS_RADIO = {
    "UV17ProGPS": "programação, vozes e imagem de abertura.",
    "UV17Pro": "programação e vozes.",
    "UV17RPlus": "só a programação (canais, zonas e ajustes). Vozes e imagem de abertura não foram testadas "
                 "neste rádio.",
    "UV21Pro": "programação e imagem de abertura (as vozes deste rádio ainda não podem ser trocadas).",
    "UV21ProGPS": "programação e imagem de abertura (as vozes deste rádio ainda não podem ser trocadas).",
    "UV5R": "só a programação (canais e ajustes). As vozes e a imagem de abertura deste rádio não podem "
            "ser trocadas pelo cabo.",
    "IC2730A": "canais, bancos e ajustes.",
    "RT3S": "programação completa, também pelo arquivo .rdt.",
}
_RISCO = "\n\nLeia o rádio antes de gravar, confira os canais e guarde o backup. O uso é por sua conta e risco."
# Aviso ao escolher um modelo ainda não testado em todas as funções
AVISO_EXPERIMENTAL = {
    "UV5R": "O firmware desse modelo muda sem aviso, e o programa pode não funcionar com o seu aparelho "
            "ou com um compatível.",
    "UV21Pro": "O UV-21 Pro usa a mesma comunicação do UV-17 Pro, mas esta opção ainda não foi testada "
               "com o rádio, nem na leitura nem na gravação." + _RISCO,
    "UV21ProGPS": "O UV-21 Pro GPS usa a mesma comunicação do UV-17 Pro GPS, com as faixas do UV-21 Pro, "
                  "mas esta opção ainda não foi testada com o rádio." + _RISCO,
    "UV17RPlus": "O UV-17R Plus usa a mesma comunicação e o mesmo mapa de memória do UV-17 Pro, mas esta "
                 "opção ainda não foi testada com o rádio." + _RISCO,
}

COR_FABRICA = tema.C["suave"]
COR_PERSONALIZADA = tema.C["ok"]


def pasta_config():
    base = os.environ.get("APPDATA") or os.path.expanduser("~/.config")
    p = os.path.join(base, "EditorVozesBaofeng")
    os.makedirs(p, exist_ok=True)
    return p


ARQ_ERROS = "erros.log"


def registra_erro(e):
    """Acrescenta o erro (com a pilha de chamadas) ao erros.log da pasta de backups, para diagnóstico."""
    try:
        pasta = os.path.join(pasta_config(), "Backups")
        os.makedirs(pasta, exist_ok=True)
        arq = os.path.join(pasta, ARQ_ERROS)
        if os.path.exists(arq) and os.path.getsize(arq) > 512 * 1024:
            os.replace(arq, arq + ".antigo")
        with open(arq, "a", encoding="utf-8") as f:
            f.write(f"\n{time.strftime('%Y-%m-%d %H:%M:%S')}  PYProg {vc.VERSAO}\n")
            f.write("".join(traceback.format_exception(type(e), e, e.__traceback__)))
    except Exception:
        pass


def kb(n):
    return f"{n / 1024:,.0f}".replace(",", ".")


class Reprodutor:
    """Prévia assíncrona em arquivo; stop invalida também pedidos ainda em preparo."""
    def __init__(self):
        self.arquivo = None
        self.proc = None
        self._trava = threading.Lock()
        self._pedido = 0

    def _para_sem_trava(self):
        if sys.platform == "win32":
            import winsound
            winsound.PlaySound(None, 0)
        elif self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=0.2)
            except ProcessLookupError:
                pass
        self.proc = None
        if self.arquivo:
            try:
                os.unlink(self.arquivo)
            except OSError:
                pass
            self.arquivo = None

    def novo_pedido(self):
        with self._trava:
            self._pedido += 1
            self._para_sem_trava()
            return self._pedido

    def toca(self, adpcm: bytes, pedido=None):
        if pedido is None:
            pedido = self.novo_pedido()
        wav = vc.pcm_para_wav(vc.adpcm_decodifica(adpcm))
        with self._trava:
            if pedido != self._pedido:
                return  # Esc/Parar ou uma prévia mais recente venceu este pedido.
            fd, self.arquivo = tempfile.mkstemp(prefix="baofeng_audio_", suffix=".wav")
            with os.fdopen(fd, "wb") as f:
                f.write(wav)
            if sys.platform == "win32":
                import winsound
                winsound.PlaySound(self.arquivo, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
                return
            for cmd in (["aplay", "-q"], ["afplay"], ["paplay"]):
                try:
                    self.proc = subprocess.Popen(cmd + [self.arquivo])
                    return
                except FileNotFoundError:
                    continue
            self._para_sem_trava()
            raise RuntimeError("Nenhum reprodutor de áudio local disponível.")

    def para(self):
        self.novo_pedido()


class Linha:
    def __init__(self, app, pai, slot, rotulo, linha):
        self.app, self.slot = app, slot
        self.var = tk.StringVar(value=app.pacote.textos.get(slot, ""))
        self.var.trace_add("write", self._texto_mudou)
        ttk.Label(pai, text=f"{slot:03d}", width=4).grid(row=linha, column=0, padx=(4, 2), pady=1)
        ttk.Label(pai, text=rotulo, width=17).grid(row=linha, column=1, sticky="w")
        ttk.Entry(pai, textvariable=self.var, width=32).grid(row=linha, column=2, padx=2, sticky="we")
        self.estado = tk.Label(pai, width=22, anchor="w", font="TkDefaultFont", bg=tema.C["fundo"])
        self.estado.grid(row=linha, column=3, padx=4)
        botoes = [("▶", self.ouvir, 3), ("Gerar voz", self.gerar, 9), ("Arquivo...", self.arquivo, 9),
                  ("Silenciar", self.silenciar, 8), ("Base", self.fabrica, 7)]
        for col, (txt, fn, w) in enumerate(botoes, start=4):
            b = ttk.Button(pai, text=txt, width=w, command=fn)
            b.grid(row=linha, column=col, padx=1)
            app.botoes_ocupado.append(b)
        self.atualiza()

    def _texto_mudou(self, *_):
        self.app.pacote.textos[self.slot] = self.var.get()
        self.atualiza()

    def atualiza(self):
        p = self.app.pacote
        if not p.tem_fabrica and self.slot not in p.origens:
            txt, cor = "Falta gerar", tema.C["aviso"]
        elif p.eh_fabrica(self.slot):
            txt, cor = "Pacote base", COR_FABRICA
        else:
            origem = p.origens.get(self.slot, {})
            txt, cor = origem.get("tipo", "Personalizada"), COR_PERSONALIZADA
            if vc.idioma_voz(origem.get("voz")) != "pt":
                txt = "Gerada em " + {"en": "inglês", "es": "espanhol", "zh": "chinês"}[vc.idioma_voz(origem.get("voz"))]
            elif origem.get("tipo") == "Gerada" and origem.get("texto") != p.textos.get(self.slot, "").strip():
                txt, cor = "Texto pendente", tema.C["aviso"]
        self.estado.config(text=f"{txt} ({p.duracao(self.slot):.1f} s)".replace(".", ","), fg=cor)

    def ouvir(self):
        self.app.reprodutor_toca(self.app.pacote.vozes[self.slot])

    def gerar(self):
        texto = self.var.get().strip()
        if not texto:
            messagebox.showwarning(TITULO, "Digite o texto a ser falado.")
            return
        self.app.executa(f"Gerando voz: {texto}", lambda: self.app.gera_slot(self.slot, texto),
                         depois=lambda: self.ouvir())

    def arquivo(self):
        caminho = filedialog.askopenfilename(
            title="Escolher áudio",
            filetypes=[("Áudio", "*.mp3 *.wav *.flac *.ogg"), ("Todos", "*.*")])
        if not caminho:
            return
        vol = self.app.volume.get() / 100.0
        vel = self.app.velocidade.get() / 100.0

        def tarefa():
            self.app.pacote.define(self.slot, vc.importa_arquivo(caminho, volume=vol, velocidade=vel),
                                   {"tipo": "Importada", "arquivo": os.path.basename(caminho)})
        self.app.executa("Importando arquivo...", tarefa, depois=lambda: self.ouvir())

    def silenciar(self):
        try:
            self.app.pacote.define(self.slot, vc.silencio(), {"tipo": "Silenciada"})
        except vc.ErroPacote as e:
            messagebox.showerror(TITULO, str(e))
        self.app.atualiza_tudo()

    def fabrica(self):
        try:
            self.app.pacote.restaura(self.slot)
        except vc.ErroPacote as e:
            messagebox.showinfo(TITULO, str(e))
            return
        self.app.atualiza_tudo()


_dica_ao_parar = tema.dica_ao_parar


class App:
    def __init__(self, raiz):
        self.raiz = raiz
        raiz.geometry("1280x800")
        raiz.minsize(960, 560)
        try:
            raiz.state("zoomed")          # abre maximizado (Windows)
        except tk.TclError:
            pass
        self.fila = queue.Queue()
        self._info_atualizacao = None
        self.ocupado = False
        self.cancelar = threading.Event()
        self._estados_widgets = []
        self._snapshot_rascunho = None
        self._rascunhos = {}           # conteúdo já gravado em cada rascunho de programação
        self.botoes_ocupado = []
        self.linhas = []
        self.reprodutor = Reprodutor()
        self.cfg = self._carrega_cfg()
        vc.PASTA_FABRICA_USUARIO = os.path.join(pasta_config(), "Fabrica")
        self._indicativo_do_instalador()
        cr.define_indicativo(self.cfg.get("indicativo", cr.INDICATIVO))
        raiz.title(self.titulo_janela())
        if self.cfg.get("letra_v") != 2:      # v2.2: padrão de letra um pouco menor
            self.cfg["letra"], self.cfg["letra_v"] = 11, 2
        self._configura_fontes(int(self.cfg.get("letra", 11)))
        self.pacote = vc.PacoteVozes(self.cfg.get("modelo", "UV17ProGPS"))
        # Rádio escolhido no topo. O UV-5R só tem programação (sem vozes nem imagem),
        # por isso o pacote de vozes continua sendo o do último modelo com vozes.
        self.modelo_radio = self.cfg.get("modelo_radio", self.pacote.modelo.chave)
        if self.modelo_radio not in NOMES_RADIO:
            self.modelo_radio = self.pacote.modelo.chave
        meus = [k for k in self.cfg.get("meus_radios", MEUS_RADIOS_PADRAO) if k in NOMES_RADIO]
        if self.modelo_radio not in meus:
            meus.append(self.modelo_radio)
        self.meus_radios = meus
        self._aplica_textos_salvos()
        self._monta_topo()
        self._monta_status()
        self.corpo.pack(fill="both", expand=True)
        self.coluna.pack(side="left", fill="y")
        # Divisória entre o menu lateral e a área de trabalho (os dois são brancos)
        tk.Frame(self.corpo, bg=tema.C["borda_suave"], width=1).pack(side="left", fill="y")
        self.area.pack(side="left", fill="both", expand=True)
        self.lateral = tema.MenuLateral(self.coluna, self._escolhe_secao, self._menu_recolhido,
                                        recolhido=bool(self.cfg.get("menu_recolhido", False)),
                                        fonte_negrito=self.fonte_negrito)
        self.lateral.pack(fill="both", expand=True)
        self._aplica_recolhido(self.lateral.recolhido)
        self.principal.pack(fill="both", expand=True)
        self.raiz.after_idle(tema.atualiza_comandos)
        self.nb = ttk.Notebook(self.pg_vozes, style="Semabas.TNotebook")
        self.nb.pack(fill="both", expand=True, padx=12, pady=(4, 12))
        self.monta_abas()
        # A aba Programação tem uma tela para os Baofeng e outra para o Icom; só uma aparece.
        self.fr_baofeng = ttk.Frame(self.pg_prog)
        self.fr_icom = ttk.Frame(self.pg_prog)
        self.fr_dmr = ttk.Frame(self.pg_prog)
        self.programacao = programacao_ui.AbaProgramacao(self, self.fr_baofeng)
        self.icom = icom_ui.AbaIcom(self, self.fr_icom)
        self.dmr = dmr_ui.AbaDMR(self, self.fr_dmr)
        self.imagem = imagem_ui.AbaImagem(self, self.pg_img)
        for caderno in (self.principal, self.programacao.nb, self.icom.nb, self.dmr.nb):
            caderno.bind("<<NotebookTabChanged>>", self._sincroniza_lateral, add="+")
        self._aplica_modelo_radio()
        raiz.protocol("WM_DELETE_WINDOW", self.fechar)
        raiz.bind("<Escape>", lambda e: self.parar_audio())
        self.vozes_salvas = self.pacote.assinatura()
        raiz.after(100, self._processa_fila)
        raiz.after(300, self.recupera_rascunhos)
        raiz.after(2000, self._autosave)
        raiz.after(4000, self._verifica_atualizacao_automatica)

    # ----------------------------------------------------------- configuração
    def _carrega_cfg(self):
        try:
            with open(os.path.join(pasta_config(), "config.json"), encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _salva_cfg(self):
        textos = self.cfg.setdefault("textos", {})
        textos[self.pacote.modelo.chave] = {str(k): v for k, v in self.pacote.textos.items()}
        self.cfg["modelo"] = self.pacote.modelo.chave
        self.cfg["modelo_radio"] = self.modelo_radio
        self.cfg["meus_radios"] = self.meus_radios
        self.cfg["porta"] = self.porta.get()
        self.cfg["volume"] = round(self.volume.get())
        self.cfg["velocidade"] = round(self.velocidade.get())
        self.cfg["voz"] = self.voz.get()
        self.cfg["letra"] = self.tam_letra
        self.cfg["indicativo"] = cr.INDICATIVO
        try:
            grava_json(os.path.join(pasta_config(), "config.json"), self.cfg)
        except Exception:
            pass

    def _indicativo_do_instalador(self):
        """O instalador grava o nome/indicativo digitado em indicativo_instalacao.txt.
        Vale quando muda (nova instalação); campo em branco no instalador mantém o atual."""
        arq = os.path.join(os.path.dirname(os.path.abspath(__file__)), "indicativo_instalacao.txt")
        try:
            with open(arq, encoding="utf-16") as f:
                txt = f.read().strip()
        except (OSError, UnicodeError):
            return
        if txt and self.cfg.get("indicativo_instalacao") != txt:
            self.cfg["indicativo"] = txt
            self.cfg["indicativo_instalacao"] = txt

    def titulo_janela(self):
        return TITULO + (f"  |  {cr.INDICATIVO}" if cr.INDICATIVO else "")

    def _muda_indicativo(self, *_):
        # Só acompanha o valor; o limite de caracteres é garantido pela validação do campo.
        cr.define_indicativo(self.indicativo.get())
        self.raiz.title(self.titulo_janela())
        self._ajusta_largura_indicativo()

    def _ajusta_largura_indicativo(self):
        """Campo do tamanho do texto (a largura do Entry é medida em caracteres "0")."""
        if not hasattr(self, "ent_indicativo"):
            return
        f = self.fonte_indicativo
        texto = self.indicativo.get() or "Indicativo"
        self.ent_indicativo.configure(width=-(-f.measure(texto + "M") // f.measure("0")))

    def _maiusculas_indicativo(self, evento):
        # Fora do trace: alterar a variável dentro do próprio trace dessincroniza o campo.
        atual = evento.widget.get()
        if atual != atual.upper():
            pos = evento.widget.index("insert")
            self.indicativo.set(atual.upper()[:cr.TAM_INDICATIVO])
            evento.widget.icursor(pos)

    def _confirma_indicativo(self, *_):
        self.indicativo.set(cr.INDICATIVO)
        if hasattr(self, "imagem"):
            self.imagem.novo_indicativo(self.cfg.get("indicativo", ""), cr.INDICATIVO)
        self.cfg["indicativo"] = cr.INDICATIVO
        try:
            grava_json(os.path.join(pasta_config(), "config.json"), self.cfg)
        except Exception:
            pass
        self.raiz.focus_set()

    def _aplica_textos_salvos(self):
        salvos = self.cfg.get("textos", {}).get(self.pacote.modelo.chave, {})
        self.pacote.textos.update({int(k): v for k, v in salvos.items()})
        # 2.8.7: sugestão do "Enter" passou de "menu" para "salvo"; troca só se ainda for a antiga.
        for slot, (ingles, sugestao) in self.pacote.modelo.rotulos.items():
            if ingles == "Enter" and self.pacote.textos.get(slot) == "menu":
                self.pacote.textos[slot] = sugestao

    # ---------------------------------------------------------------- fontes
    def _configura_fontes(self, tamanho):
        self.tam_letra = max(9, min(20, tamanho))
        for nome in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkCaptionFont",
                     "TkSmallCaptionFont", "TkIconFont", "TkTooltipFont", "TkFixedFont"):
            try:
                tkfont.nametofont(nome).configure(size=self.tam_letra)
            except tk.TclError:
                pass
        if not hasattr(self, "fonte_destaque"):
            base = tkfont.nametofont("TkDefaultFont").actual()["family"]
            self.fonte_destaque = tkfont.Font(family=base, weight="bold")
            self.fonte_negrito = tkfont.Font(family=base, weight="bold")
        self.fonte_destaque.configure(size=self.tam_letra + 1)
        self.fonte_negrito.configure(size=self.tam_letra)
        if hasattr(self, "lbl_engrenagem"):
            self._desenha_engrenagem()
        tema.aplica(self.raiz, self.fonte_destaque, self.fonte_negrito)
        if hasattr(self, "fonte_titulo"):
            self.fonte_titulo.configure(size=self.tam_letra + 6)
        if hasattr(self, "fonte_indicativo"):
            self.fonte_indicativo.configure(size=self.tam_letra + 1)
            self._ajusta_largura_indicativo()
        if hasattr(self, "lbl_letra"):
            self.lbl_letra.config(text=str(self.tam_letra))

    def largura_texto(self, caracteres):
        return tkfont.nametofont("TkDefaultFont").measure("0") * caracteres + 12

    def muda_letra(self, delta):
        self._configura_fontes(self.tam_letra + delta)
        if hasattr(self, "programacao"):
            from programacao_ui import COLUNAS
            for c, _, w in COLUNAS:
                self.programacao.tv.column(c, width=self.largura_texto(w))
        if hasattr(self, "icom"):
            self.icom.ajusta_colunas()
        if hasattr(self, "dmr"):
            self.dmr.ajusta_colunas()
        self.cfg.pop("colunas", None)          # as larguras guardadas valiam para a letra anterior
        if hasattr(self, "lateral"):
            self.lateral.atualiza()

    def seleciona_modelo(self, chave):
        self.modelo.set(NOMES_RADIO[chave])
        self.troca_modelo()
        return self.modelo_radio == chave

    def _aplica_modelo_radio(self):
        """Abas e tela de programação conforme o rádio escolhido."""
        icom = self.modelo_radio in RADIOS_ICOM
        if icom and hasattr(self, "icom"):
            self.icom.define_modelo(self.modelo_radio)
        so_prog = self.modelo_radio not in vc.MODELOS     # sem vozes nem imagem
        # Abas que não servem para o modelo ficam escondidas
        com_imagem = self.modelo_radio in imagem_ui.ia.PERFIS
        atual = str(self.principal.select())
        if (so_prog and atual == str(self.pg_vozes)) or (not com_imagem and atual == str(self.pg_img)):
            self.principal.select(self.pg_prog)
        self.principal.tab(self.pg_vozes, state="hidden" if so_prog else "normal")
        self.principal.tab(self.pg_img, state="normal" if com_imagem else "hidden")
        if com_imagem and hasattr(self, "imagem"):
            self.imagem.atualiza_modelo(self.modelo_radio)
        if hasattr(self, "cb_porta"):
            usb = self.modelo_radio in RADIOS_DMR
            self.cb_porta.configure(textvariable=self._porta_usb if usb else self.porta,
                                    state="disabled" if usb else "normal")
            self.bt_portas.configure(state="disabled" if usb else "normal")
        if hasattr(self, "fr_dmr"):
            dmr = self.modelo_radio in RADIOS_DMR
            ativo = self.fr_icom if icom else self.fr_dmr if dmr else self.fr_baofeng
            for fr in (self.fr_baofeng, self.fr_icom, self.fr_dmr):
                if fr is not ativo:
                    fr.pack_forget()
            ativo.pack(fill="both", expand=True)
        self._atualiza_lista_radios()
        if self.modelo.get() != NOMES_RADIO[self.modelo_radio]:
            self.modelo.set(NOMES_RADIO[self.modelo_radio])   # seletor sempre mostra o modelo em uso
        if hasattr(self, "status"):
            self.status.config(text=f"{NOMES_RADIO[self.modelo_radio]}: {RECURSOS_RADIO[self.modelo_radio]}")
        self._atualiza_lateral()

    # ------------------------------------------------------------ menu lateral
    def _aba_ativa(self):
        """Tela de programação do rádio escolhido (Baofeng, Icom ou DMR)."""
        if self.modelo_radio in RADIOS_ICOM:
            return self.icom
        return self.dmr if self.modelo_radio in RADIOS_DMR else self.programacao

    def _atualiza_lateral(self):
        """Seções do menu lateral conforme o modelo: as da programação e, se o rádio tiver, vozes e imagem."""
        if not hasattr(self, "lateral") or not hasattr(self, "imagem"):
            return
        nb = self._aba_ativa().nb
        prog = [(("prog", str(t)), nb.tab(t, "text"), ICONES_SECAO.get(nb.tab(t, "text"), "sliders-horizontal"))
                for t in nb.tabs() if nb.tab(t, "state") != "hidden"]
        recursos = []
        if self.principal.tab(self.pg_vozes, "state") != "hidden":
            recursos.append((("vozes", ""), "Vozes", "audio-lines"))
        if self.principal.tab(self.pg_img, "state") != "hidden":
            recursos.append((("imagem", ""), "Imagem de abertura", "image"))
        self.lateral.define([("Programação", prog), ("Recursos", recursos)])
        self._sincroniza_lateral()

    def _escolhe_secao(self, chave):
        tipo, aba = chave
        if tipo == "prog":
            self.principal.select(self.pg_prog)
            self._aba_ativa().nb.select(aba)
        else:
            self.principal.select(self.pg_vozes if tipo == "vozes" else self.pg_img)
        self._sincroniza_lateral()

    def _sincroniza_lateral(self, *_):
        self.raiz.after_idle(tema.atualiza_comandos)
        if not hasattr(self, "lateral") or not hasattr(self, "imagem"):
            return
        atual = str(self.principal.select())
        if atual == str(self.pg_vozes):
            self.lateral.seleciona(("vozes", ""))
        elif atual == str(self.pg_img):
            self.lateral.seleciona(("imagem", ""))
        else:
            self.lateral.seleciona(("prog", str(self._aba_ativa().nb.select())))

    def _menu_recolhido(self, recolhido):
        self.cfg["menu_recolhido"] = bool(recolhido)
        self._salva_cfg()
        self._aplica_recolhido(recolhido)

    def _aplica_recolhido(self, recolhido):
        """Recolhido, a lateral mostra só os ícones: somem o nome da marca e o indicativo."""
        if not hasattr(self, "textos_marca"):
            return
        if recolhido:
            self.textos_marca.pack_forget()
            self.rodape_lateral.pack_forget()
        else:
            self.textos_marca.pack(side="left")
            self.rodape_lateral.pack(side="bottom", fill="x", padx=12, pady=(4, 12), before=self.lateral)

    def nome_radio(self):
        return NOMES_RADIO[self.modelo_radio]

    def _atualiza_lista_radios(self):
        if hasattr(self, "cb_modelo"):
            nomes = [NOMES_RADIO[k] for k in NOMES_RADIO if k in self.meus_radios or k == self.modelo_radio]
            self.cb_modelo["values"] = nomes + [ESCOLHER_RADIOS]

    def meus_radios_janela(self):
        """Janela "Rádios": quais aparecem na lista de seleção e o que o PYProg faz em cada um."""
        j = tk.Toplevel(self.raiz)
        j.title("Rádios")
        j.transient(self.raiz)
        f = ttk.Frame(j, padding=(22, 18, 22, 16))
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="Rádios", font=self.fonte_titulo).pack(anchor="w")
        ttk.Label(f, text="Marque em \"Ativo\" os rádios que você vai programar: só eles aparecem na lista de "
                          "seleção do topo. Clique num modelo para ver os detalhes.", style="Suave.TLabel", wraplength=900,
                  justify="left").pack(anchor="w", pady=(2, 10))
        colunas = [("mostrar", "Ativo", 80), ("modelo", "Modelo", 470), ("prog", "Programação", 120),
                   ("vozes", "Vozes", 70), ("imagem", "Imagem", 85), ("situacao", "Situação", 115)]
        tv = ttk.Treeview(f, columns=[c for c, _, _ in colunas], show="headings", height=len(NOMES_RADIO),
                          selectmode="browse")
        for c, rot, larg in colunas:
            tv.heading(c, text=rot)
            tv.column(c, width=larg, anchor="w" if c == "modelo" else "center", stretch=c == "modelo")
        tv.tag_configure("experimental", foreground=tema.C["aviso"])
        marcados = {k: k in self.meus_radios for k in NOMES_RADIO}

        def linha(k):
            prog, voz, img, _ = TABELA_RADIOS[k]
            nome = NOMES_RADIO[k] if k == "UV5R" else NOMES_MEUS_RADIOS.get(k, NOMES_RADIO[k])
            return ("✓" if marcados[k] else "", nome, prog, voz, img,
                    "testado" if k in TESTADOS else "experimental")
        for k in NOMES_RADIO:
            tv.insert("", "end", iid=k, values=linha(k), tags=() if k in TESTADOS else ("experimental",))
        tv.pack(fill="x")
        detalhe = ttk.Label(f, text="", wraplength=900, justify="left")
        detalhe.pack(anchor="w", fill="x", pady=(10, 0))
        ttk.Label(f, text="Testado: lido e gravado com sucesso num rádio real. Experimental: segue o CHIRP ou o "
                          "programa oficial, mas ainda não foi testado com o PYProg.", style="Suave.TLabel",
                  wraplength=900, justify="left").pack(anchor="w", pady=(10, 0))

        def mostra_detalhe(_=None):
            sel = tv.selection()
            if sel:
                k = sel[0]
                detalhe.config(text=f"{NOMES_RADIO[k]}: {TABELA_RADIOS[k][3]}")

        def clique(ev):
            k = tv.identify_row(ev.y)
            if k and tv.identify_column(ev.x) == "#1":
                marcados[k] = not marcados[k]
                tv.item(k, values=linha(k))

        def espaco(_):
            for k in tv.selection():
                marcados[k] = not marcados[k]
                tv.item(k, values=linha(k))
        tv.bind("<<TreeviewSelect>>", mostra_detalhe)
        tv.bind("<Button-1>", clique, add="+")
        tv.bind("<space>", espaco)
        bt = ttk.Frame(f)
        bt.pack(fill="x", pady=(16, 0))

        def ok():
            escolhidos = [k for k in NOMES_RADIO if marcados[k]]
            if not escolhidos:
                messagebox.showinfo("Rádios", "Marque pelo menos um rádio em \"Ativo\".", parent=j)
                return
            self.meus_radios = escolhidos
            j.destroy()
            if self.modelo_radio not in escolhidos:
                # o rádio em uso saiu da lista: passa para o primeiro marcado
                self.seleciona_modelo(escolhidos[0])
            self._atualiza_lista_radios()
            self._salva_cfg()
        ttk.Button(bt, text="Cancelar", command=j.destroy).pack(side="right")
        ttk.Button(bt, text="OK", command=ok, style="Neutro.TButton").pack(side="right", padx=8)
        j.bind("<Escape>", lambda e: j.destroy())
        tv.selection_set(self.modelo_radio)
        self._centraliza(j)
        j.grab_set()

    def preferencias_janela(self):
        """Janela "Preferências": ajustes gerais que valem para todos os rádios."""
        j = tk.Toplevel(self.raiz)
        j.title("Preferências")
        j.transient(self.raiz)
        j.resizable(False, False)
        f = ttk.Frame(j, padding=(22, 18, 22, 16))
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="Preferências", font=self.fonte_titulo).pack(anchor="w", pady=(0, 6))
        v = {"backup_antes_gravar": tk.BooleanVar(value=bool(self.cfg.get("backup_antes_gravar", False))),
             "controle_faixas": tk.BooleanVar(value=bool(self.cfg.get("controle_faixas", False))),
             "verificar_atualizacoes": tk.BooleanVar(value=bool(self.cfg.get("verificar_atualizacoes", True)))}
        itens = [("Gravação no rádio", [
                    ("backup_antes_gravar", "Fazer backup do rádio antes de gravar",
                     "Lê o rádio e guarda uma cópia na pasta de backups antes de cada gravação. A gravação demora "
                     "mais; sem o backup, desfazer uma gravação errada depende de uma leitura feita antes."),
                    ("controle_faixas", "Controlar as faixas de TX",
                     "Canais que transmitem fora das faixas liberadas aparecem em vermelho e podem ser bloqueados "
                     "(botão \"Bloqueio de TX...\" na programação dos rádios Baofeng).")]),
                 ("Atualizações", [
                    ("verificar_atualizacoes", "Procurar atualizações ao abrir o programa",
                     "Consulta o GitHub sempre que o PYProg é aberto e abre uma janela quando há versão nova.")])]
        for titulo, opcoes in itens:
            ttk.Label(f, text=titulo, font=self.fonte_negrito).pack(anchor="w", pady=(12, 2))
            for chave, rot, exp in opcoes:
                ttk.Checkbutton(f, text=rot, variable=v[chave]).pack(anchor="w", padx=(10, 0), pady=(4, 0))
                ttk.Label(f, text=exp, style="Suave.TLabel", wraplength=520, justify="left").pack(
                    anchor="w", padx=(34, 0))
        bt = ttk.Frame(f)
        bt.pack(fill="x", pady=(18, 0))

        def ok():
            for chave, var in v.items():
                self.cfg[chave] = bool(var.get())
            self._salva_cfg()
            j.destroy()
            self.programacao.aplica_controle()
            self.status.config(text="Preferências salvas.")
        ttk.Button(bt, text="Cancelar", command=j.destroy).pack(side="right")
        ttk.Button(bt, text="OK", command=ok, style="Neutro.TButton").pack(side="right", padx=8)
        j.bind("<Escape>", lambda e: j.destroy())
        self._centraliza(j)
        j.grab_set()

    def _centraliza(self, j):
        j.update_idletasks()
        r = self.raiz
        j.geometry(f"+{r.winfo_rootx() + (r.winfo_width() - j.winfo_reqwidth()) // 2}"
                   f"+{r.winfo_rooty() + max(0, (r.winfo_height() - j.winfo_reqheight()) // 3)}")

    def _aceita_experimental(self, chave):
        """Aviso de modelo experimental ao escolhê-lo, com 'não mostrar de novo'."""
        aceitos = self.cfg.setdefault("experimental_aceito", [])
        if chave not in AVISO_EXPERIMENTAL or chave in aceitos:
            return True
        j = tk.Toplevel(self.raiz)
        j.title("Modelo experimental")
        j.transient(self.raiz)
        j.resizable(False, False)
        f = ttk.Frame(j, padding=18)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text=AVISO_EXPERIMENTAL[chave], wraplength=460, justify="left").pack(anchor="w")
        ttk.Label(f, text="Você aceita o risco?", font=self.fonte_negrito).pack(anchor="w", pady=(14, 8))
        nao_mostrar = tk.BooleanVar(value=False)
        ttk.Checkbutton(f, text=f"Não mostrar novamente para o {NOMES_RADIO[chave]}",
                        variable=nao_mostrar).pack(anchor="w")
        resposta = {"ok": False}
        bts = ttk.Frame(f)
        bts.pack(anchor="w", pady=(16, 0))

        def fecha(ok):
            resposta["ok"] = ok
            j.destroy()
        ttk.Button(bts, text="Sim", command=lambda: fecha(True)).pack(side="left", padx=(0, 8))
        bt_nao = ttk.Button(bts, text="Não", command=lambda: fecha(False))
        bt_nao.pack(side="left")
        j.protocol("WM_DELETE_WINDOW", lambda: fecha(False))
        j.bind("<Escape>", lambda e: fecha(False))
        j.update_idletasks()
        r = self.raiz
        j.geometry(f"+{r.winfo_rootx() + (r.winfo_width() - j.winfo_reqwidth()) // 2}"
                   f"+{r.winfo_rooty() + (r.winfo_height() - j.winfo_reqheight()) // 3}")
        bt_nao.focus_set()
        j.grab_set()
        self.raiz.wait_window(j)
        if resposta["ok"] and nao_mostrar.get():
            aceitos.append(chave)
            self._salva_cfg()
        return resposta["ok"]

    def _desenha_engrenagem(self):
        """A engrenagem é desenhada (o símbolo da fonte muda de cara em cada Windows) e segue o A+/A-."""
        self._img_engrenagem = tema.icone("settings", round((self.tam_letra + 5) * 1.5), tema.C["secundario_texto"])
        self.lbl_engrenagem.configure(image=self._img_engrenagem)

    # ---------------------------------------------------------------- layout
    def _monta_topo(self):
        # Cabeçalho claro e único: nome à esquerda; rádio, porta, indicativo e engrenagem à direita
        fundo, texto, suave = tema.C["cabecalho"], tema.C["texto"], tema.C["suave"]
        # Corpo: menu lateral à esquerda; à direita, uma faixa só com os comandos e os controles da porta
        self.corpo = tk.Frame(self.raiz, bg=tema.C["fundo"])
        self.coluna = tk.Frame(self.corpo, bg=tema.C["lateral"])
        self.area = tk.Frame(self.corpo, bg=fundo)
        cab = tk.Frame(self.area, bg=fundo, padx=18, pady=8)
        cab.pack(fill="x")
        tk.Frame(self.area, bg=tema.C["borda_suave"], height=1).pack(fill="x")
        base = tkfont.nametofont("TkDefaultFont").actual()["family"]
        self.fonte_titulo = tkfont.Font(family=base, size=self.tam_letra + 6, weight="bold")
        # A logo, o nome e o indicativo ficam no menu lateral
        marca = tk.Frame(self.coluna, bg=tema.C["lateral"])
        marca.pack(side="top", fill="x", padx=12, pady=(12, 4))
        try:
            self._icone_cab = tk.PhotoImage(file=os.path.join(vc.pasta_dados(), "icone_40.png"))
            self.lbl_logo = tk.Label(marca, image=self._icone_cab, bg=tema.C["lateral"])
            self.lbl_logo.pack(side="left", padx=(0, 8))
        except tk.TclError:
            pass
        self.textos_marca = tk.Frame(marca, bg=tema.C["lateral"])
        self.textos_marca.pack(side="left")
        tk.Label(self.textos_marca, text=NOME_APP, bg=tema.C["lateral"], fg=texto,
                 font=self.fonte_titulo).pack(anchor="w")
        self.lbl_sub = tk.Label(self.textos_marca, text=f"Versão {vc.VERSAO}", bg=tema.C["lateral"], fg=suave,
                                font="TkDefaultFont")
        self.lbl_sub.pack(anchor="w")
        self.rodape_lateral = tk.Frame(self.coluna, bg=tema.C["lateral"])
        self.rodape_lateral.pack(side="bottom", fill="x", padx=12, pady=(4, 12))

        # Comandos do rádio (Ler, Gravar, Arquivo) ficam à esquerda, na mesma linha
        tema.FAIXA_TOPO = tk.Frame(cab, bg=fundo)
        tema.FAIXA_TOPO.pack(side="left", fill="y")
        dir_ = tk.Frame(cab, bg=fundo)
        dir_.pack(side="right")
        # Engrenagem: meus rádios, tamanho da letra, atualizações, modelos compatíveis e Sobre
        engr = tk.Label(dir_, bg=fundo, cursor="hand2", bd=0)
        self.lbl_engrenagem = engr
        self._desenha_engrenagem()
        menu = tema.MenuDesenhado(self.raiz)
        menu.add_command(label="Rádios...", command=self.meus_radios_janela)
        menu.add_command(label="Preferências...", command=self.preferencias_janela)
        menu.add_separator()
        menu.add_command(label="Aumentar a letra  (A+)", command=lambda: self.muda_letra(1))
        menu.add_command(label="Diminuir a letra  (A-)", command=lambda: self.muda_letra(-1))
        menu.add_separator()
        menu.add_command(label="Verificar atualizações", command=lambda: self.verifica_atualizacao(manual=True))
        menu.add_command(label="Sobre o PYProg", command=self.sobre)
        def abre_menu(_e, menu=menu):
            esconde_dica()
            menu.popup(max(0, engr.winfo_rootx() + engr.winfo_width() - 280),
                       engr.winfo_rooty() + engr.winfo_height() + 4)
            return "break"      # sem isso, o mesmo clique chegava à janela e fechava o menu na hora
        engr.bind("<Button-1>", abre_menu)
        engr.pack(side="right", padx=(6, 0))
        esconde_dica = _dica_ao_parar(engr, "Rádios, preferências, letra, atualizações e Sobre")
        # Indicativo editável (até 16 caracteres), só o texto, sem fundo
        caixa = tk.Frame(self.rodape_lateral, bg=tema.C["lateral"])
        caixa.pack(anchor="w")
        self.indicativo = tk.StringVar(value=cr.INDICATIVO)
        vcmd = (self.raiz.register(lambda p: len(p) <= cr.TAM_INDICATIVO), "%P")
        self.fonte_indicativo = tkfont.Font(family=base, size=self.tam_letra + 1, weight="bold")
        ent = tk.Entry(caixa, textvariable=self.indicativo, width=4, justify="center",
                       font=self.fonte_indicativo, bg=fundo, fg=tema.C["secundario_texto"],
                       insertbackground=tema.C["secundario_texto"],
                       relief="flat", bd=0, highlightthickness=1, highlightbackground=fundo,
                       highlightcolor=tema.C["borda"], selectbackground=tema.C["primario"], selectforeground="#FFFFFF",
                       validate="key", validatecommand=vcmd)
        ent.pack()
        self.indicativo.trace_add("write", self._muda_indicativo)
        ent.bind("<KeyRelease>", self._maiusculas_indicativo)
        ent.bind("<Return>", self._confirma_indicativo)
        ent.bind("<FocusOut>", self._confirma_indicativo)
        ent.configure(cursor="xterm")
        _dica_ao_parar(ent, "Clique para alterar")
        self.ent_indicativo = ent
        # Sem indicativo: exemplo em cinza dentro do campo
        dica = tk.Label(caixa, text="Indicativo", bg=fundo, fg=tema.C["exemplo"], font=self.fonte_indicativo,
                        cursor="xterm")
        dica.bind("<Button-1>", lambda e: ent.focus_set())

        def mostra_dica(*_):
            if self.indicativo.get() or ent.focus_get() is ent:
                dica.place_forget()
            else:
                dica.place(relx=0.5, rely=0.5, anchor="center")
        ent.bind("<FocusIn>", mostra_dica, add="+")
        ent.bind("<FocusOut>", mostra_dica, add="+")
        self.indicativo.trace_add("write", mostra_dica)
        ent.after_idle(mostra_dica)
        self._ajusta_largura_indicativo()
        # Porta e rádio
        atualiza = tk.Button(dir_, image=tema.icone("refresh-cw", tema.tam_icone() + 2, tema.C["secundario_texto"]),
                             bg=fundo, activebackground=tema.C["secundario_h"], relief="flat", bd=0,
                             highlightthickness=1, highlightbackground=fundo, highlightcolor=tema.C["foco"],
                             padx=4, pady=4, cursor="hand2", command=self.atualiza_portas)
        atualiza.pack(side="right", padx=(4, 0))
        self.bt_portas = atualiza
        _dica_ao_parar(atualiza, "Procurar portas COM de novo")
        bt_id = tk.Button(dir_, image=tema.icone("target", tema.tam_icone() + 2, tema.C["secundario_texto"]),
                          bg=fundo, activebackground=tema.C["secundario_h"], relief="flat", bd=0,
                          highlightthickness=1, highlightbackground=fundo, highlightcolor=tema.C["foco"],
                          padx=4, pady=4, cursor="hand2", command=self.identifica_porta)
        bt_id.pack(side="right", padx=(4, 0))
        self.bt_identifica = bt_id
        _dica_ao_parar(bt_id, "Descobrir qual porta COM é o rádio ligado (testa as portas uma por uma)")
        self.porta = tk.StringVar(value=self.cfg.get("porta", ""))
        self.cb_porta = ttk.Combobox(dir_, textvariable=self.porta, width=9, style="Alto.TCombobox")
        self.cb_porta.pack(side="right")
        self._porta_usb = tk.StringVar(value="USB")       # RT3S: a conexão é pelo USB, sem porta COM
        _dica_ao_parar(self.cb_porta, "Porta COM do cabo de programação")
        tk.Label(dir_, text="Porta", bg=fundo, fg=suave).pack(side="right", padx=(16, 6))
        self.nomes_modelo = {n: k for k, n in NOMES_RADIO.items()}
        self.modelo = tk.StringVar(value=NOMES_RADIO[self.modelo_radio])
        cb = ttk.Combobox(dir_, textvariable=self.modelo, values=list(self.nomes_modelo),
                          state="readonly", width=21, style="Alto.TCombobox")
        self.cb_modelo = cb
        cb.pack(side="right")
        cb.bind("<<ComboboxSelected>>", self.troca_modelo)
        tk.Label(dir_, text="Rádio", bg=fundo, fg=suave).pack(side="right", padx=(0, 6))
        self.atualiza_portas()

        # Corpo: menu lateral à esquerda e a área principal à direita. As páginas continuam num
        # Notebook (com as abas escondidas), escolhidas pelo menu lateral.
        self.principal = ttk.Notebook(self.area, style="Semabas.TNotebook")
        self.pg_vozes = ttk.Frame(self.principal)
        self.pg_prog = ttk.Frame(self.principal)
        self.pg_img = ttk.Frame(self.principal)
        self.principal.add(self.pg_prog, text="Programação")
        self.principal.add(self.pg_vozes, text="Vozes")
        self.principal.add(self.pg_img, text="Imagem de abertura")
        ttk.Label(self.pg_vozes, text="Vozes", font=self.fonte_titulo).pack(anchor="w", padx=16, pady=(12, 0))

        # Linha das ações principais: montada aqui, exibida abaixo das configurações de voz.
        linha_voz = ttk.Frame(self.pg_vozes, padding=(12, 12, 12, 2))
        self.bt_gerar = ttk.Button(linha_voz, text="Gerar vozes", command=self.gerar_todas,
                                   style="Neutro.TButton")
        self.bt_gerar.pack(side="left", padx=(0, 8))
        self.botoes_ocupado.append(self.bt_gerar)
        self.bt_enviar = tema.botao(linha_voz, "Enviar vozes ao rádio", self.enviar, "upload", "Gravar.TButton")
        self.bt_enviar.pack(side="left", padx=(0, 10))
        self.botoes_ocupado.append(self.bt_enviar)
        self.mb_backup = ttk.Menubutton(linha_voz, text="Restaurar backup")
        menu = tema.MenuDesenhado(self.raiz)
        menu.add_command(label="Carregar o último envio deste modelo", command=self.carrega_ultimo_envio)
        menu.add_command(label="Abrir um backup de vozes (.vpa)...", command=self.abre_backup)
        menu.add_separator()
        menu.add_command(label="Abrir a pasta de backups", command=self.abre_pasta_backup)
        menu.anexa(self.mb_backup)
        self.mb_backup.pack(side="left")
        ajuda.botao(linha_voz, "backup").pack(side="left", padx=4)
        self.botoes_ocupado.append(self.mb_backup)

        # Linha 2: voz
        voz = ttk.Frame(self.pg_vozes, padding=(12, 10, 12, 0))
        voz.pack(fill="x")
        ttk.Label(voz, text="Voz:").pack(side="left")
        v = self.cfg.get("voz", vc.VOZ_PADRAO)
        todas = list(vc.VOZES) + list(vc.VOZES_INGLES) + list(vc.VOZES_ESPANHOL) + list(vc.VOZES_CHINES)
        self.voz = tk.StringVar(value=v if v in todas else vc.VOZ_PADRAO)
        ttk.Combobox(voz, textvariable=self.voz, values=todas, state="readonly",
                     width=42).pack(side="left", padx=(4, 8))
        ajuda.botao(voz, "voz_parametros").pack(side="left", padx=(0, 8))
        self.velocidade = tk.DoubleVar(value=float(self.cfg.get("velocidade", 110)))
        self.volume = tk.DoubleVar(value=float(self.cfg.get("volume", 100)))
        for rotulo, var, de, ate in (("Velocidade:", self.velocidade, 70, 150),
                                     ("Volume:", self.volume, 50, 200)):
            ttk.Label(voz, text=rotulo).pack(side="left")
            lbl = ttk.Label(voz, width=5, text=f"{var.get():.0f}%")
            ttk.Scale(voz, from_=de, to=ate, variable=var, length=90,
                      command=lambda _v, l=lbl, vv=var: l.config(text=f"{vv.get():.0f}%")).pack(side="left", padx=4)
            lbl.pack(side="left", padx=(0, 12))
        ttk.Label(voz, text="(próximas gerações)",
                  style="Suave.TLabel").pack(side="left")

        teste = ttk.Frame(self.pg_vozes, padding=(12, 8, 12, 0))
        teste.pack(fill="x")
        ttk.Label(teste, text="Testar voz:").pack(side="left")
        self.texto_teste = tk.StringVar(value="canal doze, frequência, potência baixa")
        ttk.Entry(teste, textvariable=self.texto_teste, width=44).pack(side="left", padx=(4, 6))
        b = ttk.Button(teste, text="▶ Ouvir", command=self.testar_voz)
        b.pack(side="left")
        self.botoes_ocupado.append(b)
        ttk.Label(teste, text="(ouve como vai soar no rádio, sem alterar o pacote)",
                  style="Suave.TLabel").pack(side="left", padx=8)

        # Linha 3: pacote
        acoes = ttk.Frame(self.pg_vozes, padding=(12, 8, 12, 0))
        acoes.pack(fill="x")
        for txt, fn in [("Abrir pacote...", self.abrir), ("Fazer backup", self.salvar)]:
            b = ttk.Button(acoes, text=txt, command=fn)
            b.pack(side="left", padx=(0, 6))
            self.botoes_ocupado.append(b)
        self.mb_restaura = ttk.Menubutton(acoes, text="Restaurar vozes")
        menu_r = tema.MenuDesenhado(self.raiz)
        menu_r.add_command(label="Voltar tudo para as vozes do pacote base", command=self.restaurar_tudo)
        menu_r.add_command(label="Usar as vozes em inglês de outro pacote (.vpa)...", command=self.restaurar_ingles)
        menu_r.add_separator()
        menu_r.add_command(label="Indicar o pacote base (arquivo .vpa)...", command=self.indicar_fabrica)
        menu_r.add_nota("Qualquer pacote .vpa do rádio serve. Basta indicá-lo uma vez.")
        menu_r.anexa(self.mb_restaura)
        self.mb_restaura.pack(side="left", padx=(0, 6))
        self.botoes_ocupado.append(self.mb_restaura)
        self.so_alteradas = tk.BooleanVar(value=True)
        ttk.Checkbutton(acoes, text="só falas desatualizadas", variable=self.so_alteradas).pack(side="left", padx=6)
        ajuda.botao(acoes, "geracao").pack(side="left", padx=4)

        audio = ttk.Frame(self.pg_vozes, padding=(12, 6, 12, 0))
        audio.pack(fill="x", before=acoes)
        ttk.Button(audio, text="▶ Conferir números do pacote", command=self.testa_numeros).pack(side="left")
        self.bt_parar_audio = ttk.Button(audio, text="■ Parar áudio (Esc)", command=self.parar_audio)
        self.bt_parar_audio.pack(side="left", padx=8)
        ajuda.botao(audio, "audio").pack(side="left")
        linha_voz.pack(fill="x")
        mem = ttk.Frame(self.pg_vozes, padding=(12, 6, 12, 0))
        mem.pack(fill="x")
        ttk.Label(mem, text="Memória de voz:").pack(side="left")
        self.barra_mem = ttk.Progressbar(mem, length=260, maximum=vc.TAM_PACOTE)
        self.barra_mem.pack(side="left", padx=6)
        self.lbl_mem = ttk.Label(mem)
        self.lbl_mem.pack(side="left")

    def _monta_status(self):
        st = ttk.Frame(self.raiz, padding=(16, 6), style="Rodape.TFrame")
        st.pack(fill="x", side="bottom")
        # O andamento das operações aparece no meio da janela (PainelAndamento); aqui fica só a âncora
        self.barra_ancora = ttk.Frame(st, style="Rodape.TFrame")
        self.barra_ancora.pack(side="right")
        self.andamento = PainelAndamento(self)
        self.status = ttk.Label(st, text="Pronto.", style="Rodape.TLabel")
        self.status.pack(side="left", fill="x", expand=True)

    def _aba_rolavel(self, titulo, nota, acoes=None):
        quadro = ttk.Frame(self.nb)
        self.nb.add(quadro, text=titulo)
        self._ultima_aba = quadro
        ttk.Label(quadro, text=nota, wraplength=1150, style="Suave.TLabel").pack(fill="x", padx=6, pady=4)
        if acoes:
            barra = ttk.Frame(quadro)
            barra.pack(fill="x", padx=6, pady=(0, 4))
            acoes(barra)
        tela = tk.Canvas(quadro, highlightthickness=0, bg=tema.C["fundo"])
        rol = ttk.Scrollbar(quadro, orient="vertical", command=tela.yview)
        interno = ttk.Frame(tela)
        interno.bind("<Configure>", lambda e: tela.configure(scrollregion=tela.bbox("all")))
        tela.create_window((0, 0), window=interno, anchor="nw")
        tela.configure(yscrollcommand=rol.set)
        tela.pack(side="left", fill="both", expand=True)
        rol.pack(side="right", fill="y")

        def roda(ev):
            tela.yview_scroll(int(-ev.delta / 120) if ev.delta else (1 if ev.num == 5 else -1), "units")
        for w in (tela, interno):
            w.bind("<Enter>", lambda e: (tela.bind_all("<MouseWheel>", roda),
                                         tela.bind_all("<Button-4>", roda), tela.bind_all("<Button-5>", roda)))
            w.bind("<Leave>", lambda e: (tela.unbind_all("<MouseWheel>"),
                                         tela.unbind_all("<Button-4>"), tela.unbind_all("<Button-5>")))
        cab = ["Nº", "Original", "Texto a falar (português)", "Situação"]
        for c, t in enumerate(cab):
            ttk.Label(interno, text=t, font=self.fonte_negrito).grid(row=0, column=c, sticky="w", padx=2)
        return interno

    def monta_abas(self):
        for aba in self.nb.tabs():
            w = self.nb.nametowidget(aba)
            self.nb.forget(aba)
            w.destroy()
        self.botoes_ocupado = [b for b in self.botoes_ocupado if b.winfo_exists()]
        self.linhas = []
        m = self.pacote.modelo
        for nome_attr in ("aviso_fabrica", "seletor_avisos"):
            antigo = getattr(self, nome_attr, None)
            if antigo is not None:
                antigo.destroy()
            setattr(self, nome_attr, None)
        if not self.pacote.completo:
            # Faltam avisos sem áudio: gerar todos ou indicar um pacote base resolve
            self.aviso_fabrica = f = tk.Frame(self.pg_vozes, bg=tema.C["aviso_fundo"], padx=12, pady=8)
            f.pack(fill="x", padx=12, pady=(8, 0), before=self.nb)
            self.lbl_faltam = tk.Label(f, bg=tema.C["aviso_fundo"], fg=tema.C["aviso"], justify="left",
                                       wraplength=900, anchor="w", font="TkDefaultFont",
                                       text=self._texto_faltam())
            self.lbl_faltam.pack(side="left", fill="x", expand=True)
            ttk.Button(f, text="Indicar o pacote base...", command=self.indicar_fabrica).pack(
                side="right", padx=(12, 0))
        a1 = self._aba_rolavel(
            f"Avisos em inglês ({len(m.slots_ingles)})",
            "Estes são os avisos usados quando o rádio está com a voz em inglês (menu Voice = English). "
            "Corrija o texto se quiser outra frase, clique em \"Gerar voz\" para ouvir e, no fim, envie ao rádio.")
        a1_aba = self._ultima_aba
        for i, s in enumerate(m.slots_ingles, start=1):
            self.linhas.append(Linha(self, a1, s, m.rotulos[s][0], i))
        if self.pacote.slots_chines:
            def botoes_chines(barra):
                ttk.Button(barra, text="Gerar avisos em chinês", command=self.gerar_chines).pack(side="left")
                self.bt_restaura_chines = ttk.Button(barra, text="Voltar aos avisos chineses do pacote base",
                                                     command=self.restaura_chines)
                self.bt_restaura_chines.pack(side="left", padx=(8, 0))
                if not self.pacote.tem_fabrica:
                    self.bt_restaura_chines.state(["disabled"])
            a2 = self._aba_rolavel(
                f"Avisos em chinês ({len(self.pacote.slots_chines)})",
                "Avisos em chinês, usados quando o rádio está com a voz em chinês. O texto de cada aviso já está em "
                "chinês. Para gerar, escolha uma voz em chinês. Para voltar aos avisos do pacote base, é preciso que "
                "ele esteja indicado.",
                acoes=botoes_chines)
            a2_aba = self._ultima_aba
            for i, s in enumerate(self.pacote.slots_chines, start=1):
                self.linhas.append(Linha(self, a2, s, vc.AVISOS_CHINES[m.chave][s][0], i))
            seletor = tk.Frame(self.pg_vozes, bg=tema.C["fundo"])
            seletor.pack(fill="x", padx=12, pady=(8, 0), before=self.nb)
            self.seletor_avisos = seletor
            ttk.Button(seletor, text=f"Avisos em inglês ({len(m.slots_ingles)})",
                       command=lambda: self.nb.select(a1_aba)).pack(side="left")
            ttk.Button(seletor, text=f"Avisos em chinês ({len(self.pacote.slots_chines)})",
                       command=lambda: self.nb.select(a2_aba)).pack(side="left", padx=(8, 0))
        self.atualiza_memoria()

    # --------------------------------------------------------------- estado
    def atualiza_memoria(self):
        usado = self.pacote.tamanho_usado()
        self.barra_mem["value"] = min(usado, vc.TAM_PACOTE)
        self.lbl_mem.config(text=f"{usado * 100 / vc.TAM_PACOTE:.0f}% ({kb(usado)} KB de {kb(vc.TAM_PACOTE)} KB)")

    def _texto_faltam(self):
        n = len(self.pacote.faltam())
        return (f"Faltam {n} aviso{'s' if n != 1 else ''} sem áudio para o {self.pacote.modelo.nome}. Gere todos os "
                "avisos nas abas de inglês e de chinês, ou indique um pacote .vpa desse rádio, que preenche os que "
                "você não gerar.")

    def atualiza_faixa(self):
        f = getattr(self, "aviso_fabrica", None)
        if f is None:
            return
        if self.pacote.completo:
            f.destroy()
            self.aviso_fabrica = None
        else:
            self.lbl_faltam.config(text=self._texto_faltam())

    def atualiza_tudo(self):
        for l in self.linhas:
            l.atualiza()
        self.atualiza_memoria()
        self.atualiza_faixa()

    def atualiza_portas(self):
        portas = vc.lista_portas()
        self.cb_porta["values"] = [p for p, _ in portas]
        if portas and self.porta.get() not in [p for p, _ in portas]:
            self.porta.set(portas[0][0])

    def identifica_porta(self):
        """Testa cada porta COM com o modelo escolhido e coloca no campo a que respondeu."""
        if self.ocupado:
            return
        portas = vc.lista_portas()
        if not portas:
            messagebox.showwarning("Identificar porta", "Nenhuma porta COM foi encontrada. Confira o cabo e o driver.",
                                   parent=self.raiz)
            return
        nome = NOMES_RADIO.get(self.modelo_radio, self.modelo_radio)
        self.raiz.config(cursor="watch")
        self.raiz.update_idletasks()
        try:
            res = dp.procura(self.modelo_radio, portas,
                             progresso=lambda p: (self.status.config(text=f"Testando a porta {p}..."),
                                                  self.raiz.update_idletasks()))
        except dp.ErroDeteccao as e:
            messagebox.showinfo("Identificar porta", str(e), parent=self.raiz)
            return
        except Exception as e:
            messagebox.showerror("Identificar porta", f"Não foi possível testar as portas: {e}", parent=self.raiz)
            return
        finally:
            self.raiz.config(cursor="")
            self.status.config(text="Pronto.")
        achadas = [p for p, s in res if s == dp.RESPONDEU]
        if not achadas:
            detalhe = "\n".join(f"{p}: {s}" for p, s in res) or "nenhuma porta disponível"
            messagebox.showwarning("Identificar porta",
                                   f"Nenhuma porta respondeu como {nome}.\n\n{detalhe}\n\n"
                                   "Confira o cabo e se o rádio está ligado. Se ele acabou de ser lido ou gravado, "
                                   "desligue e ligue antes de tentar de novo.", parent=self.raiz)
            return
        self.porta.set(achadas[0])
        if len(achadas) > 1:
            messagebox.showinfo("Identificar porta",
                                f"Mais de uma porta respondeu: {', '.join(achadas)}. Escolhi {achadas[0]}. "
                                "Confira qual delas é o cabo do rádio.", parent=self.raiz)
        else:
            self.status.config(text=f"{nome} encontrado na porta {achadas[0]}.")

    def reprodutor_toca(self, adpcm):
        pedido = self.reprodutor.novo_pedido()
        def toca():
            try:
                self.reprodutor.toca(adpcm, pedido)
            except Exception as e:
                self.fila.put(("erro_audio", str(e), None))
        threading.Thread(target=toca, daemon=True).start()

    def parar_audio(self):
        self.reprodutor.para()
        self.status.config(text="Reprodução interrompida.")

    # ------------------------------------------------------ tarefas em fundo
    def executa(self, msg, tarefa, depois=None, cancelavel=False, nota=""):
        """Roda a tarefa em segundo plano com o painel de andamento. 'nota' é uma linha fixa do painel
        (ex.: não desligar o rádio durante a gravação), no lugar de uma janela de aviso antes."""
        if self.ocupado:
            return
        self.ocupado = True
        self._cancelavel = cancelavel
        self._tarefa_id = getattr(self, "_tarefa_id", 0) + 1
        tid = self._tarefa_id
        self.cancelar.clear()
        self._geracao_opts = (self.voz.get(), self.velocidade.get() / 100.0, self.volume.get() / 100.0)
        self._habilita(False)
        self._inicio_tarefa = time.monotonic()
        self._conectado_em = 0.0
        self.andamento.mostra(msg, nota)
        self.status.config(text=msg)

        def corre():
            try:
                tarefa()
                self.fila.put(("fim", None, depois, tid))
            except Exception as e:
                self.fila.put(("fim", e, None, tid))
        threading.Thread(target=corre, daemon=True).start()

    def interrompe(self, perguntar=True):
        """Interrompe a operação em andamento. Devolve True se não há mais nada em andamento."""
        if not self.ocupado:
            return True
        if getattr(self, "_cancelavel", False):
            self.cancelar.set()            # a geração de vozes para sozinha, guardando o que já fez
            self.status.config(text="Parando...")
            return False
        if perguntar and not messagebox.askyesno(
                TITULO, "Interromper a operação em andamento?\n\nUma gravação interrompida deixa a programação "
                        "do rádio incompleta: desligue e ligue o rádio e grave de novo."):
            return False
        self.cancelar.set()
        interrupcao.fecha_portas()
        self._tarefa_id += 1               # o resultado da tarefa interrompida será ignorado
        self.ocupado = False
        self.andamento.esconde()
        self._habilita(True)
        self.atualiza_tudo()
        self.status.config(text="Operação interrompida.")
        return True

    def _habilita(self, ativo):
        if ativo:
            for w, estado, ttk_widget in self._estados_widgets:
                if not w.winfo_exists():
                    continue
                if ttk_widget:
                    w.state(["!" + x for x in w.state()])
                    w.state(estado)
                else:
                    w.configure(state=estado)
            self._estados_widgets = []
            # O botão Interromper fica no painel de andamento e some junto com ele. (Antes ele era
            # retirado do painel aqui e não voltava: da segunda operação em diante não havia botão.)
            return
        self._estados_widgets = []
        def visita(w):
            if w in (self.andamento.bt_interromper, self.bt_parar_audio):
                return
            if isinstance(w, (ttk.Button, ttk.Menubutton, ttk.Entry, ttk.Combobox,
                              ttk.Checkbutton, ttk.Scale, ttk.Treeview)):
                self._estados_widgets.append((w, tuple(w.state()), True))
                w.state(["disabled"])
            elif isinstance(w, (tk.Entry, tk.Button, tk.Checkbutton, tk.Scale)):
                self._estados_widgets.append((w, w.cget("state"), False))
                w.configure(state="disabled")
            for filho in w.winfo_children():
                visita(filho)
        visita(self.raiz)

    def _processa_fila(self):
        try:
            while True:
                try:
                    item = self.fila.get_nowait()
                except queue.Empty:
                    break
                try:
                    self._trata_item(item)
                except Exception as e:
                    # Uma falha ao tratar um resultado (por exemplo, no fim de uma leitura) não pode parar
                    # a fila: sem ela, o painel de andamento nunca mais fecharia.
                    registra_erro(e)
                    self.status.config(text="Erro.")
                    messagebox.showerror(TITULO, f"Erro inesperado: {e}\n\nOs detalhes ficaram em {ARQ_ERROS}, "
                                                 "na pasta de backups.")
            self._vigia_porta()
        finally:
            self.raiz.after(100, self._processa_fila)

    def _trata_item(self, item):
        tipo, a, b = item[:3]
        if tipo == "fim" and len(item) > 3 and item[3] != getattr(self, "_tarefa_id", 0):
            return                       # tarefa interrompida: resultado descartado
        if tipo == "prog":
            if self.ocupado:
                self.andamento.atualiza(a, b)
                self.status.config(text=b)
                if a and a > 0:
                    self._conectado_em = time.monotonic()
        elif tipo == "erro_audio":
            self.status.config(text="Falha na reprodução de áudio.")
            messagebox.showerror(TITULO, a)
        elif tipo == "atualiza":
            self.atualiza_tudo()
        elif tipo == "chama":            # função pedida por outra thread, executada aqui na da janela
            a()
        elif tipo == "fim":
            self.ocupado = False
            self.andamento.esconde()
            self._habilita(True)
            self.atualiza_tudo()
            if a is not None:
                self.status.config(text="Erro.")
                messagebox.showerror(TITULO, str(a))
            else:
                if self.status.cget("text").endswith("..."):
                    self.status.config(text="Pronto.")
                if b:
                    b()

    def _vigia_porta(self):
        """Se a porta COM foi aberta e o rádio não começou a responder em LIMITE_RESPOSTA segundos,
        interrompe e avisa, sem esperar indefinidamente."""
        ab = interrupcao.ultima_abertura
        if not self.ocupado or ab is None or getattr(self, "_cancelavel", False):
            return
        momento, porta = ab
        if momento < getattr(self, "_inicio_tarefa", 0) or self._conectado_em >= momento or time.monotonic() - momento < LIMITE_RESPOSTA:
            return
        interrupcao.ultima_abertura = None
        self.interrompe(perguntar=False)
        self.status.config(text=f"A porta {porta} não respondeu.")
        messagebox.showerror(TITULO, f"O rádio não respondeu na porta {porta}.\n\nConfira:\n"
                                     "- se a porta COM escolhida é a do cabo de programação;\n"
                                     "- se o cabo está bem encaixado no rádio e no computador;\n"
                                     "- se o rádio está ligado e com o modelo certo escolhido.")

    def progresso(self, pct, txt):
        self.fila.put(("prog", pct, txt))

    def testar_voz(self):
        texto = self.texto_teste.get().strip()
        idioma = vc.idioma_voz(self.voz.get())
        if idioma != "pt" and (not texto or texto == "canal doze, frequência, potência baixa"):
            texto = vc.AMOSTRA_INGLES if idioma == "en" else vc.AMOSTRA_ESPANHOL
        if not texto:
            return
        res = {}
        voz, vel, vol = self.voz.get(), self.velocidade.get() / 100.0, self.volume.get() / 100.0

        def tarefa():
            res["a"] = vc.gera_voz_ptbr(texto, voz=voz, velocidade=vel, volume=vol)
        def fim():
            self.reprodutor_toca(res["a"])
            if vc.ULTIMO_AVISO_VOZ:
                self.status.config(text=vc.ULTIMO_AVISO_VOZ)
        self.executa(f"Gerando teste com {self.voz.get()}... (pode levar alguns segundos)", tarefa, depois=fim)

    def gera_slot(self, slot, texto):
        voz, vel, vol = self._geracao_opts
        if slot in self.pacote.modelo.rotulos and vc.idioma_voz(voz) != "pt":   # voz em inglês ou espanhol fala o aviso no idioma dela
            texto = vc.fala_idioma(self.pacote.modelo.rotulos[slot][0], vc.idioma_voz(voz))
        self.pacote.define(slot, vc.gera_voz_ptbr(texto, voz=voz, velocidade=vel, volume=vol),
                           {"tipo": "Gerada", "texto": texto.strip(), "voz": voz,
                            "velocidade": vel, "volume": vol})
        # Sem o pacote base não há como montar o rascunho completo; a voz fica na memória da sessão.
        if self.pacote.completo:
            self.pacote.salva(self.rascunho_vozes())

    # ----------------------------------------------------------------- ações
    def gerar_todas(self):
        m = self.pacote.modelo
        slots = list(m.slots_ingles)
        idioma = vc.idioma_voz(self.voz.get())
        if idioma == "zh":
            messagebox.showwarning(TITULO, "Os avisos em inglês são gerados com uma voz em inglês ou português. "
                                           "Os avisos em chinês são gerados na aba Avisos em chinês.")
            return
        ingles = idioma != "pt"
        if not ingles:
            slots = [s for s in slots if self.pacote.textos.get(s, "").strip()]
        opts = self.voz.get(), self.velocidade.get() / 100.0, self.volume.get() / 100.0
        if self.so_alteradas.get():
            slots = [s for s in slots if self.pacote.precisa_gerar(s, *opts)]
        if not slots:
            messagebox.showinfo(TITULO, "As falas selecionadas já estão atualizadas para esta voz, velocidade e volume.")
            return
        if not messagebox.askyesno(TITULO, f"Gerar {len(slots)} vozes em {dict(en='inglês', es='espanhol', pt='português')[idioma]} "
                                           f"com a voz {self.voz.get()}?\n"
                                           "É preciso estar conectado à internet."):
            return
        falhas = []

        def tarefa():
            for n, s in enumerate(slots, start=1):
                if self.cancelar.is_set():
                    break
                texto = (vc.fala_idioma(m.rotulos[s][0], idioma) if ingles else self.pacote.textos[s].strip())
                self.progresso(int(n * 100 / len(slots)), f"Gerando {n} de {len(slots)}: {texto}")
                try:
                    self.gera_slot(s, texto)
                except vc.ErroPacote:
                    raise
                except Exception as e:
                    falhas.append(f"{s:03d} ({texto}): {e}")
                self.fila.put(("atualiza", None, None))
                time.sleep(0.3)

        def fim():
            if self.cancelar.is_set():
                self.status.config(text="Geração interrompida entre falas. O progresso foi guardado; use gerar novamente para retomar.")
            elif falhas:
                messagebox.showwarning(TITULO, "Algumas vozes não foram geradas:\n\n" + "\n".join(falhas[:15]))
            else:
                self.status.config(text=f"{len(slots)} vozes geradas. Salve o pacote e envie ao rádio.")
        self.executa("Gerando vozes...", tarefa, depois=fim, cancelavel=True)

    def gerar_chines(self):
        if vc.idioma_voz(self.voz.get()) != "zh":
            messagebox.showwarning(TITULO, "Para os avisos em chinês, escolha uma voz em chinês (Xiaoxiao ou Yunxi).")
            return
        slots = self.pacote.slots_chines
        if not messagebox.askyesno(TITULO, f"Gerar os {len(slots)} avisos em chinês com a voz {self.voz.get()}? Eles "
                                           "vão substituir os avisos em chinês quando você enviar ao rádio.\n\n"
                                           "Para voltar aos avisos do pacote base "
                                           "depois, use \"Voltar aos avisos chineses do pacote base\"."):
            return
        falhas = []

        def tarefa():
            for n, s in enumerate(slots, start=1):
                if self.cancelar.is_set():
                    break
                texto = self.pacote.textos[s].strip()
                self.progresso(int(n * 100 / len(slots)), f"Gerando {n} de {len(slots)}: {texto}")
                try:
                    self.gera_slot(s, texto)
                except vc.ErroPacote:
                    raise
                except Exception as e:
                    falhas.append(f"{s:03d} ({texto}): {e}")
                self.fila.put(("atualiza", None, None))
                time.sleep(0.3)

        def fim():
            if self.cancelar.is_set():
                self.status.config(text="Geração interrompida. Use gerar novamente para retomar.")
            elif falhas:
                messagebox.showwarning(TITULO, "Alguns avisos não foram gerados:\n\n" + "\n".join(falhas[:15]))
            else:
                self.status.config(text=f"{len(slots)} avisos em chinês gerados. Envie ao rádio para aplicar.")
        self.executa("Gerando avisos em chinês...", tarefa, depois=fim, cancelavel=True)

    def restaura_chines(self):
        if not self.pacote.tem_fabrica:
            messagebox.showinfo(TITULO, vc.MSG_SEM_FABRICA)
            return
        if messagebox.askyesno(TITULO, "Voltar os avisos em chinês aos do pacote base?\n\n"
                                       "Depois, clique em Enviar vozes ao rádio."):
            self.pacote.restaura_chines()
            self.atualiza_tudo()
            self.status.config(text="Avisos em chinês restaurados. Envie ao rádio para aplicar.")

    def restaurar_tudo(self):
        m = self.pacote.modelo
        if not self.pacote.tem_fabrica:
            messagebox.showinfo(TITULO, vc.MSG_SEM_FABRICA)
            return
        if messagebox.askyesno(TITULO, f"Voltar TODOS os {m.total} áudios para a voz do pacote base?\n\n"
                                       "Será usado o pacote de vozes que você indicou. Não é uma cópia "
                                       "extraída do aparelho.\n\nDepois, clique em Enviar vozes ao rádio."):
            self.pacote.restaura_tudo()
            self.atualiza_tudo()
            self.status.config(text="Vozes do pacote base restauradas. Envie ao rádio para aplicar.")

    def restaurar_ingles(self):
        if not self.pacote.tem_fabrica:
            messagebox.showinfo(TITULO, vc.MSG_SEM_FABRICA)
            return
        caminho = filedialog.askopenfilename(
            title="Pacote com as vozes em inglês", filetypes=[("Pacote de vozes", "*.vpa"), ("Todos", "*.*")])
        if not caminho:
            return
        if not messagebox.askyesno(TITULO, f"Colocar nos avisos em inglês as vozes de \"{os.path.basename(caminho)}\"?\n\n"
                                           "As demais entradas voltam ao pacote base.\n"
                                           "Depois, clique em Enviar vozes ao rádio e deixe o menu "
                                           "Voice do rádio em English."):
            return
        try:
            self.pacote.aplica_pacote_ingles(caminho)
        except Exception as e:
            messagebox.showerror(TITULO, str(e))
            return
        self.atualiza_tudo()
        self.status.config(text=f"Vozes em inglês de {os.path.basename(caminho)} aplicadas. Envie ao rádio para gravar.")

    def indicar_fabrica(self):
        caminho = filedialog.askopenfilename(
            title="Pacote de vozes (.vpa) deste rádio",
            filetypes=[("Pacote de vozes", "*.vpa"), ("Todos", "*.*")])
        if not caminho:
            return
        try:
            chave = vc.instala_fabrica(caminho)
        except Exception as e:
            messagebox.showerror(TITULO, f"Este arquivo não pôde ser usado como pacote base:\n\n{e}")
            return
        nome = vc.MODELOS[chave].nome
        if chave != self.pacote.modelo.chave:
            messagebox.showinfo(TITULO, f"O arquivo é o pacote base do {nome}. Ele foi guardado e será "
                                        f"usado quando esse rádio estiver selecionado.")
            return
        if not self.pacote.tem_fabrica:
            textos = dict(self.pacote.textos)
            completo = self.pacote.completo
            vozes = list(self.pacote.vozes)
            self.pacote = vc.PacoteVozes(chave)
            self.pacote.textos.update(textos)
            if completo:
                self.pacote.vozes = vozes
            self.vozes_salvas = self.pacote.assinatura()
            self.monta_abas()
        messagebox.showinfo(TITULO, f"Pacote base do {nome} guardado. Ele não precisa ser indicado de novo.")

    def abrir(self):
        if not self.confirma_vozes():
            return
        caminho = filedialog.askopenfilename(title="Abrir pacote de vozes",
                                             filetypes=[("Pacote de vozes", "*.vpa"), ("Todos", "*.*")])
        if not caminho:
            return
        try:
            novo = vc.PacoteVozes.abre(caminho)
        except Exception as e:
            messagebox.showerror(TITULO, str(e))
            return
        self._salva_cfg()
        self.pacote = novo
        self.vozes_salvas = novo.assinatura()
        self.modelo.set(novo.modelo.nome)
        self.modelo_radio = novo.modelo.chave
        self.monta_abas()
        self._aplica_modelo_radio()
        self.status.config(text=f"Pacote aberto: {os.path.basename(caminho)}")

    def salvar(self):
        caminho = filedialog.asksaveasfilename(title="Salvar pacote de vozes", defaultextension=".vpa",
                                               initialfile=f"Voz_PTBR_{self.pacote.modelo.chave}.vpa",
                                               filetypes=[("Pacote de vozes", "*.vpa")])
        if not caminho:
            return
        try:
            self.pacote.salva(caminho)
            self.vozes_salvas = self.pacote.assinatura()
            self._remove_rascunho_vozes()
            self.status.config(text=f"Pacote salvo: {os.path.basename(caminho)}")
            return True
        except Exception as e:
            messagebox.showerror(TITULO, str(e))

    def troca_modelo(self, *_):
        if self.modelo.get() == ESCOLHER_RADIOS:
            self.modelo.set(NOMES_RADIO[self.modelo_radio])
            self.raiz.after(50, self.meus_radios_janela)
            return
        chave = self.nomes_modelo[self.modelo.get()]
        if chave == self.modelo_radio:
            return
        escolhido = self.modelo.get()
        self.modelo.set(NOMES_RADIO[self.modelo_radio])   # o campo só mostra o modelo novo depois do "Sim"
        if self.ocupado or not self._aceita_experimental(chave):
            return
        self.modelo.set(escolhido)
        if chave in vc.MODELOS and chave != self.pacote.modelo.chave:
            if not self.confirma_vozes():
                self.modelo.set(NOMES_RADIO[self.modelo_radio])
                return
            self._salva_cfg()
            self.pacote = vc.PacoteVozes(chave)
            self._aplica_textos_salvos()
            self.vozes_salvas = self.pacote.assinatura()
            self.monta_abas()
        self.modelo_radio = chave
        self._aplica_modelo_radio()
        self._salva_cfg()

    # --------------------------------------------------------------- backups
    def pasta_backup(self):
        p = os.path.join(pasta_config(), "Backups")
        os.makedirs(p, exist_ok=True)
        return p

    def arquivo_ultimo_envio(self, chave=None):
        return os.path.join(self.pasta_backup(), f"Ultimo_envio_{chave or self.pacote.modelo.chave}.vpa")

    def _carrega_pacote(self, caminho, descricao):
        if not self.confirma_vozes():
            return
        try:
            novo = vc.PacoteVozes.abre(caminho)
        except Exception as e:
            messagebox.showerror(TITULO, str(e))
            return
        self._salva_cfg()
        self.pacote = novo
        self.vozes_salvas = novo.assinatura()
        self.modelo.set(novo.modelo.nome)
        self.modelo_radio = novo.modelo.chave
        self.monta_abas()
        self._aplica_modelo_radio()
        self.principal.select(self.pg_vozes)
        self.status.config(text=f"{descricao}: {os.path.basename(caminho)}. Para gravá-lo, clique em Enviar vozes ao rádio.")

    def carrega_ultimo_envio(self):
        arq = self.arquivo_ultimo_envio()
        if not os.path.exists(arq):
            messagebox.showinfo(TITULO, "Ainda não há envio registrado para este modelo.\n\n"
                                        "Para enviar um pacote completo, use Restaurar vozes > Voltar tudo para "
                                        "as vozes do pacote base e envie.")
            return
        self._carrega_pacote(arq, "Último envio carregado")

    def abre_backup(self):
        caminho = filedialog.askopenfilename(title="Abrir backup", initialdir=self.pasta_backup(),
                                             filetypes=[("Pacote de vozes", "*.vpa"), ("Todos", "*.*")])
        if caminho:
            self._carrega_pacote(caminho, "Backup carregado")

    def abre_pasta_backup(self):
        p = self.pasta_backup()
        if sys.platform == "win32":
            os.startfile(p)
        else:
            messagebox.showinfo(TITULO, p)

    def sobre(self):
        licencas.janela_sobre(self, NOME_APP, vc.VERSAO)

    # ------------------------------------------------------------ atualização
    def _verifica_atualizacao_automatica(self):
        if self.cfg.get("verificar_atualizacoes", True):
            self.verifica_atualizacao(manual=False)

    def verifica_atualizacao(self, manual=False):
        atualizacao.verifica(self, manual)

    def fecha_para_atualizar(self):
        return self.fechar()

    # ----------------------------------------------------------------- envio
    def enviar(self):
        if not self.pacote.completo:
            faltam = self.pacote.faltam()
            messagebox.showinfo(TITULO, f"Faltam {len(faltam)} avisos sem áudio. Gere todos os avisos nas abas de "
                                        "inglês e de chinês, ou indique um pacote base de vozes.")
            return
        porta = self.porta.get().strip()
        if not porta:
            messagebox.showerror(TITULO, "Escolha a porta COM do cabo de programação.")
            return
        trocados = [s for s in self.pacote.slots_chines if not self.pacote.eh_fabrica(s)]
        if not self.pacote.tem_fabrica:
            extra = ("\n\nOs avisos em chinês serão trocados pelos avisos gerados. Sem pacote base, eles "
                     "não poderão ser restaurados depois.") if trocados else ""
        else:
            extra = (f"\n\nOs {len(trocados)} avisos em chinês serão trocados pelos avisos gerados. Para voltar "
                     "aos do pacote base depois, use \"Voltar aos avisos chineses do pacote base\"." if trocados else "")
        if not messagebox.askyesno(
                "Enviar vozes ao rádio", f"Enviar as vozes ao {self.pacote.modelo.nome}? Elas substituem as que "
                                         "estão no rádio." + extra):
            return
        pacote = self.pacote.copia()
        resultado = {}

        def tarefa():
            registro = RegistroEnvio(self.pasta_backup(), "Vozes", pacote.modelo.chave, porta, ".vpa", pacote.salva)
            resultado["bkp"] = registro.arquivo
            resultado["aviso"] = registro.executa(lambda: vc.envia_ao_radio(porta, pacote, progresso=self.progresso))
            try:
                pacote.salva(self.arquivo_ultimo_envio(pacote.modelo.chave))
            except Exception as e:
                resultado["aviso"] += f" Não foi possível atualizar o atalho do último envio: {e}"

        def fim():
            self.status.config(text=f"Vozes enviadas ao rádio. Cópia do pacote: "
                                    f"{os.path.basename(resultado['bkp'])}. {resultado.get('aviso', '')}".strip())
        self.executa("Enviando as vozes ao rádio...", tarefa, depois=fim, nota=tema.NOTA_GRAVACAO)


    def pasta_rascunhos(self):
        p = os.path.join(pasta_config(), "Recuperacao")
        os.makedirs(p, exist_ok=True)
        return p

    def rascunho_vozes(self):
        return os.path.join(self.pasta_rascunhos(), f"Rascunho_vozes_{self.pacote.modelo.chave}.vpa")

    def _remove_rascunho_vozes(self):
        self._snapshot_rascunho = None
        try:
            os.unlink(self.rascunho_vozes())
        except FileNotFoundError:
            pass

    def confirma_vozes(self):
        if self.pacote.assinatura() == self.vozes_salvas:
            return True
        decisao = messagebox.askyesnocancel(TITULO, "Há alterações de vozes ou textos não salvas. Salvar antes de continuar?")
        if decisao is None:
            return False
        if decisao:
            return bool(self.salvar())
        self._remove_rascunho_vozes()
        return True

    def _autosave(self):
        if not self.ocupado:
            try:
                sig = self.pacote.assinatura()
                dirty = sig != self.vozes_salvas
                self.raiz.title(self.titulo_janela() + ("  * vozes não salvas" if dirty else ""))
                if dirty and sig != self._snapshot_rascunho and self.pacote.completo:
                    self.pacote.salva(self.rascunho_vozes())
                    self._snapshot_rascunho = sig
                p = self.programacao
                self._atualiza_lateral()
                self._salva_rascunho("icom", self.icom.modificado and self.icom.radio is not None,
                                     lambda: icom_ui.ic.imagem(self.icom.radio), self.icom.salva_rascunho)
                self._salva_rascunho("dmr", self.dmr.modificado and self.dmr.cp is not None,
                                     lambda: self.dmr.cp.imagem(), self.dmr.salva_rascunho)
                self._salva_rascunho("baofeng", bool(p.prog) and p.modificado,
                                     lambda: (p.chave, p.prog.imagem(), json.dumps(p.meta_extra(), sort_keys=True)),
                                     lambda: cr.salva_img(
                                         os.path.join(self.pasta_rascunhos(), f"Rascunho_programacao_{p.chave}.img"),
                                         p.chave, p.prog.imagem(), extra=p.meta_extra()))
            except Exception as e:
                self.status.config(text=f"Não foi possível salvar a recuperação automática: {e}")
        self.raiz.after(2000, self._autosave)

    def _salva_rascunho(self, nome, modificado, conteudo, salva):
        """Grava o rascunho só quando o conteúdo mudou desde a última gravação (antes, o arquivo era
        regravado a cada 2 segundos enquanto houvesse alteração não salva)."""
        if not modificado:
            self._rascunhos.pop(nome, None)
            return
        atual = conteudo()
        if self._rascunhos.get(nome) != atual:
            salva()
            self._rascunhos[nome] = atual

    def recupera_rascunhos(self):
        caminho = self.rascunho_vozes()
        if os.path.exists(caminho):
            if messagebox.askyesno(TITULO, "Foi encontrado um rascunho de vozes. Recuperar o trabalho?"):
                try:
                    self.pacote = vc.PacoteVozes.abre(caminho)
                    self.monta_abas()
                except Exception as e:
                    messagebox.showerror(TITULO, f"Falha ao recuperar vozes: {e}")
            else:
                self._remove_rascunho_vozes()
        if self.modelo_radio in RADIOS_DMR:
            caminho = self.dmr.arquivo_rascunho()
            if os.path.exists(caminho):
                if messagebox.askyesno(TITULO, "Foi encontrado um rascunho do arquivo .rdt. Recuperar?"):
                    try:
                        import dmr380
                        self.dmr.carrega(dmr380.Codeplug.abre(caminho), None, "Rascunho recuperado")
                        self.dmr.salvo_estado = None
                        self.dmr.modificado = True
                        self.dmr._atualiza_origem()
                    except Exception as e:
                        messagebox.showerror(TITULO, f"Falha ao recuperar: {e}")
                else:
                    os.unlink(caminho)
            return
        if self.modelo_radio in RADIOS_ICOM:
            caminho = self.icom.arquivo_rascunho()
            if os.path.exists(caminho):
                if messagebox.askyesno(TITULO, f"Foi encontrado um rascunho de programação do "
                                               f"{icom_ui.ic.NOME}. Recuperar?"):
                    try:
                        self.icom.carrega(icom_ui.ic.abre_arquivo(caminho), "Rascunho recuperado")
                        self.icom.salvo_estado = None
                        self.icom.modificado = True
                        self.icom._atualiza_origem()
                    except Exception as e:
                        messagebox.showerror(TITULO, f"Falha ao recuperar programação: {e}")
                else:
                    os.unlink(caminho)
            return
        caminho = os.path.join(self.pasta_rascunhos(), f"Rascunho_programacao_{self.modelo_radio}.img")
        if os.path.exists(caminho):
            if messagebox.askyesno(TITULO, "Foi encontrado um rascunho de programação. Recuperar?"):
                try:
                    chave, dados, meta = cr.abre_img(caminho)
                    self.programacao.carrega(dados, chave, "Rascunho recuperado", meta)
                    self.programacao.salvo_estado = None
                    self.programacao.modificado = True
                    self.programacao._atualiza_origem()
                except Exception as e:
                    messagebox.showerror(TITULO, f"Falha ao recuperar programação: {e}")
            else:
                os.unlink(caminho)

    def testa_numeros(self):
        if self.ocupado:
            return
        por_nome = {en: s for s, (en, pt) in self.pacote.modelo.rotulos.items()}
        # Digits, special teens and tens come from different positions in the radio.
        ordem = vc.NUMEROS_EN
        pcm = []
        for nome in ordem:
            if nome in por_nome:
                pcm.extend(vc.adpcm_decodifica(self.pacote.vozes[por_nome[nome]]))
                pcm.extend([0] * 1600)
        from array import array
        self.reprodutor_toca(vc.adpcm_codifica(array("h", pcm)))
        self.status.config(text="Conferindo números do pacote: 0 a 19, dezenas e cem. Não há gravação no rádio.")

    def fechar(self):
        """Fecha a janela depois de confirmar o que não foi salvo. Retorna True se fechou."""
        if self.ocupado:
            if not messagebox.askyesno(TITULO, "Há uma operação em andamento. Interromper e fechar?\n\nSe o "
                                               "PYProg estiver gravando no rádio, a programação pode ficar "
                                               "incompleta."):
                return False
            if getattr(self, "_cancelavel", False):
                self.cancelar.set()
                self._tarefa_id += 1
                self.ocupado = False
            elif not self.interrompe(perguntar=False):
                return False
        if not self.confirma_vozes():
            return False
        if self.programacao.modificado:
            decisao = messagebox.askyesnocancel(TITULO, "Salvar a programação alterada antes de fechar?")
            if decisao is None:
                return False
            if decisao:
                self.programacao.salvar()
                if self.programacao.modificado:
                    return False
            self.programacao._remove_rascunho()
        if self.dmr.modificado:
            decisao = messagebox.askyesnocancel(TITULO, "Salvar as mudanças no arquivo .rdt antes de fechar?")
            if decisao is None:
                return False
            if decisao and not self.dmr.salvar():
                return False
            self.dmr.remove_rascunho()
        if self.icom.modificado:
            decisao = messagebox.askyesnocancel(TITULO, f"Salvar a programação do {icom_ui.ic.NOME} antes de fechar?")
            if decisao is None:
                return False
            if decisao and not self.icom.salvar():
                return False
            self.icom.remove_rascunho()
        self._salva_cfg()
        self.reprodutor.para()
        self.raiz.destroy()
        return True


def _aplica_icone(raiz):
    pasta = vc.pasta_dados()
    if sys.platform == "win32":
        try:  # faz a barra de tarefas usar o ícone do programa, e não o do Python
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PYProg.PYProg")
        except Exception:
            pass
        try:
            raiz.iconbitmap(default=os.path.join(pasta, "icone.ico"))
        except tk.TclError:
            pass
    try:
        # uma versão por tamanho, reduzida com qualidade: sem isso o Tk reduz a de 256 px e a barra de tarefas fica borrada
        from PIL import Image
        original = Image.open(os.path.join(pasta, "icone.png")).convert("RGBA")
        raiz._icones = [tema._foto(original.resize((n, n), Image.LANCZOS)) for n in (16, 32, 48, 256)]
        raiz.iconphoto(True, *raiz._icones)
    except Exception:
        pass


_MUTEX = None


LIMITE_RESPOSTA = 15      # segundos para o rádio começar a responder depois de abrir a porta


class PainelAndamento:
    """Janela pequena no meio da tela com o andamento da operação e o botão Interromper."""

    def __init__(self, app):
        self.app = app
        self.j = None
        self.barra = None
        self._cria()

    def _cria(self):
        raiz = self.app.raiz
        j = tk.Toplevel(raiz)
        j.withdraw()
        j.title(TITULO)
        j.transient(raiz)
        j.resizable(False, False)
        j.protocol("WM_DELETE_WINDOW", lambda: self.app.interrompe())
        borda = tk.Frame(j, bg=tema.C["borda"], padx=1, pady=1)
        borda.pack(fill="both", expand=True)
        corpo = ttk.Frame(borda, padding=(24, 20, 24, 18))
        corpo.pack(fill="both", expand=True)
        self.lbl = ttk.Label(corpo, text="", wraplength=380, justify="left")
        self.lbl.pack(anchor="w")
        self.barra = ttk.Progressbar(corpo, length=380, maximum=100)
        self.barra.pack(fill="x", pady=(12, 4))
        self.lbl_pct = ttk.Label(corpo, text="", style="Suave.TLabel")
        self.lbl_pct.pack(anchor="e")
        self.lbl_nota = ttk.Label(corpo, text="", wraplength=380, justify="left", font=self.app.fonte_negrito)
        self.bt_interromper = ttk.Button(corpo, text="Interromper", command=self.app.interrompe)
        self.bt_interromper.pack(anchor="e", pady=(10, 0))
        self.j = j

    def mostra(self, msg, nota=""):
        if self.j is None or not self.j.winfo_exists():
            self._cria()
        self.lbl.config(text=msg)
        self.lbl_nota.config(text=nota)
        if nota:
            self.lbl_nota.pack(anchor="w", pady=(6, 0), before=self.bt_interromper)
        else:
            self.lbl_nota.pack_forget()
        self.barra.config(mode="indeterminate", value=0)
        self.barra.start(12)
        self.lbl_pct.config(text="")
        self.bt_interromper.state(["!disabled"])
        raiz = self.app.raiz
        raiz.update_idletasks()
        self.j.update_idletasks()
        w, h = self.j.winfo_reqwidth(), self.j.winfo_reqheight()
        x = raiz.winfo_rootx() + (raiz.winfo_width() - w) // 2
        y = raiz.winfo_rooty() + (raiz.winfo_height() - h) // 2
        self.j.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        self.j.deiconify()
        self.j.lift()

    def atualiza(self, pct, txt):
        if self.j is None:
            return
        if txt:
            self.lbl.config(text=txt)
        if pct is not None and pct > 0:
            if str(self.barra.cget("mode")) != "determinate":
                self.barra.stop()
                self.barra.config(mode="determinate")
            self.barra["value"] = pct
            self.lbl_pct.config(text=f"{int(pct)}%")

    def esconde(self):
        if self.j is not None and self.j.winfo_exists():
            self.barra.stop()
            self.barra.config(mode="determinate", value=0)
            self.j.withdraw()


def main():
    global _MUTEX
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PYProg.PYProg")
            # sinal para o instalador saber que o programa está aberto (some quando o programa fecha)
            _MUTEX = ctypes.windll.kernel32.CreateMutexW(None, False, "PYProgAberto")
        except Exception:
            pass
    raiz = tk.Tk()
    _aplica_icone(raiz)
    try:
        ttk.Style(raiz).theme_use("clam")
    except tk.TclError:
        pass
    app = App(raiz)

    def erro_na_janela(tipo, valor, tb):
        # Sem console (pythonw), um erro num botão sumia sem deixar rastro
        registra_erro(valor.with_traceback(tb))
        try:
            app.status.config(text=f"Erro inesperado: {valor} (detalhes em {ARQ_ERROS}, na pasta de backups).")
        except tk.TclError:
            pass
    raiz.report_callback_exception = erro_na_janela
    if sys.platform == "win32":      # garante a janela aberta e à frente, mesmo se o Windows pedir minimizada
        def _mostra():
            try:
                if raiz.state() == "iconic":
                    raiz.state("normal")
                raiz.deiconify()
                raiz.lift()
                raiz.focus_force()
            except tk.TclError:
                pass
        raiz.after(300, _mostra)
    raiz.mainloop()


if __name__ == "__main__":
    main()

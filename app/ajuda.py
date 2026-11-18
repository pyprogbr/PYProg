"""Ajuda contextual em balões não modais, exibidos ao passar o mouse."""
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

import tema

TEXTOS = {
    "modelo": ("Modelos compatíveis", "UV-17 Pro GPS: programação, vozes e imagem de abertura.\n"
               "UV-17 Pro / R / L: programação e vozes.\n"
               "UV-17R Plus, UV-21 Pro e UV-21 Pro GPS: programação.\n"
               "UV-5R: programação. Vale também para UV-5RA, UV-5RE, UV-5R Plus, UV-5X, "
               "Retevis RT5R, RT5RV e RT5, Rugged RH5R, Radioddity UV-5R EX e Ansoko A-5R.\n\n"
               "Não use a opção UV-5R para BF-F8HP, UV-82, UV-5X3 ou UV-6.\n\n"
               "Icom IC-2730A: canais, bancos e ajustes, com arquivos .icf do programa da Icom (CS-2730).\n\n"
               "Retevis RT3S GPS (TYT MD-UV380/UV390): canais, zonas, contatos e "
               "ajustes; também abre e salva os arquivos .rdt.\n\n"
               "Escolha quais aparecem na lista em Rádios..., no menu da engrenagem, ou em Escolher rádios..., no fim da própria lista."),
    "porta": ("Porta do cabo", "Escolha a porta COM atribuída ao cabo de programação no Windows. Atualizar refaz a lista. Se houver dúvida, desconecte o cabo, atualize a lista, conecte e atualize novamente. A porta nova é a do cabo. Feche outros programas que possam estar usando essa porta."),
    "voz_parametros": ("Voz, velocidade e volume", "Há vozes em português, inglês e espanhol; com voz em inglês ou espanhol, os avisos são gerados nesse idioma. A velocidade altera o ritmo e o volume altera o nível do áudio convertido. Esses controles valem para as próximas gerações/importações; não modificam automaticamente os áudios já presentes no pacote. Gere novamente as falas desejadas para aplicar a mudança. O volume do alto-falante continua sendo ajustado no próprio rádio."),
    "geracao": ("Geração e retomada", "A geração atua apenas nas posições identificadas. As entradas adicionais do pacote são preservadas, sem edição. Só falas desatualizadas compara texto, voz, velocidade e volume com a origem da gravação. As que já correspondem são preservadas. Interromper (no rodapé) termina a fala em processamento e para antes da próxima. Gere novamente para retomar. O cache evita repetir consultas idênticas ao serviço. Parar áudio e Interromper são controles diferentes."),
    "backup": ("Arquivos, recuperação e backups", "Fazer backup salva em arquivo a programação ou o pacote aberto no editor. Para guardar o estado atual do rádio, use Ler rádio antes de fazer o backup da programação. Restaurar backup carrega o arquivo no editor; para aplicar ao aparelho, use Gravar no rádio. O .img guarda a programação: canais, zonas e ajustes. O .vpa guarda um pacote de áudios e seus textos. O .bmp guarda uma imagem de abertura. Antes de enviar, o programa salva uma cópia do material preparado e um registro .envio.json. Vozes e imagem não são extraídas do rádio por esta versão. Último envio é organizado por modelo, não identifica qual aparelho está conectado. Rascunhos de trabalhos não salvos podem ser recuperados ao reabrir o programa."),
    "audio": ("Conferir e parar o áudio", "Conferir números reproduz os áudios numéricos existentes no pacote, sem gerar novas vozes e sem enviar dados ao rádio. A sequência permite comparar unidades, números de 11 a 19 e dezenas. Use Parar áudio ou a tecla Esc para interromper a prévia. Isso também interrompe a audição de um item individual."),
    "tx_radioamador": ("Bloquear e liberar TX por faixa", "As ações em lote usam as faixas de referência brasileiras dentro das frequências tratadas por este programa: 144 a 148 MHz, 220 a 225 MHz e 430 a 440 MHz (radioamador), mais 462 a 467 MHz (FRS), com as bordas incluídas. A frequência examinada é a de TRANSMISSÃO (TX), já considerando duplex e offset; não apenas a de recepção.\n\nBloquear faixas atua em todos os canais ocupados das dez zonas e coloca Sem TX nos que transmitiriam fora dessas faixas, inclusive antigas exceções. Os demais canais permanecem como estão. Liberar faixas atua apenas nos canais bloqueados cujo TX a restaurar está nessas faixas e é aceito pelo mapa de frequências do programa. Não libera a faixa de aviação. Se não houver TX anterior guardado, o desbloqueio usa simplex (TX igual ao RX).\n\nOs botões de selecionados e o botão direito na lista de canais (Bloquear TX / Liberar TX) permitem controle individual. Nenhuma dessas edições é enviada imediatamente: use Gravar no rádio para aplicar. Desfazer reverte a ação em lote. As faixas personalizadas da janela Bloqueio de TX continuam independentes dessas ações de radioamador. O suporte real de cada faixa depende do hardware e firmware do aparelho."),
    "nome": ("Nome do canal", "Identificação mostrada na lista e, conforme a configuração do visor, no rádio. Este perfil aceita até 12 caracteres sem acentos. Alterar o nome não altera a frequência."),
    "rx": ("Frequência de recepção", "RX é a frequência que o rádio escuta. Digite em MHz, com ponto ou vírgula, por exemplo 145,500. O TX pode ser igual, deslocado por offset ou separado, conforme Duplex."),
    "duplex": ("Duplex e transmissão", "Simplex: TX igual ao RX. + e -: o TX é RX mais ou menos o deslocamento informado em Offset. TX separado: o campo Offset/TX passa a conter a frequência completa de transmissão. Sem TX: o canal fica apenas para recepção. O botão RX = TX ao lado dos tons copia o TOM, não a frequência."),
    "offset": ("Offset ou TX separado", "Com duplex + ou -, informe o deslocamento em MHz (por exemplo 0,6). Com TX separado, informe a frequência completa de TX em MHz. Com simplex, o campo não é utilizado. O bloqueio por faixa considera o resultado final do TX."),
    "tomtx": ("Tom de transmissão", "CTCSS transmite um tom contínuo de baixa frequência; DCS transmite um código. São usados para abrir o silenciador de equipamentos configurados para esse tom/código. DxxxN e DxxxI indicam polaridades normal e invertida. Desligado transmite sem esse sinal. O tom não torna a conversa privada."),
    "tomrx": ("Tom de recepção", "Faz o áudio abrir apenas quando o sinal recebido tem o CTCSS ou DCS selecionado. Se houver sinal mas não áudio, um tom RX diferente pode ser a causa. Desligado não exige tom. RX = TX copia o tom configurado para transmissão."),
    "pot": ("Potência", "Seleciona a potência de transmissão do canal entre os níveis oferecidos pelo perfil. A potência efetiva depende do aparelho, da bateria e da faixa. Não aumenta o volume de recepção."),
    "larg": ("Largura de banda", "Larga (FM) e Estreita (NFM) selecionam a largura/desvio de FM do canal. Use a configuração compatível com o sistema com que se comunica. Na faixa de aviação, a recepção AM é determinada automaticamente pela frequência neste perfil."),
    "pttid": ("PTT-ID", "Determina quando o identificador configurado é transmitido: BOT no início do PTT, EOT no final, Ambos ou Desligado. A edição da lista completa de códigos de identificação não está disponível neste programa."),
    "scode": ("S-Code / DTMF", "Escolhe o grupo de sinalização DTMF associado ao canal. Este campo seleciona um grupo existente; não edita a sequência de dígitos desse grupo. Preserve o valor se não usar sinalização."),
    "varredura": ("Incluir na varredura", "Define se o canal participa da procura automática por sinais quando a varredura de canais está ativa. O canal continua acessível manualmente se ficar fora da varredura."),
    "bcl": ("Bloqueio de canal ocupado", "BCL pode impedir a transmissão quando o rádio detecta o canal ocupado. É diferente de Sem TX: Sem TX bloqueia a transmissão permanentemente naquele canal até que seja liberada."),
    "squelch": ("Squelch / silenciador", "Define o limiar de sinal para abrir o áudio de recepção. Níveis altos reduzem ruído, mas podem ocultar sinais fracos. Desligado mantém o áudio aberto."),
    "tot": ("Tempo limite de transmissão", "Limita a duração de uma transmissão contínua pelo PTT. Ao atingir o tempo configurado, o rádio interrompe a transmissão segundo o comportamento do firmware. Desligado remove esse limite de tempo."),
    "totalarm": ("Aviso antes do TOT", "Define com quantos segundos de antecedência o rádio avisa que o tempo limite de transmissão está perto do fim. É útil quando o TOT está habilitado."),
    "savemode": ("Economia de bateria", "Permite ao rádio alternar períodos de atividade e repouso na recepção para poupar bateria. Pode afetar o tempo de abertura de áudio; o comportamento é determinado pelo firmware."),
    "dualstandby": ("Dupla escuta", "Alterna a monitoração das linhas A e B. Não representa dois receptores totalmente independentes nem permite ouvir duas conversas ao mesmo tempo."),
    "chaworkmode": ("Modo da linha A", "Escolhe se a linha A trabalha com frequência digitada (VFO) ou canais de memória. Os botões de bloquear canais atuam nas memórias e não modificam as limitações do VFO."),
    "chbworkmode": ("Modo da linha B", "Escolhe se a linha B trabalha com frequência digitada (VFO) ou canais de memória. Os botões de bloquear canais atuam nas memórias e não modificam as limitações do VFO."),
    "chadistype": ("Exibição do canal A", "Escolhe o que aparece na linha A ao usar memórias: nome, frequência ou número do canal. A programação da frequência permanece a mesma."),
    "chbdistype": ("Exibição do canal B", "Escolhe o que aparece na linha B ao usar memórias: nome, frequência ou número do canal. A programação da frequência permanece a mesma."),
    "powerondistype": ("Tela ao ligar", "Logotipo faz o rádio apresentar a imagem de abertura. Tensão da bateria apresenta a leitura de tensão. Enviar uma imagem não ativa automaticamente a opção Logotipo; grave também a configuração desejada."),
    "backlight": ("Luz de fundo", "Determina por quanto tempo a iluminação permanece acesa após uma operação, ou se fica sempre acesa. Mais tempo de iluminação aumenta o consumo de bateria."),
    "menuquittime": ("Saída automática do menu", "Tempo sem operação após o qual o rádio sai do menu. Não é o tempo de iluminação nem a duração da imagem de abertura."),
    "voicesw": ("Avisos de voz", "Liga ou desliga as mensagens faladas do rádio. Gerar/enviar um pacote não altera automaticamente esse ajuste."),
    "voice": ("Idioma e banco de voz", "Inglês seleciona o banco cujas falas são substituídas pelas vozes enviadas pelo PYProg. Portanto, depois de enviar as vozes, mantenha este ajuste em Inglês (vozes editáveis). Chinês seleciona o outro banco. O nome dessa opção no firmware não é renomeado pelo pacote."),
    "beep": ("Retorno sonoro das teclas", "Escolhe bipe, voz, ambos ou desligado, conforme os valores reconhecidos pelo perfil. A implementação e as opções efetivas podem variar entre firmwares; preserve valores desconhecidos apresentados como Valor atual do rádio."),
    "roger": ("Bipe de fim de transmissão", "Emite o sinal de encerramento de transmissão (Roger) conforme o firmware. É diferente dos bipes locais ao pressionar teclas."),
    "tailclear": ("Eliminação de cauda", "Tenta reduzir o ruído ouvido ao final de uma transmissão. Depende de compatibilidade com o equipamento da outra ponta; não melhora a intensidade do sinal."),
    "sidetone": ("Tom lateral", "Controla o retorno sonoro local dos tons de teclado/DTMF e/ou identificação ANI. Permite ouvir a sinalização que está sendo operada."),
    "tone": ("Tom piloto", "Seleciona a frequência do tom de chamada/abertura oferecido pelo rádio, como 1750 Hz. Não é CTCSS contínuo e não substitui o campo Tom TX do canal."),
    "fmenable": ("Desabilitar rádio FM", "A opção tem sentido negativo: marcada, desabilita o receptor de radiodifusão FM. Não se refere ao modo FM/NFM dos canais de comunicação."),
    "voxsw": ("VOX ligado", "Permite transmitir pela detecção de voz no microfone, sem manter o PTT pressionado. Ajuste também a sensibilidade e o atraso do VOX."),
    "vox": ("Sensibilidade do VOX", "Seleciona o nível de disparo da transmissão por som. Ajuste no ambiente em que usará o rádio para evitar disparos por ruídos. No perfil sem GPS, a opção Desligado também desativa o VOX."),
    "voxdlytime": ("Atraso do VOX", "Tempo que a transmissão permanece ativa após o som cair abaixo do limiar do VOX. Um intervalo maior evita cortes entre palavras, mas mantém o canal ocupado por mais tempo."),
    "scanmode": ("Modo de varredura", "Por tempo: retoma a busca após um intervalo. Por portadora: retoma quando o sinal desaparece. Busca: para no sinal encontrado, conforme o firmware. Incluir canais na varredura é uma configuração separada de cada memória."),
    "ctsdcsscantype": ("Salvar tom encontrado", "Ao usar a busca de CTCSS/DCS do rádio, escolhe se o tom detectado será associado ao RX, ao TX ou a ambos. Não inicia uma busca a partir do computador."),
    "rpttailclear": ("Cauda da repetidora", "Intervalo associado ao tratamento da cauda de repetidora. Depende de compatibilidade com o sistema utilizado. Não é o deslocamento de frequência (offset) da repetidora."),
    "rpttaildet": ("Detecção de cauda", "Tempo associado à detecção/tratamento do fim de sinal da repetidora. Os efeitos variam conforme o firmware e a repetidora; mantenha o valor atual se não precisar desse recurso."),
    "autolock": ("Bloqueio automático do teclado", "Faz o rádio bloquear as teclas após o período definido pelo firmware. Não bloqueia a transmissão de um canal nem modifica suas frequências."),
    "keylock": ("Estado de bloqueio do teclado", "Define se o teclado deve ficar bloqueado. O desbloqueio físico continua dependendo da combinação de teclas do aparelho. Não é o bloqueio de TX."),
    "key2short": ("Tecla lateral 2", "Associa uma função ao toque curto da segunda tecla lateral. Os valores oferecidos são os reconhecidos por este perfil; não remapeia outras teclas."),
    "rstmenu": ("Permitir reset pelo menu", "Permite disponibilizar a restauração de padrões no menu do rádio. Não executa um reset no momento em que você marca a opção no computador."),
    "alarmmode": ("Modo de alarme", "Local reproduz o alarme no aparelho. Enviar tom ou código pode acionar transmissão segundo o firmware. Escolha o comportamento desejado antes de usar a tecla de emergência."),
    "alarmtone": ("Som do alarme", "Liga ou desliga o som associado à função de alarme. O tipo de ação do alarme é escolhido no ajuste Modo do alarme."),
    "pttdly": ("Atraso de envio de identificação", "Intervalo em milissegundos associado ao envio do identificador quando o PTT é acionado. Não define o tempo máximo de transmissão."),
    "gpsw": ("GPS ligado", "Habilita o receptor de posicionamento do rádio. Uma posição válida depende de visibilidade dos satélites. Não transforma um modelo sem hardware GPS em um modelo GPS."),
    "gpsmode": ("Sistema de posicionamento", "Seleciona GPS, BeiDou ou ambos, conforme o receptor do aparelho. Não altera as faixas de recepção/transmissão de voz."),
    "gpstimezone": ("Fuso horário", "Deslocamento, em horas, em relação ao UTC. Para o horário de Brasília, a referência usual é -3. Não configura automaticamente mudanças de horário nem a posição geográfica."),
    "imagem": ("Imagem de abertura", "O UV-17 Pro GPS usa 150 x 128 pixels; o UV-21 Pro e o UV-21 Pro GPS, 128 x 160 (tela em pé). A imagem é convertida para RGB565 antes do envio. O botão envia somente a imagem; para exibi-la, selecione Tela ao ligar = Logotipo nos ajustes e grave a programação. A cópia guardada é da imagem enviada pelo computador, não da imagem extraída do rádio."),
    "u5_squelch": ('Squelch (UV-5R)', 'Nível de sinal necessário para abrir o áudio. 0 deixa o áudio sempre aberto; números maiores exigem sinal mais forte.'),
    "u5_timeout": ('Tempo limite de transmissão', 'Interrompe a transmissão depois do tempo escolhido, para evitar PTT preso. A opção Desligado só funciona em parte dos firmwares do UV-5R.'),
    "u5_save": ('Economia de bateria', 'Desliga o receptor em ciclos quando não há sinal. Proporções maiores economizam mais, mas podem cortar o início das chamadas.'),
    "u5_tdr": ('Dupla escuta', 'Alterna entre as linhas A e B. Quando uma delas recebe sinal, o rádio para nela até o sinal acabar.'),
    "u5_tdrab": ('Prioridade de TX na dupla escuta', 'Com a dupla escuta ligada, define em qual linha o rádio transmite ao apertar o PTT. Desligada: transmite na linha em uso.'),
    "u5_workmode": ('Modo ao ligar', 'Frequência (VFO) para digitar frequências livremente; Canal (MR) para usar os canais gravados. No rádio, alterne com a tecla VFO/MR.'),
    "u5_mdfa": ('Exibição do canal A', 'O que a linha A mostra no modo canal: o número, o nome gravado ou a frequência.'),
    "u5_mdfb": ('Exibição do canal B', 'O que a linha B mostra no modo canal: o número, o nome gravado ou a frequência.'),
    "u5_abr": ('Luz do visor', 'Por quantos segundos a luz do visor fica acesa depois de usar o rádio. Desligada apaga a luz automática.'),
    "u5_wtled": ('Cor da luz em espera', 'Cor do visor com o rádio parado.'),
    "u5_rxled": ('Cor da luz ao receber', 'Cor do visor enquanto recebe sinal.'),
    "u5_txled": ('Cor da luz ao transmitir', 'Cor do visor enquanto transmite.'),
    "u5_ponmsg": ('Tela ao ligar', 'Teste do visor acende todos os segmentos ao ligar. Mensagem mostra as duas linhas de texto abaixo (por exemplo, seu nome e indicativo).'),
    "u5_msg1": ('Mensagem de abertura, linha 1', 'Até 7 letras, números ou símbolos simples, sem acento. Aparece ao ligar quando Tela ao ligar = Mensagem.'),
    "u5_msg2": ('Mensagem de abertura, linha 2', 'Até 7 letras, números ou símbolos simples, sem acento. Aparece ao ligar quando Tela ao ligar = Mensagem.'),
    "u5_voice": ('Aviso de voz', 'Idioma dos avisos falados. As vozes do UV-5R ficam no firmware e não podem ser trocadas pelo cabo.'),
    "u5_beep": ('Bipe das teclas', 'Som ao apertar as teclas.'),
    "u5_roger": ('Bipe de fim de transmissão', 'Toca um bipe ao soltar o PTT, avisando os outros que você terminou de falar.'),
    "u5_ste": ('Eliminação de cauda', 'Reduz o ruído (chiado) no fim das transmissões entre rádios portáteis.'),
    "u5_vox": ('VOX', 'Transmissão acionada pela voz. Desligado exige o PTT; números maiores exigem voz mais alta para transmitir.'),
    "u5_screv": ('Retomada da varredura', 'Por tempo: para no sinal e continua após alguns segundos. Por portadora: continua quando o sinal acaba. Busca: para no primeiro sinal e encerra.'),
    "u5_rpste": ('Eliminação de cauda da repetidora', 'Reduz o ruído no fim das transmissões recebidas por repetidora. O valor deve combinar com o da repetidora.'),
    "u5_rptrl": ('Atraso da eliminação de cauda', 'Tempo de atraso usado na eliminação de cauda pela repetidora.'),
    "u5_bcl": ('Bloqueio de canal ocupado (geral)', 'Impede transmitir quando há sinal no canal. O mesmo ajuste também existe por canal (coluna BCL).'),
    "u5_autolk": ('Bloqueio automático do teclado', 'Bloqueia o teclado sozinho depois de alguns segundos sem uso.'),
    "u5_keylock": ('Teclado bloqueado', 'Estado do bloqueio do teclado gravado no rádio.'),
    "u5_almod": ('Modo do alarme', 'Local: só toca no rádio. Enviar tom: transmite o tom de alarme. Enviar código: transmite o código de alarme.'),
    "encaixe": ("Encaixe da imagem", "Ajustar preserva toda a imagem e acrescenta bordas se necessário. Preencher corta o excesso para ocupar o visor sem deformar. Esticar ocupa toda a área e pode deformar as proporções. A prévia já reduz as cores para simular o visor."),
}


class IconeAjuda(tk.Canvas):
    """Ícone circular i e tooltip que permite ler/rolar sem tomar o foco."""
    def __init__(self, pai, chave):
        if chave not in TEXTOS:
            raise KeyError(f"Ajuda não cadastrada: {chave}")
        estilo = ttk.Style(pai)
        fundo = estilo.lookup("TFrame", "background") or tema.C["fundo"]
        import tkinter.font as tkfont
        px = max(18, round(tkfont.nametofont("TkDefaultFont").metrics("linespace") * 1.05))
        super().__init__(pai, width=px + 2, height=px + 2, bg=fundo,
                         highlightthickness=0, bd=0, cursor="question_arrow", takefocus=1)
        self.chave = chave
        self.balao = None
        self._espera = None
        self._fechar = None
        # ícone i da família Lucide, em imagem nítida no tamanho da letra (acompanha a escala do Windows)
        self._img = tema.icone("info", px, tema.C["primario"])
        # fundo circular (muda de cor ao passar o mouse ou receber o foco); o desenho do ícone fica por cima
        self.create_oval(1, 1, px + 1, px + 1, fill=tema.C["secundario"], outline="", tags="circulo")
        self.create_image((px + 2) // 2, (px + 2) // 2, image=self._img, tags="letra")
        self.bind("<Enter>", self._entra)
        self.bind("<Leave>", self._sai)
        self.bind("<FocusIn>", lambda e: self.mostrar())
        self.bind("<FocusOut>", self._sai)
        self.bind("<Button-1>", lambda e: self.mostrar())
        self.bind("<F1>", self._tecla)
        self.bind("<Return>", self._tecla)
        self.bind("<space>", self._tecla)
        self.bind("<Escape>", lambda e: self.ocultar())
        self.bind("<Destroy>", self._destruir)

    def _tecla(self, evento):
        self.mostrar()
        return "break"

    def _cancela(self, atributo):
        identificador = getattr(self, atributo)
        if identificador is not None:
            try:
                self.after_cancel(identificador)
            except tk.TclError:
                pass
            setattr(self, atributo, None)

    def _entra(self, evento=None):
        self._cancela("_fechar")
        self.itemconfigure("circulo", fill=tema.C["selecao"], outline=tema.C["primario_p"])
        if self.balao is None:
            self._cancela("_espera")
            self._espera = self.after(350, self.mostrar)

    def _sai(self, evento=None):
        self._cancela("_espera")
        self.itemconfigure("circulo", fill=tema.C["secundario"], outline=tema.C["primario"])
        self._cancela("_fechar")
        self._fechar = self.after(180, self._fecha_se_fora)

    def _contem_ponteiro(self, widget):
        if widget is None or not widget.winfo_exists():
            return False
        x, y = self.winfo_pointerxy()
        return (widget.winfo_rootx() <= x < widget.winfo_rootx() + widget.winfo_width()
                and widget.winfo_rooty() <= y < widget.winfo_rooty() + widget.winfo_height())

    def _fecha_se_fora(self):
        self._fechar = None
        if not self._contem_ponteiro(self) and not self._contem_ponteiro(self.balao):
            self.ocultar()

    def mostrar(self):
        self._cancela("_espera")
        self._cancela("_fechar")
        if self.balao is not None:
            return
        titulo, texto = TEXTOS[self.chave]
        tela_w, tela_h = self.winfo_screenwidth(), self.winfo_screenheight()
        largura = min(510, max(240, tela_w - 24))
        fonte = tkfont.nametofont("TkDefaultFont")
        coluna = max(1, fonte.measure("0"))
        linhas = sum(max(1, (fonte.measure(parte) + largura - 43) // (largura - 42))
                     for parte in texto.split("\n"))
        max_linhas = max(3, min(16, (tela_h - 120) // max(1, fonte.metrics("linespace"))))
        altura = min(max_linhas, max(3, linhas + 1))
        self.balao = janela = tk.Toplevel(self)
        janela.withdraw()
        janela.overrideredirect(True)
        try:
            janela.attributes("-topmost", True)
        except tk.TclError:
            pass
        borda = tk.Frame(janela, background=tema.C["borda"], padx=1, pady=1)
        borda.pack(fill="both", expand=True)
        miolo = tk.Frame(borda, background=tema.C["cartao"], padx=12, pady=10)
        miolo.pack(fill="both", expand=True)
        tk.Label(miolo, text=titulo, background=tema.C["cartao"], foreground=tema.C["texto"],
                 font="TkHeadingFont", wraplength=largura-30, justify="left", anchor="w").pack(fill="x", pady=(0, 6))
        corpo = tk.Frame(miolo, background=tema.C["cartao"])
        corpo.pack(fill="both", expand=True)
        campo = tk.Text(corpo, wrap="word", width=max(24, (largura-42)//coluna), height=altura,
                        font="TkDefaultFont", background=tema.C["cartao"], foreground=tema.C["texto"],
                        relief="flat", bd=0, highlightthickness=0, padx=0, pady=0,
                        cursor="arrow", takefocus=0)
        campo.pack(side="left", fill="both", expand=True)
        campo.insert("1.0", texto)
        campo.configure(state="disabled")
        if linhas + 1 > max_linhas:
            rol = ttk.Scrollbar(corpo, command=campo.yview)
            rol.pack(side="right", fill="y", padx=(8, 0))
            campo.configure(yscrollcommand=rol.set)
        for w in (janela, borda, miolo, corpo, campo):
            w.bind("<Enter>", lambda e: self._cancela("_fechar"))
            w.bind("<Leave>", self._sai)
        janela.update_idletasks()
        w, h = janela.winfo_reqwidth(), janela.winfo_reqheight()
        x = max(8, min(self.winfo_rootx()+12, tela_w-w-8))
        y = self.winfo_rooty()+self.winfo_height()+8
        if y+h > tela_h-8:
            y = max(8, self.winfo_rooty()-h-8)
        janela.geometry(f"+{x}+{y}")
        janela.deiconify()

    def ocultar(self):
        self._cancela("_espera")
        self._cancela("_fechar")
        janela, self.balao = self.balao, None
        if janela is not None:
            try:
                janela.destroy()
            except tk.TclError:
                pass

    def _destruir(self, evento):
        if evento.widget is self:
            self.ocultar()


def botao(pai, chave):
    # Mesmo ponto de integração das versões anteriores, com ícone e tooltip.
    return IconeAjuda(pai, chave)

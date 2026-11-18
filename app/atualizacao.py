# -*- coding: utf-8 -*-
"""
Verificação de versão nova na página de downloads do PYProg no GitHub.

Só consulta a última versão publicada (nenhum dado do usuário ou do rádio é enviado).
Se houver versão mais nova, o rodapé mostra um aviso. Ao atualizar, o instalador é
baixado, conferido pelo código SHA-256 informado pelo GitHub e aberto; o PYProg fecha.
"""
import hashlib
import json
import os
import re
import ssl
import sys
import tempfile
import threading
import urllib.request
import webbrowser
from tkinter import messagebox

REPO = "pyprogbr/PYProg"
URL_API = f"https://api.github.com/repos/{REPO}/releases/latest"
URL_PAGINA = f"https://github.com/{REPO}/releases/latest"
PREFIXO_INSTALADOR = "Instalar_PYProg"
PREFIXO_WIN7 = "Windows7_Instalar_PYProg"


def windows_antigo():
    """Windows 7 ou 8 (anterior ao 8.1), que precisa do instalador próprio."""
    if sys.platform != "win32":
        return False
    v = sys.getwindowsversion()
    return (v.major, v.minor) < (6, 3)


def numero_versao(txt):
    """'v1.2.3', '1.2.3 (beta)' -> (1, 2, 3)."""
    nums = re.findall(r"\d+", str(txt or ""))[:3]
    return tuple(int(n) for n in nums) + (0,) * (3 - len(nums))


def eh_mais_nova(remota, local):
    return numero_versao(remota) > numero_versao(local)


def _contexto_ssl():
    try:
        import certifi  # type: ignore
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _abre(url, versao_local, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": f"PYProg/{versao_local}",
                                               "Accept": "application/vnd.github+json"})
    return urllib.request.urlopen(req, timeout=timeout, context=_contexto_ssl())


def consulta(versao_local):
    """Retorna dict com versao, notas, url_pagina, instalador {nome, url, tamanho, sha256} ou None."""
    with _abre(URL_API, versao_local) as r:
        dados = json.loads(r.read().decode("utf-8"))
    inst = None
    # No Windows 7 e 8 usa o instalador próprio (Windows7_Instalar_PYProg_...); nos demais, o normal
    prefixo = PREFIXO_WIN7 if windows_antigo() else PREFIXO_INSTALADOR
    for a in dados.get("assets", []):
        nome = a.get("name", "")
        if nome.startswith(prefixo) and nome.lower().endswith(".exe"):
            dig = a.get("digest") or ""
            inst = {"nome": nome, "url": a.get("browser_download_url"), "tamanho": a.get("size", 0),
                    "sha256": dig.split(":", 1)[1].lower() if dig.startswith("sha256:") else None}
            break
    return {"versao": (dados.get("tag_name") or "").lstrip("vV"), "notas": dados.get("body") or "",
            "url_pagina": dados.get("html_url") or URL_PAGINA, "instalador": inst}


def baixa(inst, versao_local, progresso=None):
    pasta = os.path.join(tempfile.gettempdir(), "PYProg_atualizacao")
    os.makedirs(pasta, exist_ok=True)
    destino = os.path.join(pasta, os.path.basename(inst["nome"]))
    h = hashlib.sha256()
    total = inst.get("tamanho") or 0
    feito = 0
    with _abre(inst["url"], versao_local, timeout=30) as r, open(destino + ".parcial", "wb") as f:
        while True:
            bloco = r.read(256 * 1024)
            if not bloco:
                break
            f.write(bloco)
            h.update(bloco)
            feito += len(bloco)
            if progresso and total:
                pct = min(99, feito * 100 // total)
                progresso(pct, f"Baixando a atualização... {pct}%")
    if inst.get("sha256") and h.hexdigest() != inst["sha256"]:
        os.unlink(destino + ".parcial")
        raise RuntimeError("O arquivo baixado não confere com o código SHA-256 informado pelo GitHub. "
                           "A atualização foi cancelada; tente de novo mais tarde.")
    os.replace(destino + ".parcial", destino)
    return destino


def verifica(app, manual=False):
    """Consulta em segundo plano; o resultado volta para a janela pela fila do app."""
    import vozes_core as vc
    local = vc.VERSAO

    def tarefa():
        try:
            info = consulta(local)
            erro = None
        except Exception as e:
            info, erro = None, e
        # O resultado volta pela fila do app: o Tk só pode ser usado pela thread da janela
        app.fila.put(("chama", lambda: _resultado(app, info, erro, manual, local), None))
    if manual:
        app.status.config(text="Verificando atualizações...")
    threading.Thread(target=tarefa, daemon=True).start()


def _resultado(app, info, erro, manual, local):
    if erro is not None or not info or not info.get("versao"):
        if manual:
            app.status.config(text="Não foi possível verificar atualizações.")
            messagebox.showinfo("Atualizações", "Não foi possível consultar a página de downloads agora. "
                                                "Confira a conexão com a internet e tente de novo.\n\n"
                                                f"Detalhe: {erro or 'sem versão publicada'}")
        return
    if not eh_mais_nova(info["versao"], local):
        if manual:
            app.status.config(text=f"Você está com a versão mais recente ({local}).")
            messagebox.showinfo("Atualizações", f"Você está com a versão mais recente do PYProg ({local}).")
        return
    # Versão nova: abre a janela de atualização a cada abertura do programa
    oferece(app, info)


def oferece(app, info):
    import vozes_core as vc
    notas = info["notas"].strip()
    if len(notas) > 1200:
        notas = notas[:1200] + "..."
    inst = info.get("instalador")
    texto = f"Há uma versão nova do PYProg: {info['versao']} (você está com a {vc.VERSAO}).\n\n"
    if notas:
        texto += f"Novidades:\n{notas}\n\n"
    if sys.platform != "win32" or not inst or not inst.get("url"):
        if messagebox.askyesno("Atualização", texto + "Abrir a página de downloads?"):
            webbrowser.open(info["url_pagina"])
        return
    if not inst.get("sha256"):
        # Sem o código de conferência, não instala sozinho: abre a página
        if messagebox.askyesno("Atualização", texto + "Abrir a página de downloads para baixar o instalador?"):
            webbrowser.open(info["url_pagina"])
        return
    if not messagebox.askyesno("Atualização", texto + "Baixar e instalar agora? O PYProg vai fechar para a "
                                                      "instalação; o indicativo, as configurações e os backups "
                                                      "são mantidos."):
        return
    res = {}

    def tarefa():
        res["arq"] = baixa(inst, vc.VERSAO, app.progresso)

    def fim():
        app.status.config(text="Atualização baixada e conferida.")
        if app.fecha_para_atualizar():
            try:
                os.startfile(res["arq"])  # pede elevação (UAC) como um duplo clique
            except Exception as e:  # pragma: no cover
                messagebox.showerror("Atualização", f"Não foi possível abrir o instalador: {e}\n\n{res['arq']}")
    app.executa("Baixando a atualização...", tarefa, depois=fim)

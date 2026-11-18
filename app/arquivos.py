"""Gravação atômica, cache local e histórico das transferências."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
import uuid
from pathlib import Path


def grava_atomico(caminho, dados):
    destino = Path(caminho)
    destino.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=destino.name + ".", suffix=".tmp", dir=destino.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(dados)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, destino)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def grava_json(caminho, dados):
    grava_atomico(caminho, json.dumps(dados, ensure_ascii=False, indent=2).encode("utf-8"))


def assinatura(*partes):
    h = hashlib.sha256()
    for p in partes:
        if not isinstance(p, bytes):
            p = json.dumps(p, sort_keys=True, ensure_ascii=False).encode("utf-8")
        h.update(len(p).to_bytes(8, "little"))
        h.update(p)
    return h.hexdigest()


class RegistroEnvio:
    """Cópia do material a enviar; nunca representa uma extração de vozes/imagem."""

    def __init__(self, pasta, tipo, modelo, porta, extensao, salva):
        nome = time.strftime("%Y-%m-%d_%H-%M-%S") + "_" + uuid.uuid4().hex[:8]
        self.base = Path(pasta) / f"{tipo}_{nome}_{modelo}"
        self.arquivo = str(self.base) + extensao
        self.registro = str(self.base) + ".envio.json"
        salva(self.arquivo)  # falha aqui impede iniciar a transferência
        bruto = Path(self.arquivo).read_bytes()
        self.dados = dict(tipo=tipo, modelo=modelo, porta=porta,
                          inicio=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                          arquivo=Path(self.arquivo).name,
                          sha256=hashlib.sha256(bruto).hexdigest(),
                          estado="preparado", leitura_de_retorno=False,
                          origem="Cópia do arquivo preparado no computador; não extraído do rádio")
        self.grava()

    def grava(self):
        grava_json(self.registro, self.dados)

    def executa(self, enviar):
        self.dados["estado"] = "em_andamento"
        self.grava()
        try:
            enviar()
        except Exception as e:
            self.dados.update(estado="falha_ou_interrompido", erro=str(e),
                              fim=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
            try:
                self.grava()
            except OSError:
                pass  # o registro em_andamento permanece para diagnóstico
            raise
        self.dados.update(estado="concluido_sem_leitura_de_retorno",
                          fim=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
        try:
            self.grava()
        except OSError as e:
            return f"Transferência concluída, mas não foi possível atualizar o histórico: {e}"
        return ""

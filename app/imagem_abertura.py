# -*- coding: utf-8 -*-
"""
Imagem de abertura (tela exibida ao ligar) dos Baofeng da família UV-17.

Formato e protocolo conforme o utilitário "Import Picture tools" da Baofeng:
  - cores RGB565 (2 bytes por pixel, little-endian), linha por linha, de cima para baixo;
  - UV-17 Pro GPS: 150 x 128 pixels, gravados na flash a partir de 0xC0000;
  - UV-21 Pro e UV-21 Pro GPS: 128 x 160 pixels (tela em pé), a partir de 0x100000;
  - 1 bloco de 64 KB apagado, com o mesmo protocolo de pacotes usado para as vozes;
  - a saudação de conexão é a mesma usada na programação de cada modelo.
"""
from __future__ import annotations

import os

import configuracao_radio as cr
import vozes_core as vc

LARGURA, ALTURA = 150, 128          # UV-17 Pro GPS (padrão)
ENDERECO = 0xC0000
BLOCOS = 1
# modelo: (largura, altura, endereço na flash)
PERFIS = {"UV17ProGPS": (150, 128, 0xC0000),
          "UV21Pro": (128, 160, 0x100000),
          "UV21ProGPS": (128, 160, 0x100000)}


def tamanho(modelo="UV17ProGPS"):
    return PERFIS.get(modelo, PERFIS["UV17ProGPS"])[:2]
MODOS = ["Ajustar (com bordas)", "Preencher (cortar)", "Esticar"]


class ErroImagem(Exception):
    pass


def _pil():
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageOps  # type: ignore
        return Image, ImageDraw, ImageFont, ImageOps
    except ImportError as e:  # pragma: no cover
        raise ErroImagem("Biblioteca 'pillow' não instalada (pip install pillow).") from e


def abre(caminho):
    Image, *_ = _pil()
    try:
        return Image.open(caminho).convert("RGB")
    except Exception as e:
        raise ErroImagem(f"Não foi possível abrir a imagem: {e}") from e


def ajusta(img, modo=MODOS[0], fundo=(0, 0, 0), modelo="UV17ProGPS"):
    """Redimensiona para o tamanho da tela do modelo."""
    LARGURA, ALTURA = tamanho(modelo)
    Image, _, _, ImageOps = _pil()
    img = img.convert("RGB")
    if img.size == (LARGURA, ALTURA):
        return img.copy()
    if modo == MODOS[2]:
        return img.resize((LARGURA, ALTURA), Image.LANCZOS)
    if modo == MODOS[1]:
        return ImageOps.fit(img, (LARGURA, ALTURA), Image.LANCZOS)
    copia = img.copy()
    copia.thumbnail((LARGURA, ALTURA), Image.LANCZOS)
    tela = Image.new("RGB", (LARGURA, ALTURA), fundo)
    tela.paste(copia, ((LARGURA - copia.width) // 2, (ALTURA - copia.height) // 2))
    return tela


def _fonte(tamanho):
    _, _, ImageFont, _ = _pil()
    candidatos = ["arialbd.ttf", "segoeuib.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"]
    pastas = [os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts"),
              "/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/truetype/liberation"]
    for nome in candidatos:
        for p in [nome] + [os.path.join(d, nome) for d in pastas]:
            try:
                return ImageFont.truetype(p, tamanho)
            except Exception:
                continue
    return ImageFont.load_default()


def com_texto(linhas, cor_fundo=(0, 32, 96), cor_texto=(255, 255, 255), cor_destaque=(255, 210, 0),
              modelo="UV17ProGPS"):
    """Cria uma tela de abertura com até 3 linhas de texto centralizadas.
    A primeira linha (ex.: o indicativo) sai maior e na cor de destaque."""
    LARGURA, ALTURA = tamanho(modelo)
    Image, ImageDraw, _, _ = _pil()
    img = Image.new("RGB", (LARGURA, ALTURA), cor_fundo)
    d = ImageDraw.Draw(img)
    linhas = [l.strip() for l in linhas if l and l.strip()][:3]
    if not linhas:
        return img
    blocos = []
    for i, txt in enumerate(linhas):
        alvo = 40 if i == 0 else 18
        tam = alvo
        while tam > 8:
            f = _fonte(tam)
            x0, y0, x1, y1 = d.textbbox((0, 0), txt, font=f)
            if x1 - x0 <= LARGURA - 10:
                break
            tam -= 1
        blocos.append((txt, f, x1 - x0, y1 - y0, y0, cor_destaque if i == 0 else cor_texto))
    espaco = 8
    total = sum(b[3] for b in blocos) + espaco * (len(blocos) - 1)
    y = (ALTURA - total) // 2
    for txt, f, w, h, off, cor in blocos:
        d.text(((LARGURA - w) // 2, y - off), txt, font=f, fill=cor)
        y += h + espaco
    return img


def para_rgb565(img, modelo="UV17ProGPS") -> bytes:
    LARGURA, ALTURA = tamanho(modelo)
    if img.size != (LARGURA, ALTURA):
        raise ErroImagem(f"A imagem precisa ter {LARGURA} x {ALTURA} pixels.")
    out = bytearray()
    px = img.convert("RGB").load()
    for y in range(ALTURA):
        for x in range(LARGURA):
            r, g, b = px[x, y]
            v = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
            out += bytes((v & 0xFF, v >> 8))
    return bytes(out)


def de_rgb565(dados: bytes, modelo="UV17ProGPS"):
    LARGURA, ALTURA = tamanho(modelo)
    Image, *_ = _pil()
    img = Image.new("RGB", (LARGURA, ALTURA))
    px = img.load()
    i = 0
    for y in range(ALTURA):
        for x in range(LARGURA):
            v = dados[i] | (dados[i + 1] << 8)
            i += 2
            r, g, b = (v >> 11) & 31, (v >> 5) & 63, v & 31
            px[x, y] = ((r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2))
    return img


def previa(img, modelo="UV17ProGPS"):
    """Como a imagem vai aparecer no visor (cores reduzidas a RGB565)."""
    return de_rgb565(para_rgb565(img, modelo), modelo)


def envia(porta, img, progresso=None, log=None, modelo="UV17ProGPS"):
    if modelo not in PERFIS:
        raise ErroImagem("Este rádio não permite trocar a imagem de abertura.")
    dados = para_rgb565(img, modelo)
    vc.envia_dados(porta, cr.CLONE[modelo]["magic"].decode("ascii"), dados, len(dados),
                   PERFIS[modelo][2], BLOCOS, progresso, log, "imagem")

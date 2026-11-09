# PYProg

Programação de rádios: canais, ajustes, vozes e imagem de abertura.

**[Baixar a versão mais recente](https://github.com/pyprogbr/PYProg/releases/latest)**

![Downloads](https://img.shields.io/github/downloads/pyprogbr/PYProg/total?label=downloads)

Na página da versão, baixe `Instalar_PYProg_<versão>.exe` e execute. Não é preciso instalar mais nada. Se o Windows mostrar "O Windows protegeu o computador", clique em "Mais informações" e depois em "Executar assim mesmo".

Depois de instalado, o PYProg avisa quando houver versão nova.

## O que o programa faz

- Lê e grava a programação pelo cabo: canais, zonas ou bancos e ajustes, com backup automático.
- Edita o arquivo .rdt do CPS do Retevis RT3S e do Baofeng DM-1701, com todas as telas do CPS.
- Ordena, arrasta e organiza canais, zonas, contatos e listas, mantendo as referências atualizadas.
- Bloqueia a transmissão fora das faixas liberadas.
- Gera vozes em português, inglês e espanhol para o rádio.
- Troca a imagem de abertura (UV-17 Pro GPS, UV-21 Pro e UV-21 Pro GPS).
- Exporta a lista de canais em PDF ou CSV.

## Modelos

| Modelo | Programação | Vozes | Imagem de abertura | Situação |
|---|---|---|---|---|
| Baofeng UV-17 Pro GPS | pelo cabo | sim | sim | testado |
| Baofeng UV-17 Pro / R / L | pelo cabo | sim | não | experimental |
| Baofeng UV-17R Plus | pelo cabo | não | não | experimental |
| Baofeng UV-21 Pro / Pro GPS | pelo cabo | não | sim | experimental |
| Baofeng UV-5R e compatíveis | pelo cabo | não | não | testado |
| Icom IC-2730A | pelo cabo | não | não | testado |
| Retevis RT3S | arquivo .rdt do CPS | não | não | testado com o CPS |
| Baofeng DM-1701 | arquivo .rdt do CPS | não | não | experimental |

## Arquivos de terceiros

Para editar as vozes, o PYProg pede uma vez o pacote base de vozes (.vpa) que acompanha o CPS modificado (miklor.com); ele não é distribuído aqui. A geração de vozes usa um serviço on-line da Microsoft, sujeito aos termos desse serviço.

## Aviso

Esta é uma versão de testes (beta), distribuída gratuitamente e sem garantia de qualquer tipo, podendo conter falhas. Antes de gravar alterações, confira o modelo selecionado e guarde uma cópia da programação. As vozes e a imagem de abertura gravadas no rádio não podem ser lidas de volta pelo computador: depois de trocadas, as originais não podem ser restauradas. O uso é de responsabilidade exclusiva do usuário e deve observar as normas da Anatel.

Projeto independente, sem vínculo com fabricantes de rádios ou com o projeto CHIRP.

## Licença

O PYProg usa código do [CHIRP](https://www.chirpmyradio.com) e é distribuído sob a [GNU GPL versão 3](https://www.gnu.org/licenses/gpl-3.0.html). O código-fonte de cada versão está na página da versão, no arquivo `PYProg_<versão>_codigo_fonte.zip`.

Contato: pu2keu@gmail.com

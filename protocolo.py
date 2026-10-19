"""Protocolo TCP: mensagens JSON com tamanho e inteiros uint16 em blocos."""

from array import array
import json
from pathlib import Path
import socket
import struct
import sys

VERSAO = 1
ELEMENTOS_PADRAO = 1_000_000
BLOCO_PADRAO = 32_768
MAX_JSON = 65_536
CABECALHO = struct.Struct("!I")


class ErroProtocolo(ValueError):
    """Mensagem inválida ou conexão encerrada antes do esperado."""


def inteiro_positivo(texto: str) -> int:
    valor = int(texto)
    if valor <= 0:
        raise ValueError("O valor deve ser um inteiro positivo.")
    return valor


def segundos_positivos(texto: str) -> float:
    valor = float(texto)
    if not 0 < valor < float("inf"):
        raise ValueError("O tempo deve ser positivo e finito.")
    return valor


def receber_exatamente(conexao: socket.socket, quantidade: int) -> bytearray:
    """TCP é um fluxo: recv_into pode preencher apenas parte do buffer."""
    dados = bytearray(quantidade)
    vista = memoryview(dados)
    posicao = 0
    while posicao < quantidade:
        recebidos = conexao.recv_into(vista[posicao:])
        if recebidos == 0:
            raise ErroProtocolo(
                f"Conexão encerrada: recebidos {posicao} de {quantidade} bytes."
            )
        posicao += recebidos
    return dados


def enviar_json(conexao: socket.socket, mensagem: dict) -> None:
    dados = json.dumps(mensagem, ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(dados) > MAX_JSON:
        raise ErroProtocolo("Mensagem JSON muito grande.")
    conexao.sendall(CABECALHO.pack(len(dados)) + dados)


def receber_json(conexao: socket.socket) -> dict:
    tamanho = CABECALHO.unpack(receber_exatamente(conexao, CABECALHO.size))[0]
    if not 0 < tamanho <= MAX_JSON:
        raise ErroProtocolo("Tamanho de mensagem JSON inválido.")
    try:
        mensagem = json.loads(receber_exatamente(conexao, tamanho))
    except (UnicodeError, ValueError) as erro:
        raise ErroProtocolo("JSON inválido.") from erro
    if not isinstance(mensagem, dict):
        raise ErroProtocolo("A mensagem deve ser um objeto JSON.")
    return mensagem


def codificar_numeros(numeros: array) -> bytes:
    """Cada número usa 2 bytes em ordem de rede (big endian)."""
    copia = array("H", numeros)
    if copia.itemsize != 2:
        raise ErroProtocolo("Esta plataforma não fornece uint16 de 2 bytes.")
    if sys.byteorder == "little":
        copia.byteswap()
    return copia.tobytes()


def decodificar_numeros(dados: bytes | bytearray) -> array:
    numeros = array("H")
    if numeros.itemsize != 2 or len(dados) % 2:
        raise ErroProtocolo("Bloco uint16 inválido.")
    numeros.frombytes(dados)
    if sys.byteorder == "little":
        numeros.byteswap()
    return numeros


def salvar_json(caminho: Path, dados: dict) -> None:
    """Publica o arquivo inteiro; o benchmark nunca lê JSON parcialmente escrito."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_name(caminho.name + ".tmp")
    temporario.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporario.replace(caminho)

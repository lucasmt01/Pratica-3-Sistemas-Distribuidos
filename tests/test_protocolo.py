"""Testa fragmentação TCP, ordem dos bytes e rejeição de mensagens inválidas."""

from array import array
import struct
import unittest

from protocolo import (
    ErroProtocolo, MAX_JSON, codificar_numeros, decodificar_numeros,
    enviar_json, receber_exatamente, receber_json,
)


class SocketFragmentado:
    """Simula recv retornando um único byte, mesmo com buffer maior."""

    def __init__(self, dados: bytes):
        self.dados = bytearray(dados)
        self.enviados = bytearray()

    def recv_into(self, buffer: memoryview) -> int:
        quantidade = min(1, len(buffer), len(self.dados))
        buffer[:quantidade] = self.dados[:quantidade]
        del self.dados[:quantidade]
        return quantidade

    def sendall(self, dados: bytes) -> None:
        self.enviados.extend(dados)


class TestProtocolo(unittest.TestCase):
    def test_leitura_fragmentada(self):
        self.assertEqual(receber_exatamente(SocketFragmentado(b"abcdef"), 6), b"abcdef")

    def test_desconexao_prematura(self):
        with self.assertRaises(ErroProtocolo):
            receber_exatamente(SocketFragmentado(b"abc"), 6)

    def test_json_fragmentado(self):
        mensagem = {"tipo": "pronto", "cliente_id": 16}
        conexao = SocketFragmentado(b"")
        enviar_json(conexao, mensagem)
        self.assertEqual(receber_json(SocketFragmentado(bytes(conexao.enviados))), mensagem)

    def test_json_tamanho_invalido(self):
        for tamanho in (0, MAX_JSON + 1):
            with self.subTest(tamanho=tamanho), self.assertRaises(ErroProtocolo):
                receber_json(SocketFragmentado(struct.pack("!I", tamanho)))

    def test_json_conteudo_invalido(self):
        for dados in (b"[1,2]", b"{invalido}", b"\xff"):
            with self.subTest(dados=dados), self.assertRaises(ErroProtocolo):
                receber_json(SocketFragmentado(struct.pack("!I", len(dados)) + dados))

    def test_numeros_em_ordem_de_rede(self):
        numeros = array("H", [0, 1, 255, 256, 1000])
        esperado = b"\x00\x00\x00\x01\x00\xff\x01\x00\x03\xe8"
        self.assertEqual(codificar_numeros(numeros), esperado)
        self.assertEqual(list(decodificar_numeros(esperado)), list(numeros))

    def test_bloco_incompleto(self):
        with self.assertRaises(ErroProtocolo):
            decodificar_numeros(b"\x00")


if __name__ == "__main__":
    unittest.main()

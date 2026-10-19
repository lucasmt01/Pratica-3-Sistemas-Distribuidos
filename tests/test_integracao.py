"""Testes com processos independentes, sockets reais e encerramento em falhas."""

from array import array
import csv
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest

from protocolo import VERSAO, codificar_numeros, enviar_json, receber_json

RAIZ = Path(__file__).resolve().parents[1]


class TestIntegracao(unittest.TestCase):
    def setUp(self):
        self.temporario = tempfile.TemporaryDirectory(prefix="sd_teste_")
        self.pasta = Path(self.temporario.name)
        self.processos = []

    def tearDown(self):
        for processo in self.processos:
            if processo.poll() is None:
                processo.kill()
            processo.wait(timeout=5)
            if processo.stdout:
                processo.stdout.close()
        self.temporario.cleanup()

    def iniciar_servidor(self, clientes=1, elementos=3, timeout=3):
        pronto = self.pasta / "pronto.json"
        processo = subprocess.Popen([
            sys.executable, str(RAIZ / "servidor.py"), "--porta", "0",
            "--clientes", str(clientes), "--elementos", str(elementos),
            "--timeout", str(timeout), "--pronto-json", str(pronto),
        ], cwd=RAIZ, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.processos.append(processo)
        limite = time.perf_counter() + 10
        while not pronto.exists():
            if processo.poll() is not None or time.perf_counter() > limite:
                self.fail("Servidor não iniciou: " + processo.communicate(timeout=5)[0].decode(errors="replace"))
            time.sleep(0.02)
        porta = json.loads(pronto.read_text(encoding="utf-8"))["porta"]
        return processo, porta

    def pronto(self, conexao, elementos=3, identificador=1):
        enviar_json(conexao, {"tipo": "pronto", "versao": VERSAO,
                              "elementos": elementos, "cliente_id": identificador})

    def test_benchmark_processos_e_blocos_incompletos(self):
        saida = self.pasta / "resultados.csv"
        processo = subprocess.Popen([
            sys.executable, str(RAIZ / "benchmark.py"), "--clientes", "1", "4",
            "--elementos", "103", "--bloco", "17", "--timeout", "20",
            "--saida", str(saida),
        ], cwd=RAIZ, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.processos.append(processo)
        texto, _ = processo.communicate(timeout=30)
        self.assertEqual(processo.returncode, 0, texto.decode(errors="replace"))
        with saida.open(newline="", encoding="utf-8") as arquivo:
            linhas = list(csv.DictReader(arquivo))
        self.assertEqual([int(linha["total_numeros"]) for linha in linhas], [103, 412])
        self.assertTrue(all(linha["validado"] == "True" for linha in linhas))
        self.assertTrue(all(float(linha["tempo_servidor_s"]) > 0 for linha in linhas))

    def test_limites_zero_e_mil(self):
        processo, porta = self.iniciar_servidor()
        with socket.create_connection(("127.0.0.1", porta), timeout=5) as conexao:
            self.pronto(conexao)
            self.assertEqual(receber_json(conexao)["tipo"], "iniciar")
            conexao.sendall(codificar_numeros(array("H", [0, 1000, 1000])))
            resposta = receber_json(conexao)
        self.assertEqual(resposta["soma_cliente"], 2000)
        self.assertEqual(resposta["soma_total"], 2000)
        self.assertEqual(processo.wait(timeout=5), 0)

    def test_largada_e_resultado_aguardam_todos(self):
        processo, porta = self.iniciar_servidor(clientes=2)
        with socket.create_connection(("127.0.0.1", porta), timeout=5) as primeira:
            with socket.create_connection(("127.0.0.1", porta), timeout=5) as segunda:
                self.pronto(primeira, identificador=1)
                primeira.settimeout(0.1)
                with self.assertRaises(socket.timeout):
                    primeira.recv(1)
                self.pronto(segunda, identificador=2)
                primeira.settimeout(5)
                self.assertEqual(receber_json(primeira)["tipo"], "iniciar")
                self.assertEqual(receber_json(segunda)["tipo"], "iniciar")
                primeira.sendall(codificar_numeros(array("H", [1, 2, 3])))
                primeira.settimeout(0.1)
                with self.assertRaises(socket.timeout):
                    primeira.recv(1)
                segunda.sendall(codificar_numeros(array("H", [4, 5, 6])))
                primeira.settimeout(5)
                for conexao, soma in ((primeira, 6), (segunda, 15)):
                    resposta = receber_json(conexao)
                    self.assertEqual(resposta["soma_cliente"], soma)
                    self.assertEqual(resposta["soma_total"], 21)
                    self.assertEqual(resposta["total_numeros"], 6)
        self.assertEqual(processo.wait(timeout=5), 0)

    def test_desconexao_durante_transmissao(self):
        processo, porta = self.iniciar_servidor()
        with socket.create_connection(("127.0.0.1", porta), timeout=5) as conexao:
            self.pronto(conexao)
            receber_json(conexao)
            conexao.sendall(b"\x00")
        self.assertEqual(processo.wait(timeout=5), 1)

    def test_quantidade_incompativel(self):
        processo, porta = self.iniciar_servidor()
        with socket.create_connection(("127.0.0.1", porta), timeout=5) as conexao:
            self.pronto(conexao, elementos=4)
        self.assertEqual(processo.wait(timeout=5), 1)

    def test_numero_fora_do_intervalo(self):
        processo, porta = self.iniciar_servidor()
        with socket.create_connection(("127.0.0.1", porta), timeout=5) as conexao:
            self.pronto(conexao)
            receber_json(conexao)
            conexao.sendall(codificar_numeros(array("H", [0, 1001, 2])))
        self.assertEqual(processo.wait(timeout=5), 1)

    def test_falta_de_cliente_aborta_barreira(self):
        processo, porta = self.iniciar_servidor(clientes=2, timeout=0.5)
        with socket.create_connection(("127.0.0.1", porta), timeout=5) as conexao:
            self.pronto(conexao)
            self.assertEqual(processo.wait(timeout=5), 1)

    def test_cliente_id_repetido(self):
        processo, porta = self.iniciar_servidor(clientes=2)
        with socket.create_connection(("127.0.0.1", porta), timeout=5) as primeira:
            with socket.create_connection(("127.0.0.1", porta), timeout=5) as segunda:
                self.pronto(primeira)
                self.pronto(segunda)
                self.assertEqual(processo.wait(timeout=5), 1)

    def test_timeout_apos_largada(self):
        processo, porta = self.iniciar_servidor(timeout=0.5)
        with socket.create_connection(("127.0.0.1", porta), timeout=5) as conexao:
            self.pronto(conexao)
            receber_json(conexao)
            self.assertEqual(processo.wait(timeout=5), 1)


if __name__ == "__main__":
    unittest.main()

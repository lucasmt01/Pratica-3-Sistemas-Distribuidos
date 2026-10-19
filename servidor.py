"""Servidor de uma rodada: uma thread por cliente, soma e tempo compartilhados."""

import argparse
from pathlib import Path
import socket
import threading
import time

from protocolo import (
    BLOCO_PADRAO, ELEMENTOS_PADRAO, VERSAO, ErroProtocolo,
    decodificar_numeros, enviar_json, inteiro_positivo, receber_exatamente,
    receber_json, salvar_json, segundos_positivos,
)


class Rodada:
    def __init__(self, clientes: int, elementos: int, bloco: int, timeout: float):
        self.clientes = clientes
        self.elementos = elementos
        self.bloco = bloco
        self.timeout = timeout
        self.lock = threading.Lock()
        self.finalizada = threading.Event()
        self.barreira = threading.Barrier(
            clientes + 1, action=self.iniciar_relogio, timeout=timeout
        )
        self.conexoes: list[socket.socket] = []
        self.ids: set[int] = set()
        self.resultados: dict[int, dict] = {}
        self.erros: list[str] = []
        self.inicio = 0.0
        self.tempo = 0.0
        self.soma_total = 0
        self.total_numeros = 0

    def iniciar_relogio(self) -> None:
        # Executada uma única vez, antes da liberação da barreira.
        self.inicio = time.perf_counter()

    def falhar(self, erro: BaseException) -> None:
        with self.lock:
            self.erros.append(f"{type(erro).__name__}: {erro}")
            conexoes = list(self.conexoes)
        self.barreira.abort()
        self.finalizada.set()
        # Desbloqueia as threads que estejam em recv/send em caso de falha.
        for conexao in conexoes:
            try:
                conexao.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def atender(self, conexao: socket.socket) -> None:
        try:
            with conexao:
                conexao.settimeout(self.timeout)
                mensagem = receber_json(conexao)
                identificador = mensagem.get("cliente_id")
                if (
                    mensagem.get("tipo") != "pronto"
                    or type(mensagem.get("versao")) is not int
                    or mensagem["versao"] != VERSAO
                    or type(mensagem.get("elementos")) is not int
                    or mensagem["elementos"] != self.elementos
                    or type(identificador) is not int
                    or not 1 <= identificador <= self.clientes
                ):
                    raise ErroProtocolo("Identificação ou quantidade de elementos inválida.")
                with self.lock:
                    if identificador in self.ids:
                        raise ErroProtocolo("Identificador de cliente repetido.")
                    self.ids.add(identificador)

                self.barreira.wait()
                enviar_json(conexao, {"tipo": "iniciar", "versao": VERSAO})
                soma = 0
                recebidos = 0
                while recebidos < self.elementos:
                    quantidade = min(self.bloco, self.elementos - recebidos)
                    dados = receber_exatamente(conexao, quantidade * 2)
                    numeros = decodificar_numeros(dados)
                    if any(numero > 1000 for numero in numeros):
                        raise ErroProtocolo("Número fora do intervalo de 0 a 1000.")
                    soma += sum(numeros)
                    recebidos += quantidade

                # O lock protege a acumulação e a identificação do último cliente.
                with self.lock:
                    self.resultados[identificador] = {
                        "cliente_id": identificador, "elementos": recebidos, "soma": soma,
                    }
                    self.soma_total += soma
                    self.total_numeros += recebidos
                    if len(self.resultados) == self.clientes:
                        self.tempo = time.perf_counter() - self.inicio
                        self.finalizada.set()

                if not self.finalizada.wait(self.timeout):
                    raise TimeoutError("Tempo esgotado aguardando os outros clientes.")
                with self.lock:
                    if self.erros:
                        raise ErroProtocolo("Rodada abortada por falha em outro cliente.")
                    resposta = {
                        "tipo": "resultado", "cliente_id": identificador,
                        "clientes": self.clientes, "elementos": recebidos,
                        "soma_cliente": soma, "soma_total": self.soma_total,
                        "total_numeros": self.total_numeros,
                        "tempo_servidor_s": self.tempo,
                    }
                enviar_json(conexao, resposta)
                print(f"Cliente {identificador:02d}: {recebidos:,} números; soma = {soma}", flush=True)
        except Exception as erro:
            self.falhar(erro)

    def resumo(self) -> dict:
        return {
            "clientes": self.clientes,
            "numeros_por_cliente": self.elementos,
            "total_numeros": self.total_numeros,
            "soma_total": self.soma_total,
            "tempo_servidor_s": self.tempo,
            "clientes_resultados": [self.resultados[i] for i in sorted(self.resultados)],
        }


def executar(args: argparse.Namespace) -> dict:
    rodada = Rodada(args.clientes, args.elementos, args.bloco, args.timeout)
    threads: list[threading.Thread] = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as servidor:
            servidor.bind((args.host, args.porta))
            servidor.listen(args.clientes)
            servidor.settimeout(0.25)
            porta = servidor.getsockname()[1]
            print(f"Servidor em {args.host}:{porta}; aguardando {args.clientes} cliente(s).", flush=True)
            if args.pronto_json:
                salvar_json(args.pronto_json, {"host": args.host, "porta": porta})
            limite = time.perf_counter() + args.timeout
            while len(threads) < args.clientes:
                with rodada.lock:
                    if rodada.erros:
                        raise ErroProtocolo(rodada.erros[0])
                if time.perf_counter() >= limite:
                    raise TimeoutError("Nem todos os clientes se conectaram a tempo.")
                try:
                    conexao, _ = servidor.accept()
                except socket.timeout:
                    continue
                with rodada.lock:
                    rodada.conexoes.append(conexao)
                thread = threading.Thread(target=rodada.atender, args=(conexao,),
                                          name=f"cliente-{len(threads) + 1}")
                threads.append(thread)
                thread.start()
            rodada.barreira.wait()
            for thread in threads:
                thread.join()
            if rodada.erros:
                raise ErroProtocolo(rodada.erros[0])
            resultado = rodada.resumo()
            if args.resultado_json:
                salvar_json(args.resultado_json, resultado)
            print(
                f"Rodada concluída: clientes={args.clientes}; "
                f"números={resultado['total_numeros']}; soma={resultado['soma_total']}; "
                f"tempo do servidor={resultado['tempo_servidor_s']:.6f} s", flush=True,
            )
            return resultado
    except BaseException as erro:
        rodada.falhar(erro)
        raise
    finally:
        for thread in threads:
            thread.join()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--porta", type=int, default=5000, help="0 escolhe uma porta livre")
    parser.add_argument("--clientes", type=inteiro_positivo, default=1)
    parser.add_argument("--elementos", type=inteiro_positivo, default=ELEMENTOS_PADRAO)
    parser.add_argument("--bloco", type=inteiro_positivo, default=BLOCO_PADRAO)
    parser.add_argument("--timeout", type=segundos_positivos, default=180.0)
    parser.add_argument("--pronto-json", type=Path, help="Sinalização para o benchmark")
    parser.add_argument("--resultado-json", type=Path)
    args = parser.parse_args()
    if not 0 <= args.porta <= 65535:
        parser.error("A porta deve estar entre 0 e 65535.")
    try:
        executar(args)
    except KeyboardInterrupt:
        print("Servidor interrompido; conexões e threads encerradas.")
        return 130
    except Exception as erro:
        print(f"ERRO no servidor: {erro}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Executa rodadas independentes com processos reais e valida todos os resultados."""

import argparse
import csv
from datetime import datetime, timezone
from contextlib import ExitStack
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time

from protocolo import (
    BLOCO_PADRAO, ELEMENTOS_PADRAO, inteiro_positivo, salvar_json, segundos_positivos,
)

RAIZ = Path(__file__).resolve().parent
CAMPOS = ("cenario", "clientes", "numeros_por_cliente", "total_numeros",
          "soma_total", "tempo_servidor_s", "validado", "seed_base")


def ler_json(caminho: Path) -> dict:
    return json.loads(caminho.read_text(encoding="utf-8"))


def aguardar_arquivo(caminho: Path, processo: subprocess.Popen, limite: float) -> dict:
    while not caminho.exists():
        if processo.poll() is not None:
            raise RuntimeError("O servidor encerrou antes de abrir a porta. Consulte o log.")
        if time.perf_counter() >= limite:
            raise TimeoutError("O servidor não ficou pronto a tempo.")
        time.sleep(0.02)
    return ler_json(caminho)


def encerrar_processos(processos: list[subprocess.Popen]) -> None:
    for processo in processos:
        if processo.poll() is None:
            processo.terminate()
    for processo in processos:
        try:
            processo.wait(timeout=5)
        except subprocess.TimeoutExpired:
            processo.kill()
            processo.wait()


def executar_cenario(args: argparse.Namespace, cenario: int, clientes: int) -> dict:
    processos: list[subprocess.Popen] = []
    pasta_logs = args.saida.parent / "logs" / f"cenario_{cenario:02d}_{clientes}_clientes"
    pasta_logs.mkdir(parents=True, exist_ok=True)
    # Os relatórios JSON e logs também permitem auditar as somas após a execução.
    with tempfile.TemporaryDirectory(prefix="sd_rodada_") as pasta, ExitStack() as arquivos:
        temporarios = Path(pasta)
        pronto = temporarios / "pronto.json"
        resultado_servidor = pasta_logs / "servidor.json"
        prazo = time.perf_counter() + args.timeout

        def iniciar(script: str, parametros: list[str], log: Path) -> subprocess.Popen:
            arquivo = arquivos.enter_context(log.open("w", encoding="utf-8"))
            ambiente = os.environ.copy()
            ambiente["PYTHONIOENCODING"] = "utf-8"
            processo = subprocess.Popen(
                [sys.executable, "-u", str(RAIZ / script), *parametros],
                cwd=RAIZ, stdout=arquivo, stderr=subprocess.STDOUT, env=ambiente,
            )
            processos.append(processo)
            return processo

        comuns = ["--elementos", str(args.elementos), "--bloco", str(args.bloco),
                  "--timeout", str(args.timeout)]
        try:
            servidor = iniciar("servidor.py", [
                "--host", "127.0.0.1", "--porta", "0", "--clientes", str(clientes),
                "--pronto-json", str(pronto), "--resultado-json", str(resultado_servidor),
                *comuns,
            ], pasta_logs / "servidor.log")
            endereco = aguardar_arquivo(pronto, servidor, prazo)
            relatorios = []
            for identificador in range(1, clientes + 1):
                relatorio = pasta_logs / f"cliente_{identificador:02d}.json"
                relatorios.append(relatorio)
                iniciar("cliente.py", [
                    "--host", "127.0.0.1", "--porta", str(endereco["porta"]),
                    "--id", str(identificador),
                    "--seed", str(args.seed + clientes * 1000 + identificador),
                    "--resultado-json", str(relatorio), *comuns,
                ], pasta_logs / f"cliente_{identificador:02d}.log")

            # Todos os clientes já estão em execução antes desta espera.
            pendentes = list(processos)
            while pendentes:
                for processo in list(pendentes):
                    codigo = processo.poll()
                    if codigo is not None:
                        if codigo != 0:
                            raise RuntimeError(f"Processo PID {processo.pid} falhou (código {codigo}).")
                        pendentes.remove(processo)
                if pendentes:
                    if time.perf_counter() >= prazo:
                        raise TimeoutError("Tempo máximo da rodada excedido.")
                    time.sleep(0.02)

            resumo = ler_json(resultado_servidor)
            individuais = [ler_json(caminho) for caminho in relatorios]
            soma_esperada = sum(item["soma_esperada"] for item in individuais)
            if (
                resumo["clientes"] != clientes
                or resumo["numeros_por_cliente"] != args.elementos
                or resumo["total_numeros"] != clientes * args.elementos
                or resumo["soma_total"] != soma_esperada
                or len(resumo["clientes_resultados"]) != clientes
                or {item["cliente_id"] for item in resumo["clientes_resultados"]}
                != set(range(1, clientes + 1))
            ):
                raise RuntimeError("A quantidade ou soma global não confere.")
            por_id = {item["cliente_id"]: item for item in resumo["clientes_resultados"]}
            for identificador, item in enumerate(individuais, start=1):
                resposta = item["resposta"]
                if (
                    not item["validado"]
                    or item["cliente_id"] != identificador
                    or item["elementos"] != args.elementos
                    or item["soma_esperada"] != por_id[identificador]["soma"]
                    or resposta["soma_total"] != soma_esperada
                    or resposta["clientes"] != clientes
                    or resposta["tempo_servidor_s"] != resumo["tempo_servidor_s"]
                ):
                    raise RuntimeError(f"A conferência do cliente {identificador} falhou.")
            return {
                "cenario": cenario, "clientes": clientes,
                "numeros_por_cliente": args.elementos,
                "total_numeros": resumo["total_numeros"], "soma_total": resumo["soma_total"],
                "tempo_servidor_s": resumo["tempo_servidor_s"],
                "validado": True, "seed_base": args.seed,
            }
        except Exception as erro:
            raise RuntimeError(f"Cenário com {clientes} cliente(s): {erro} Logs: {pasta_logs}") from erro
        finally:
            encerrar_processos(processos)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clientes", nargs="+", type=inteiro_positivo, default=[1, 4, 8, 16])
    parser.add_argument("--elementos", type=inteiro_positivo, default=ELEMENTOS_PADRAO)
    parser.add_argument("--bloco", type=inteiro_positivo, default=BLOCO_PADRAO)
    parser.add_argument("--timeout", type=segundos_positivos, default=180.0,
                        help="Limite por cenário, incluindo geração e início dos processos")
    parser.add_argument("--seed", type=int, default=20261019)
    parser.add_argument("--saida", type=Path, default=RAIZ / "resultados" / "resultados.csv")
    args = parser.parse_args()
    args.saida = args.saida.resolve()
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    salvar_json(args.saida.with_suffix(".ambiente.json"), {
        "data_utc": datetime.now(timezone.utc).isoformat(), "python": sys.version,
        "executavel": sys.executable, "sistema": platform.platform(),
        "processador": platform.processor(), "cpus_logicas": os.cpu_count(),
        "clientes": args.clientes, "elementos": args.elementos,
        "bloco": args.bloco, "seed_base": args.seed, "timeout_s": args.timeout,
        "host": "127.0.0.1", "repeticoes_por_cenario": 1,
    })
    print("Clientes | Total de números | Soma total  | Tempo servidor (s) | Conferência", flush=True)
    print("---------|------------------|-------------|--------------------|------------", flush=True)
    try:
        with args.saida.open("w", newline="", encoding="utf-8") as arquivo:
            escritor = csv.DictWriter(arquivo, fieldnames=CAMPOS)
            escritor.writeheader()
            arquivo.flush()
            for cenario, clientes in enumerate(args.clientes, start=1):
                resultado = executar_cenario(args, cenario, clientes)
                escritor.writerow(resultado)
                arquivo.flush()
                print(
                    f"{clientes:8d} | {resultado['total_numeros']:16d} | "
                    f"{resultado['soma_total']:11d} | "
                    f"{resultado['tempo_servidor_s']:18.6f} | OK", flush=True,
                )
    except KeyboardInterrupt:
        print("Benchmark interrompido; processos encerrados.")
        return 130
    except Exception as erro:
        print(f"ERRO: {erro}", file=sys.stderr, flush=True)
        return 1
    print(f"Resultados reais salvos em: {args.saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

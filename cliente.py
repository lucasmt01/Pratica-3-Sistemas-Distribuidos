"""Processo cliente: gera os dados, aguarda a largada e confere a soma."""

import argparse
from array import array
from pathlib import Path
import random
import socket
import time

from protocolo import (
    BLOCO_PADRAO, ELEMENTOS_PADRAO, VERSAO, ErroProtocolo,
    codificar_numeros, enviar_json, inteiro_positivo, receber_json,
    salvar_json, segundos_positivos,
)


def executar(args: argparse.Namespace) -> dict:
    gerador = random.Random(args.seed)
    inicio_geracao = time.perf_counter()
    numeros = array("H", (gerador.randint(0, 1000) for _ in range(args.elementos)))
    soma_esperada = sum(numeros)
    tempo_geracao = time.perf_counter() - inicio_geracao
    print(
        f"Cliente {args.id:02d}: {len(numeros):,} números gerados em {tempo_geracao:.6f} s; "
        f"soma esperada = {soma_esperada}. Aguardando liberação.", flush=True,
    )
    with socket.create_connection((args.host, args.porta), timeout=args.timeout) as conexao:
        conexao.settimeout(args.timeout)
        enviar_json(conexao, {
            "tipo": "pronto", "versao": VERSAO,
            "cliente_id": args.id, "elementos": args.elementos,
        })
        liberacao = receber_json(conexao)
        if liberacao != {"tipo": "iniciar", "versao": VERSAO}:
            raise ErroProtocolo("Liberação inválida do servidor.")
        for inicio in range(0, len(numeros), args.bloco):
            conexao.sendall(codificar_numeros(numeros[inicio:inicio + args.bloco]))
        resposta = receber_json(conexao)

    campos_inteiros = ("cliente_id", "clientes", "elementos", "soma_cliente",
                      "soma_total", "total_numeros")
    if any(type(resposta.get(campo)) is not int for campo in campos_inteiros):
        raise ErroProtocolo("Resultado incompleto ou com tipos inválidos.")
    if (
        resposta.get("tipo") != "resultado"
        or resposta["cliente_id"] != args.id
        or resposta["elementos"] != args.elementos
        or resposta["soma_cliente"] != soma_esperada
        or resposta["clientes"] < 1
        or resposta["total_numeros"] != args.elementos * resposta["clientes"]
        or not soma_esperada <= resposta["soma_total"] <= resposta["total_numeros"] * 1000
        or (resposta["clientes"] == 1 and resposta["soma_total"] != soma_esperada)
        or type(resposta.get("tempo_servidor_s")) not in (int, float)
        or not 0 <= resposta["tempo_servidor_s"] < float("inf")
    ):
        raise ErroProtocolo(f"Resultado incompatível com os dados enviados: {resposta}")
    resultado = {
        "cliente_id": args.id, "elementos": len(numeros), "seed": args.seed,
        "soma_esperada": soma_esperada, "validado": True,
        "tempo_geracao_s": tempo_geracao, "resposta": resposta,
    }
    if args.resultado_json:
        salvar_json(args.resultado_json, resultado)
    print(
        f"Cliente {args.id:02d}: OK, soma recebida = {resposta['soma_cliente']}; "
        f"soma da rodada = {resposta['soma_total']}; "
        f"tempo do servidor = {resposta['tempo_servidor_s']:.6f} s.", flush=True,
    )
    return resultado


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--porta", type=inteiro_positivo, default=5000)
    parser.add_argument("--id", type=inteiro_positivo, default=1)
    parser.add_argument("--elementos", type=inteiro_positivo, default=ELEMENTOS_PADRAO)
    parser.add_argument("--bloco", type=inteiro_positivo, default=BLOCO_PADRAO)
    parser.add_argument("--seed", type=int, default=None, help="Semente opcional para reproduzir dados")
    parser.add_argument("--timeout", type=segundos_positivos, default=180.0)
    parser.add_argument("--resultado-json", type=Path)
    args = parser.parse_args()
    if args.porta > 65535:
        parser.error("A porta deve estar entre 1 e 65535.")
    try:
        executar(args)
    except KeyboardInterrupt:
        print("Cliente interrompido; conexão encerrada.")
        return 130
    except Exception as erro:
        print(f"ERRO no cliente {args.id}: {erro}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

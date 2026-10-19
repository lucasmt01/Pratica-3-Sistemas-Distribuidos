# Cliente-Servidor com Multithreading

Projeto desenvolvido em Python para demonstrar a comunicação entre processos clientes e um servidor utilizando sockets TCP e multithreading.

O sistema permite que vários clientes enviem números simultaneamente para um servidor, responsável por calcular as somas e retornar os resultados.

## Funcionamento

Cada cliente gera **1.000.000 de números aleatórios entre 0 e 1000** e os envia ao servidor.

O servidor utiliza uma thread para atender cada cliente, permitindo que várias conexões sejam processadas ao mesmo tempo.

O processo funciona da seguinte maneira:

1. O servidor é iniciado e aguarda as conexões.
2. Os clientes geram seus números e se conectam ao servidor.
3. Após todos estarem prontos, o envio dos números começa.
4. O servidor recebe os dados e calcula as somas.
5. Os resultados são retornados aos clientes e o tempo total de processamento é registrado.

Foram realizados experimentos com **1, 4, 8 e 16 clientes simultâneos**.

## Tecnologias utilizadas

- Python 3
- Sockets TCP para comunicação entre processos
- Threads para atendimento simultâneo dos clientes
- Subprocessos para execução dos experimentos

O projeto utiliza apenas bibliotecas padrão do Python.

## Estrutura do projeto

- `servidor.py` — recebe as conexões e realiza as somas.
- `cliente.py` — gera os números e os envia ao servidor.
- `benchmark.py` — executa automaticamente os experimentos.
- `protocolo.py` — organiza a comunicação entre cliente e servidor.
- `tests/` — contém os testes automatizados.
- `resultados/` — armazena os tempos e registros das execuções.

## Como executar

É necessário ter o Python 3.10 ou superior instalado.

Com o terminal aberto na pasta do projeto, execute:

```bash
py -3 benchmark.py
```

Esse comando executa automaticamente os quatro experimentos, iniciando o servidor e os clientes necessários para cada cenário.

Para executar um teste com menos números:

```bash
py -3 benchmark.py --elementos 10003
```

Também é possível executar o servidor e o cliente separadamente.

**Terminal 1 — Servidor**

```bash
py -3 servidor.py --host 127.0.0.1 --porta 5000 --clientes 1
```

**Terminal 2 — Cliente**

```bash
py -3 cliente.py --host 127.0.0.1 --porta 5000 --id 1
```

Para executar os testes automatizados:

```bash
py -3 -m unittest discover -s tests -v
```

## Resultados

Os experimentos foram executados com 1 milhão de números por cliente, obtendo os seguintes resultados:

| Clientes | Números processados | Tempo no servidor |
|---:|---:|---:|
| 1 | 1.000.000 | 0,106454 s |
| 4 | 4.000.000 | 0,433015 s |
| 8 | 8.000.000 | 0,826133 s |
| 16 | 16.000.000 | 1,637667 s |

Todas as somas foram verificadas e corresponderam aos valores esperados.

O tempo de execução aumentou conforme a quantidade de clientes, já que cada novo cliente adiciona mais 1 milhão de números ao processamento.

Os tempos foram medidos no servidor e incluem a comunicação e o processamento dos dados. Os resultados podem variar conforme o computador e as condições de execução.

Os registros completos estão disponíveis na pasta `resultados/`.

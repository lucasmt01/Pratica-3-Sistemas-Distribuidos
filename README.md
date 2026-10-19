# Sistemas Distribuídos: TCP e multithreading em Python

Atividade prática de Sistemas Distribuidos: cada processo cliente envia
**1.000.000 de inteiros aleatórios entre 0 e 1000**, inclusive. Um processo
servidor atende cada cliente em uma thread, soma os dados e devolve tanto a
soma individual quanto a soma de toda a rodada.

O benchmark executa **1, 4, 8 e 16 clientes simultâneos**, com um servidor novo
em cada cenário. Todos os resultados incluídos neste projeto vieram de
execuções reais em TCP local, com conferência das somas.

## Requisitos e execução no Windows 11

Use Python **3.10 ou superior** no terminal do VS Code ou no PowerShell.
Não há dependências externas nem necessidade de instalar pacotes. O arquivo
`requirements.txt` documenta essa decisão. Entre na pasta do projeto:

```powershell
cd "C:\Users\lucas\OneDrive\Documentos\UFC\SD\Pratica3"
py -3 --version
py -3 benchmark.py
```

O último comando executa os quatro cenários completos automaticamente. Não é
necessário abrir terminais adicionais. O programa imprime uma tabela, salva
`resultados/resultados.csv` e encerra todos os processos iniciados por ele.
A duração de todo o comando também inclui geração dos números e inicialização
dos processos, portanto será maior que a soma dos tempos medidos no servidor.

Para um teste rápido com os mesmos quatro cenários:

```powershell
py -3 benchmark.py --elementos 10003 --bloco 257 --saida resultados/teste_menor/resultados.csv
```

Para escolher os cenários ou aumentar o limite de tempo de cada um:

```powershell
py -3 benchmark.py --clientes 1 4 --elementos 1000000 --timeout 300 --saida resultados/outra_execucao/resultados.csv
```

Cada execução sobrescreve o CSV e os logs correspondentes ao caminho escolhido.
Use outra pasta em `--saida` para preservar uma medição anterior. O caminho
padrão é relativo à localização de `benchmark.py`; um caminho informado em
`--saida` é relativo ao diretório do terminal.

### Execução manual: um servidor e um cliente

No primeiro terminal:

```powershell
py -3 servidor.py --host 127.0.0.1 --porta 5000 --clientes 1
```

No segundo terminal, após o servidor informar que está aguardando:

```powershell
py -3 cliente.py --host 127.0.0.1 --porta 5000 --id 1
```

O servidor termina após uma rodada. Reinicie-o para outra rodada. Se alterar
`--elementos`, informe o mesmo valor nos dois comandos. Para vários clientes
manuais, use IDs distintos de 1 até `--clientes` e inicie todos antes do timeout.
O benchmark cuida dessas tarefas automaticamente. A porta do servidor é
configurável; `--porta 0` solicita uma porta livre ao sistema operacional.
`--help` exibe todas as opções de cada script.

## Organização

```text
.
├── servidor.py              # Processo servidor e uma thread por conexão
├── cliente.py               # Geração, envio em blocos e validação individual
├── benchmark.py             # Processos, rodadas, conferência global e CSV
├── protocolo.py             # Leitura completa, JSON e inteiros binários
├── tests/
│   ├── test_protocolo.py
│   └── test_integracao.py
├── resultados/
│   ├── resultados.csv
│   ├── resultados.ambiente.json
│   ├── logs/                # Logs e relatórios JSON por cenário/processo
│   └── teste_menor/         # Execução real com 10.003 números por cliente
├── ROTEIRO_VIDEO.md
├── requirements.txt
└── .gitignore
```

## Arquitetura e multithreading

`benchmark.py` usa `subprocess.Popen` para abrir um **processo servidor separado**
e N **processos clientes separados**, todos usando o mesmo interpretador Python
do benchmark (`sys.executable`). Ele inicia todos os clientes antes de aguardar
seus términos. O sistema operacional escalona esses processos concorrentemente.

O servidor usa `socket`, `accept()` e `threading.Thread`. Para cada conexão,
cria uma thread dedicada, que recebe e soma os números daquele cliente.
A thread principal aceita as conexões e coordena o encerramento da rodada.
As threads ficam no mesmo processo servidor e compartilham os resultados.

Uma `threading.Barrier` reúne as N threads e a thread principal do servidor.
Cada cliente primeiro gera seus dados e calcula sua soma esperada. Só então
abre a conexão e envia a identificação `pronto`. A thread que o atende entra
na barreira após validar essa mensagem.

Assim, o cliente mais rápido espera o mais lento concluir sua geração. Quando
todos estão prontos, a ação da barreira registra o instante inicial e libera
as threads, que enviam a mensagem `iniciar`. Nenhum cliente envia os números
antes dessa autorização. Existe uma pequena diferença de escalonamento entre
as liberações efetivas das threads; ela faz parte do tempo medido.

As somas parciais são variáveis locais de cada thread. Um `threading.Lock`
protege a atualização da soma global, do total de números, dos IDs e dos
resultados compartilhados. A última thread a concluir registra o instante
final. Um `threading.Event` permite às demais aguardarem essa conclusão antes
de responder: todos os clientes recebem a mesma soma global e o mesmo tempo.

## Protocolo TCP e transmissão dos números

TCP transporta um fluxo de bytes, sem preservar as fronteiras dos envios.
Por isso, o código não presume que um `recv()` receba uma mensagem completa.
`receber_exatamente()` repete `recv_into()` até preencher todo o buffer e
detecta encerramento prematuro da conexão. Os envios usam `sendall()`.

O protocolo tem três etapas:

1. **Preparação:** o cliente envia JSON com versão, ID e quantidade de números.
   Mensagens JSON usam um cabeçalho de 4 bytes, sem sinal e big endian, com o
   tamanho do corpo UTF-8. O tamanho do JSON é limitado a 65.536 bytes.
2. **Transmissão:** após receber o JSON `iniciar`, o cliente envia exatamente
   `elementos × 2` bytes. Cada inteiro ocupa 2 bytes sem sinal (`uint16`), em
   ordem de rede, big endian. Não há um JSON nem uma chamada de rede por número.
3. **Resposta:** após concluir toda a rodada, o servidor envia JSON com soma
   individual, soma global, contagens e tempo do servidor. A conexão é fechada.

O bloco padrão contém 32.768 números, ou 65.536 bytes. O último bloco pode ser
menor; não há perda de elementos quando a quantidade não é múltipla do bloco.
Os blocos são apenas uma estratégia de leitura e envio: as suas fronteiras
não precisam coincidir na rede. O servidor sabe quantos bytes esperar pela
quantidade configurada e validada na preparação.

Cada cliente mantém seus dados em `array('H')`, aproximadamente 2 MB para um
milhão de números, para gerar tudo antes da largada. O envio converte apenas
um bloco por vez para big endian. O servidor mantém buffers por bloco,
converte os inteiros, verifica o intervalo de 0 a 1000 e acumula com `sum()`.
Os acumuladores são inteiros Python, que comportam a soma dos 16 milhões de
valores sem estouro de um inteiro de 32 bits.

O servidor não recebe a soma esperada do cliente. Ele precisa calcular a soma
a partir dos números transmitidos. Cada cliente compara a soma individual
retornada com a soma calculada antes do envio. Um cliente isolado não conhece
os números dos outros; por isso a conferência exata da soma global é feita
pelo benchmark, somando as expectativas de **todos** os processos clientes.

O benchmark usa sementes reproduzíveis: `seed_base + clientes * 1000 + id`.
A semente base padrão é `20261019`. As sementes e somas individuais ficam nos
relatórios JSON. Sementes fixas permitem repetir os dados na mesma versão de
Python; os tempos continuam sendo medidos em cada execução. O cliente manual
sem `--seed` usa a inicialização padrão de `random.Random`.

## O que o tempo mede

A medição principal acontece exclusivamente no servidor, com
`time.perf_counter()`:

```text
início = instante da ação da barreira, antes da liberação das threads
fim    = instante em que a última soma parcial é incorporada à soma global
tempo_servidor_s = fim - início
```

Esse intervalo inclui mensagens de largada, escalonamento das threads e dos
clientes, preparação dos blocos binários nos clientes, comunicação TCP,
recebimento, conversão, validação dos valores, somas e sincronização no servidor.
**É tempo decorrido de comunicação e processamento, e não tempo puro de CPU.**

Ficam fora do intervalo: inicialização dos processos, geração dos números,
cálculo das somas esperadas nos clientes, conexão e identificação inicial,
envio das respostas finais, gravação dos resultados e encerramento dos
processos. O tempo de geração que aparece no log do cliente é uma informação
separada e não é o resultado principal do experimento.

## Resultados reais registrados

Execução em **19/10/2026**, no Windows 11, CPython 3.13.5 de 64 bits,
16 CPUs lógicas, conexão local `127.0.0.1`, blocos de 32.768 números e
uma execução por cenário. O arquivo `resultados.ambiente.json` contém os
metadados da máquina, a data em UTC e a configuração usada.

| Clientes | Total de números | Soma total | Tempo no servidor (s) | Conferência |
|---:|---:|---:|---:|:---:|
| 1 | 1.000.000 | 500.155.829 | 0,106454 | OK |
| 4 | 4.000.000 | 2.000.828.557 | 0,433015 | OK |
| 8 | 8.000.000 | 3.999.357.662 | 0,826133 | OK |
| 16 | 16.000.000 | 8.000.896.151 | 1,637667 | OK |

O CSV preserva os tempos com mais casas decimais; a tabela está arredondada.
Todas as contagens foram verificadas. As 29 somas individuais conferiram e
a soma global de cada rodada corresponde à soma das expectativas dos clientes.
Os relatórios de todos os participantes contêm o mesmo resultado global.

Os tempos cresceram aproximadamente com a carga total nesta execução.
Com 16 clientes também há 16 vezes mais números que com um cliente; portanto,
essa tabela **não mede aceleração sobre uma carga fixa**. A taxa observada
fica próxima de 9 a 10 milhões de números por segundo, neste ambiente.
Uma única medição por cenário não permite concluir significância estatística.
Outras máquinas e novas execuções produzirão tempos diferentes.

Os testes menores reais, com 10.003 números por cliente e blocos de 257,
também passaram nos quatro cenários. Seus resultados ficam separados em
`resultados/teste_menor/`.

## Validação e tratamento de falhas

Para verificar a sintaxe e executar os testes automatizados:

```powershell
py -3 -m compileall -q protocolo.py servidor.py cliente.py benchmark.py tests
py -3 -m unittest discover -s tests -v
```

A suíte verifica fragmentação de leituras TCP, mensagens inválidas, ordem dos
bytes, desconexão antecipada, limites 0 e 1000, valor fora do intervalo,
quantidade incompatível, ID duplicado, falta de cliente e timeout após a
largada. Também verifica que a largada e a resposta aguardam todos os
participantes, além de executar um benchmark menor com processos reais.

Sockets possuem timeout. Uma falha no servidor aborta a barreira, sinaliza as
threads em espera e interrompe os sockets para desbloquear leituras. As
threads são reunidas com `join()` antes de encerrar. Erros retornam código de
saída diferente de zero.

O benchmark tem um prazo por cenário que inclui a preparação dos processos.
Se um processo falha, o prazo expira ou o usuário pressiona `Ctrl+C`, o bloco
`finally` encerra os processos restantes e aguarda sua saída, usando `kill()`
se necessário. A execução não usa `shell=True` nem abre janelas extras.
No servidor manual, o timeout limita a espera por conexões, pela barreira e
por operações de socket; no benchmark há também o prazo total da rodada.

O CSV recebe uma linha somente após o sucesso e a conferência de toda a
rodada. Em caso de falha, o programa aponta a pasta dos logs; resultados de
cenários já concluídos ficam preservados. Não há tempos simulados nem
preenchimento de valores para cenários que falharam.

## Limitações e interpretação

- A execução registrada usa TCP em loopback. Não mede latência, largura de
  banda ou perdas de uma rede entre máquinas físicas distintas. O servidor
  também pode usar outro endereço IPv4 em `--host`, mas o benchmark fornecido
  inicia todos os processos na máquina local.
- Servidor e clientes disputam CPU, memória e escalonamento na mesma máquina.
  A geração ocorre antes da medição; envio, conversões e concorrência ainda
  influenciam o intervalo registrado. A carga do sistema e o tamanho dos
  blocos também afetam o resultado.
- No CPython tradicional com GIL, apenas uma thread por processo executa código
  Python por vez. Esperas de socket permitem sobreposição de I/O, mas criar
  mais threads não garante aceleração das somas e validações. Cada cliente é
  outro processo e tem seu próprio interpretador; no servidor, as threads
  compartilham o mesmo GIL. Não se pretende demonstrar paralelismo de CPU das
  threads do servidor.
- Cada cenário tem uma única medição, sem aquecimento e sem médias ou
  intervalos de confiança. Para uma análise estatística, repita o benchmark
  em pastas distintas, mantendo máquina e configuração comparáveis.
- É um protocolo didático em uma rede confiável, sem autenticação, criptografia
  ou reconexão automática. Uma falha invalida a rodada, que deve ser repetida.

## Entrega

A pasta pode ser publicada em um repositório GitHub ou compactada em ZIP.
Inclua os scripts, testes, documentação e resultados reais; caches, ambientes
virtuais e arquivos temporários são ignorados pelo `.gitignore`.
`ROTEIRO_VIDEO.md` traz uma sequência sugerida para gravar a apresentação.
A gravação do vídeo deve ser feita pelo aluno.

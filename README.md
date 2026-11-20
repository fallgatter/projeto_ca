# Quadrilátero Central de Curitiba

Microssimulação SUMO do cenário de referência do projeto de Ciências do Ambiente da UTFPR. A execução mensal combina velocidades medianas do **TomTom Traffic Stats**, proporções de viagens do **TomTom O/D Analysis** e GPS, itinerários e paradas da **URBS/C3SL**. O Dash exibe a reprodução do tráfego e os indicadores do SUMO no Quadrilátero Central de Curitiba.

## Passo a passo no Windows

### 1. Preparar o ambiente

Abra o PowerShell na raiz de `projeto_ca`, onde ficam este README e o arquivo `requirements.txt`. Em uma instalação nova, use Python 3.11 ou posterior e prepare o ambiente:

```powershell
python -m venv .venv
$python = '.\.venv\Scripts\python.exe'
& $python -m pip install -r requirements.txt
```

Nesta máquina, você também pode usar o Python 3.15 já instalado com as dependências em `.deps`:

```powershell
$env:PYTHONPATH = '.deps'
$python = "$env:USERPROFILE\AppData\Local\Python\pythoncore-3.15-64\python.exe"
```

Para gerar simulações, instale o SUMO e coloque `sumo` e `netconvert` no `PATH`, ou configure `SUMO_HOME` com a pasta de instalação. Confirme com `sumo --version` se estiver usando o `PATH`. Mantenha `Sumo-CAmbiente-main` como pasta irmã, pois ela fornece o mapa OSM e o relatório histórico do modo offline. Para apontar outra localização, use `& $python -m ca --reference 'C:\caminho\Sumo-CAmbiente-main' run --offline`. [Instalação oficial do SUMO](https://sumo.dlr.de/docs/Installing/index.html)

### 2. Obter e configurar as chaves

| Variável no `.env` | Onde obter | Quando usar |
| --- | --- | --- |
| `TOMTOM_STATS_API_KEY` | Entre no TomTom MOVE com e-mail profissional ou institucional e copie a chave de API do menu do MOVE. Verifique o acesso a **Traffic Stats** e, para gerar a matriz, a **O/D Analysis**. [Portal TomTom MOVE](https://move.tomtom.com/login) · [Cadastro](https://docs.tomtom.com/move-portal/guides/signing-in) · [Chave do Traffic Stats](https://docs.tomtom.com/traffic-stats/documentation/api/introduction) | `run` mensal com dados do MOVE. Se a conta só tiver Traffic Stats, use `--sem-od`. |
| `TOMTOM_API_KEY` | Em MyTomTom, abra **API & SDK Keys** e copie a chave de um projeto com acesso ao serviço Traffic. [MyTomTom](https://my.tomtom.com/keys) · [Guia oficial de chaves](https://docs.tomtom.com/platform/documentation/my-tomtom/how-to-get-a-tomtom-api-key) | Captura de tráfego ao vivo com `tomtom`. |

Se ainda não tem um arquivo `.env`, crie-o a partir do modelo e abra-o para editar:

```powershell
if (-not (Test-Path -LiteralPath '.env')) { Copy-Item '.env.example' '.env' }
notepad .env
```

Cole cada chave ao lado do nome correspondente. Guarde os valores no `.env` local. O Dash com resultados salvos, os replays e o modo offline funcionam sem chave. O projeto lê os arquivos públicos da URBS/C3SL e o mapa OSM local. [Acervo aberto da URBS/C3SL](https://dadosabertos.c3sl.ufpr.br/curitibaurbs/)

### 3. Abrir os resultados salvos

```powershell
& $python -m ca serve --port 8052
```

Abra o [Dash local](http://127.0.0.1:8052/) e mantenha o terminal aberto. No seletor do topo, escolha **Manhã · 06:30–09:00** ou **Noite · 17:00–19:00**. Com os resultados do projeto em `runs/`, **Como está hoje** mostra a Onda Verde fixa à esquerda. À direita, **Melhor resultado** mostra o replay com MQTT nos oito sinais da Kennedy que mais reduziu o atraso médio de carros e ônibus em relação ao seu par fixo naquele pico. A barra de reprodução controla os dois mapas, e os indicadores de cada mapa resumem o pico completo.

### 4. Gerar uma demanda de referência

Se a demanda já estiver em uma execução fixa concluída em `runs/`, use a pasta correspondente como origem no passo seguinte. Para gerar uma nova, escolha um dos comandos:

```powershell
# Cenário mensal usando a chave MOVE
& $python -m ca run --control fixed --no-dashboard

# Cenário usando o relatório histórico e o cache da URBS
& $python -m ca urbs --through 2024-08-02
& $python -m ca run --offline --control fixed --no-dashboard
```

O comando informa o ID de cada execução ao concluir. Também é possível localizar os IDs com `Get-ChildItem runs -Directory | Select-Object -ExpandProperty Name`. No fluxo mensal, use `--month AAAA-MM` para escolher um mês civil completo disponível na conta.

### 5. Gerar o antes e depois com MQTT

1. Instale o Mosquitto, coloque seu executável no `PATH` e inicie o broker na raiz do projeto. Mantenha esse terminal aberto. [Instaladores oficiais do Mosquitto](https://mosquitto.org/download/)

   ```powershell
   mosquitto -c config/mosquitto.conf
   ```

2. Em outro terminal na raiz do projeto, configure `$python` como no passo 1. O exemplo usa uma execução de julho de 2026 salva com o projeto. Substitua `$origem` pelo ID escolhido no passo 4 se tiver gerado outra demanda. Use nomes novos em cada repetição. Se a origem já tiver a Onda Verde, omita `--signals $plano` nos dois comandos para herdar o plano.

   ```powershell
   $origem = 'mensal-2026-07-manha-20261119-235229-202742'
   $plano = 'config/signals/onda-verde-kennedy.add.xml'
   & $python -m ca replay $origem --name demonstracao-manha-fixo --control fixed --signals $plano
   & $python -m ca replay $origem --name demonstracao-manha-mqtt --control mqtt-adaptive --signals $plano --mqtt 127.0.0.1:1883
   ```

3. Quando os dois replays terminarem, volte ao painel ou abra-o como no passo 3. O painel avalia o novo par junto aos resultados salvos. Os comandos acima gravam as posições a cada 2 s. Acrescente `--summary-only` aos dois comandos para usar as posições dos blocos de 30 s.

### Como o projeto funciona

O OSM fornece a malha viária. O TomTom fornece velocidades e distribuição de viagens, e a URBS fornece trajetos e GPS para representar o transporte coletivo. A demanda de carros é sintética e o projeto inclui pedestres e bicicletas. O SUMO simula o tráfego passo a passo. O TraCI coleta posições, filas, viagens e emissões, e grava os resultados em `runs/`.

No modo fixo, o SUMO segue os programas semafóricos do cenário. No modo MQTT, o simulador publica observações de fila, espaço nas saídas e presença de BRT. O controlador devolve ajustes de verde pelo broker, e o TraCI os aplica dentro dos limites de cada fase. A leitura seguinte mede o efeito do ajuste. Na Kennedy, o verde longo pode terminar até 4 s antes ou depois da referência da Onda Verde. O Dash pareia os replays pelos arquivos de entrada e mostra a reprodução, os indicadores e a diferença entre os cenários. [Método e resultados](docs/quadrilatero-mqtt.md)

## Executar com o relatório TomTom local

```powershell
& $python -m ca run --offline
```

O modo offline usa o GeoJSON incluído no projeto original, com velocidades médias de **1 e 2 de agosto de 2024** agregadas ao longo do dia. Assim como no original, a relação entre o limite da via e a velocidade média aumenta a probabilidade de gerar partidas nas vias mais lentas. Os mesmos pesos são usados nos dois picos do SUMO, com o volume configurado para cada horário.

O comando busca no cache local um dia útil da URBS com itinerários, paradas e GPS nos dois picos. Ele prioriza as datas do relatório e usa o dia útil mais recente disponível quando precisar recorrer a outra data. Use `--urbs-date AAAA-MM-DD` para escolher um dia do cache. Em uma instalação nova, `python -m ca urbs --through 2024-08-02` prepara os arquivos históricos. As datas da TomTom e da URBS ficam registradas nos metadados.

## Executar o cenário mensal

Para criar uma conta no **TomTom MOVE**, use um e-mail institucional. O cadastro deste projeto foi concluído com um e-mail institucional após o portal recusar o endereço pessoal. [Guia de cadastro no MOVE](https://docs.tomtom.com/move-portal/guides/signing-in)

Preencha `TOMTOM_STATS_API_KEY` no `.env` com a chave do **TomTom MOVE**. A mesma chave atende ao **Traffic Stats** e ao **O/D Analysis** quando os dois produtos estão habilitados na conta. No PowerShell:

```powershell
& $python -m ca run
```

O comando sem subcomando (`python -m ca`) também inicia esse fluxo. Uma nova análise pode consumir a cota do MOVE. O projeto reaproveita os resultados locais e retoma análises já abertas no portal. A chave `TOMTOM_API_KEY` atende às capturas do modo **TomTom ao vivo**. [Traffic Stats](https://docs.tomtom.com/traffic-stats/documentation/api/introduction) · [O/D Analysis](https://docs.tomtom.com/od-analysis/documentation/v2/user-guide/introduction)

O padrão é o último mês civil completo. Se o MOVE indicar um período restrito, use `--month AAAA-MM` para selecionar um mês permitido nos dois produtos. Para a janela de julho de 2026 habilitada na conta do projeto, use `python -m ca run --month 2026-07`. O Dash identifica o mês usado. A opção `--sem-od` usa as medianas do Traffic Stats com a distribuição de viagens estimada pela malha.

Para usar um relatório exportado pelo MOVE, forneça um **GeoJSON de Área completa**, em quilômetros, no fuso `America/Sao_Paulo`. Configure o mês civil selecionado e dois conjuntos de horários de segunda a sexta, **06:30–09:00** e **17:00–19:00**, sobre o recorte WGS84 de [config/curitiba.json](config/curitiba.json).

```powershell
& $python -m ca run --traffic-stats .\relatorio.geojson
```

O cenário usa os picos de **06h30 a 09h** e **17h a 19h**. A URBS fornece os trajetos dos ônibus a partir do GPS e dos itinerários de um dia útil do mesmo mês. O comando procura o dia útil mais recente com GPS nos dois horários. Use `--urbs-date AAAA-MM-DD` para escolher outro.

Os carros percorrem viagens sintéticas no SUMO. A matriz O/D orienta o sorteio dos pares de zonas por pico, distinguindo viagens internas, entradas, saídas e travessias do recorte. O código encaixa esses pares na malha e registra no painel a proporção que conseguiu representar. Nos trechos cobertos pelo Traffic Stats, as medianas limitam a velocidade desejada dos carros. Semáforos, filas e interações entre veículos determinam a velocidade e o tempo de viagem simulados. As taxas de **2.300 partidas/h de manhã** e **2.700 à tarde** são parâmetros do cenário. A matriz O/D fornece proporções de uma amostra e as contagens locais permitem calibrar e validar o volume total.

## Acompanhar no Dash

Quando o terminal informar que o Dash iniciou, abra [o painel local](http://127.0.0.1:8050). Compare **Como está hoje** e **Melhor resultado** nos mapas lado a lado. Eles acumulam desde o início do pico o tempo que carros e ônibus passam em cada célula de cerca de 100 m. Um veículo por um minuto equivale a um veículo-minuto. Os pontos escuros marcam os **Semáforos** do SUMO.

Os dois mapas ocupam a área principal da janela. Use a roda do mouse ou os botões **+** e **−** para ampliar ou reduzir. Arraste para navegar pelo recorte e use o ícone de redefinir os eixos para voltar à vista inicial. **Tela cheia** abre a interface em tela cheia do navegador. Cada mapa mostra seus quatro indicadores no topo. Os ícones **i** mostram explicações ao passar o mouse ou receber foco pelo teclado.

Use **Velocidade** de 0,25× a 8×. Na velocidade de 1×, cada segundo de reprodução avança 15 segundos de simulação. Clique ou arraste a barra para avançar ou voltar em passos de um minuto. A reprodução pausa no horário escolhido e **Reproduzir** retoma dali. **Reiniciar** volta ao início. O mapa interpola a ocupação entre os blocos. Os KPIs comparam o pico completo. As camadas do mapa incluem LAeq, passagens, filas e GPS URBS. Encerre o servidor com `Ctrl+C`.

Nos replays com registro semafórico, os pontos verde, amarelo e vermelho mostram o estado dos movimentos por faixa a cada segundo. O ponto fica verde quando algum movimento da faixa está liberado. Passe o cursor para ver os estados individuais do SUMO. No mapa MQTT, um anel azul marca uma observação publicada e um anel roxo indica que o SUMO aplicou um ajuste de verde. O quadro sobre o mapa mostra quantos sinais enviaram observações, quantas propostas voltaram e quantos ajustes foram aplicados. Use **0,25×** ou **Pausar** para ler um lote. Os eventos reais são gravados em `runs/<id>/signal-events.jsonl`. Replays anteriores a esse registro continuam com os pontos de localização dos semáforos.

**Carros simulados** e **Ônibus simulados** mostram as coordenadas individuais registradas pelo TraCI a cada 2 segundos simulados nas novas execuções. O mapa interpola entre posições consecutivas do mesmo veículo. Os KPIs continuam usando blocos de 30 segundos. A legenda permite ocultar cada camada e ativar **GPS URBS** para comparar com os ônibus observados. Ao passar o mouse sobre um veículo, o mapa mostra seu identificador no SUMO e, para ônibus, a linha quando disponível. Execuções anteriores usam os registros de posição que já possuem.

Uma viagem concluída vai da partida efetiva à chegada no SUMO. As médias de duração e perda de tempo (`timeLoss`) consideram em conjunto todas as viagens concluídas de carros e ônibus. A maior fila e o CO₂ direto também representam os dois modais. A fila é medida pelas faixas conectadas, inclusive quando passa de uma via para outra. O quadro **Indicadores** mostra o total de CO₂ direto de carros e ônibus.

## Pedestres e bicicletas

No Marco 3, o enunciado pede modelar o comportamento de travessia no **Calçadão da XV de Novembro** e integrar **faixas exclusivas para ciclistas**. O SUMO simula pedestres nas calçadas e faixas conectadas à XV. A demanda a pé deriva de uma pesquisa no calçadão e usa uma fração estimada de 15% por faixa modelada. O painel conta entradas simuladas nas travessias monitoradas. As bicicletas percorrem conexões exclusivas na malha SUMO, com preferência pelos trechos próximos ao cadastro do IPPUC. As 32 partidas por hora são um parâmetro de cenário e o painel também mostra quantas viagens terminaram. As camadas **Ciclovias SUMO** e **Ciclovias IPPUC** permitem comparar a malha simulada com o cadastro municipal. [Premissas e referências](docs/memorial.md)

## Controle dinâmico e comparação As-Is × To-Be

`run` e `simulate` usam a Onda Verde da Kennedy com controle `fixed` por padrão. Use `--signals` para carregar outro plano SUMO. O plano padrão é a reconstrução da Kennedy usada como referência do projeto. As defasagens municipais vigentes estão pendentes. [Origem do plano](docs/onda-verde.md)

Use `python -m ca run --month 2026-07 --control ml` para executar o controle aprendido sobre a Onda Verde. O modelo padrão é carregado por pico a partir de `config/models/`. O modo `cycle-pressure` usa as mesmas restrições com uma regra determinística, e `by-peak` aplica presença de manhã e prioridade BRT seletiva à tarde. [Experimento e resultados](docs/controle-aprendido.md)

Use `--control ml-online` para atualizar o modelo durante a simulação. O painel mostra quantas atualizações ocorreram e quantas decisões a evidência recente mudou. [Método e comparação online](docs/controle-aprendido.md#aprendizado-online)

Os modos `feedback` e `feedback-transit` usam a ocupação das saídas e as filas observadas para decidir os ajustes de verde. [Malha fechada e comparação com a Onda Verde](docs/malha-fechada.md)

O modo **`mqtt-adaptive`** fecha a malha pelo broker. Dois clientes MQTT trocam observações de câmeras virtuais e decisões de duração do verde. Quando a Onda Verde da Kennedy está carregada, os oito sinais do corredor participam do mesmo controle. O verde longo de cada um pode terminar até 4 s antes ou depois do horário previsto pelo plano. Com um broker MQTT 5 local iniciado por `mosquitto -c config/mosquitto.conf`, use `python -m ca run --offline --control mqtt-adaptive --mqtt 127.0.0.1:1883`. Para usar a demanda de julho da comparação, siga os comandos de replay no relatório. [Método, resultados e reprodução](docs/quadrilatero-mqtt.md)

Use `replay` para comparar estratégias com a mesma rota, malha, semente, janela e limites de velocidade de uma execução fixa concluída. A repetição herda o plano da execução de origem. Em referências antigas, passe `--signals config/signals/onda-verde-kennedy.add.xml` para aplicar a Onda Verde.

```powershell
python -m ca replay ID_DA_EXECUCAO_FIXA --name comparacao-fixa --control fixed
python -m ca replay ID_DA_EXECUCAO_FIXA --name comparacao-dinamica --control by-peak
python -m ca serve
```

O endpoint `/api/v1/runs/<run>/comparison` fornece os valores brutos dos indicadores, inclusive de alternativas arquivadas. A comparação exige uma repetição fixa com os mesmos arquivos de entrada. Para publicar sensores MQTT e receber solicitações de extensão de verde, consulte o [esquema de sensores e a configuração do broker](docs/arquitetura.md#sinalização-e-sensoriamento-virtual).

### Aproximação ao verde

Use `--eco-approach` em `run`, `simulate` ou `replay` para equipar os carros com o GLOSA do SUMO em toda a malha. O dispositivo estima quando o sinal abre para o movimento do carro e calcula uma velocidade de aproximação mais baixa quando há espaço e tempo para chegar durante o verde. O SUMO continua a aplicar o semáforo real e as regras de distância e prioridade. Uma fila ou um vermelho longo ainda pode exigir uma parada. [GLOSA no SUMO](https://eclipse.dev/sumo/docs/Simulation/GLOSA.html)

```powershell
python -m ca replay onda-tarde-kennedy --name tarde-aproximacao-verde --control fixed --eco-approach
python -m ca serve
```

Consulte `/api/v1/runs/tarde-aproximacao-verde/comparison` para ver os resultados desse replay. Com uma referência fixa sem GLOSA e os mesmos sinais e semente, o endpoint compara o tempo de viagem, o tempo parado e o número de paradas dos carros que concluíram a viagem em ambos os cenários sem teletransporte. O SUMO considera velocidades de até 0,1 m/s para medir paradas de trânsito ao longo de toda a viagem. [Definição dos indicadores](https://eclipse.dev/sumo/docs/Simulation/Output/TripInfo.html)

Em `eco_approach`, ajuste o alcance em metros, a velocidade mínima de aproximação em m/s e a margem em segundos depois da abertura do verde. [Configuração de Curitiba](config/curitiba.json)

#### Comparação no pico da tarde

As execuções `onda-tarde-kennedy`, `glosa-tarde-100m` e `glosa-tarde-150m` cobrem 17h–19h com a demanda de julho de 2026, semente 42 e os mesmos programas semafóricos. Os indicadores dos carros usam as 4.633 viagens concluídas sem teletransporte nos três cenários. Filas e CO₂ cobrem o pico completo.

| Indicador | Referência | 100 m e 18 km/h | 150 m e 14,4 km/h |
| --- | ---: | ---: | ---: |
| Tempo parado por carro (s) | 201,8 | 197,9 | 196,5 |
| Paradas por carro | 7,33 | 7,24 | 7,14 |
| Tempo de viagem por carro (s) | 744,3 | 741,0 | 741,5 |
| Fila média por cruzamento (m) | 4,19 | 3,97 | 3,95 |
| Maior fila na rede (m) | 260,4 | 274,5 | 334,2 |
| CO₂ de carros e ônibus (kg) | 16.416,1 | 16.120,7 | 16.008,7 |

A configuração padrão ao ativar GLOSA usa alcance de 100 m, velocidade mínima de aproximação de 18 km/h e margem de 2 s. Entre as configurações testadas, ela oferece a menor fila máxima e o menor tempo de viagem dos carros. As duas reduziram o tempo parado e a fila média em relação à referência, com aumento da maior fila. Os resultados se referem a um pico e uma semente de simulação.

## Arquitetura

**MOVE e URBS/C3SL** alimentam a demanda mensal. A malha do SUMO vem do **OSM**, e o cadastro do **IPPUC** orienta a escolha das rotas de bicicleta. O **TraCI** avança a simulação no SUMO e coleta chegadas, filas, ocupação e emissões a cada segundo. As execuções gravam blocos de 30 s em `runs/`. O **Dash** e a API HTTP leem os mesmos resultados. [Diagrama, módulos e contratos JSON](docs/arquitetura.md)

Use `run --no-dashboard` para gerar os resultados pelo terminal ou `serve` para reabrir execuções salvas. Use `simulate --help` para executar uma data específica ou usar uma captura ao vivo, e `run --help` para incluir contagens, medições acústicas ou um plano semafórico. A rede e as fontes ficam em `data/cache`. As saídas do simulador ficam em `runs`. A execução mensal aplica os limites de referência via TraCI durante o comando `run`.

Nesta máquina, as dependências também estão em `.deps`. Para usar o Python instalado diretamente, execute `$env:PYTHONPATH = '.deps'` antes de `python -m ca run`.

## Referências do projeto

- [Memorial de cálculo e fontes](docs/memorial.md)
- [Diagnóstico e resultados executados](docs/diagnostico.md)
- [Relatório executivo As-Is × To-Be](docs/relatorio-m4.md)
- [Comparação com Onda Verde e plano histórico da Setran](docs/onda-verde.md)
- [Controle aprendido e comparação com as regras](docs/controle-aprendido.md)
- [JSON Schema da integração](schemas/interop.schema.json)

# Comparação de KPIs e emissões no Quadrilátero de Curitiba

**Antes** corresponde à onda verde de referência, com tempos fixos. **Depois** corresponde ao controle preditivo, com a variante `atuado` pela manhã e `reservas_ciclo` à tarde. Os dois cenários de cada pico usaram a mesma rede, demanda, semente 101 do SUMO, limites de velocidade e plano semafórico inicial. A demanda foi montada com dados de julho de 2026. Os picos simulados são das 6h30 às 9h e das 17h às 19h. A semente 101 também foi usada na escolha das variantes. [Relatório do lote](onda_verde_senoidal/results_refinado/report.json) · [Seleção das variantes](docs/revisao-fluxo.md)

Nas tabelas, a seta indica **antes → depois**. A variação é calculada com os valores sem arredondamento pela fórmula `100 × (depois − antes) / antes`. Valores negativos indicam redução.

## KPIs da malha

| Pico | Viagens pareadas | Tempo médio de viagem (s) | Atraso médio (s) | Maior fila contínua (m) |
| --- | ---: | ---: | ---: | ---: |
| Manhã | 9.973 | 469,95 → 443,97 (−5,53%) | 248,99 → 223,31 (−10,32%) | 260,54 → 284,43 (+9,17%) |
| Tarde | 9.092 | 441,01 → 401,61 (−8,94%) | 237,77 → 198,92 (−16,34%) | 256,34 → 314,62 (+22,74%) |
| Dois picos | 19.065 | 456,15 → 423,77 (−7,10%) | 243,64 → 211,68 (−13,12%) | 260,54 → 314,62 (+20,76%) |

O tempo de viagem e o atraso médio diminuíram nos dois picos. A fila máxima da malha aumentou em ambos, com o maior aumento à tarde.

- **Tempo médio de viagem.** O SUMO registra `duration` em `trips.xml`, da entrada efetiva do veículo na malha à chegada. O simulador gera `completed.json` com os carros e ônibus que concluíram a viagem sem teletransporte. Para cada pico, o relatório cruza os IDs dos dois arquivos e calcula a média das durações desses mesmos veículos em cada cenário. [Coleta e filtro de viagens](onda_verde_senoidal/simulate.py) · [Pareamento e médias](onda_verde_senoidal/report.py) · [SUMO TripInfo](https://eclipse.dev/sumo/docs/Simulation/Output/TripInfo.html)
- **Atraso médio.** Usa o campo `timeLoss` dos mesmos IDs pareados. O SUMO acumula o tempo perdido ao trafegar abaixo da velocidade ideal do veículo e exclui o tempo das paradas programadas desse cálculo. A linha dos dois picos pondera tanto a duração quanto o atraso pelo número de viagens pareadas de cada pico. [Pareamento e médias](onda_verde_senoidal/report.py) · [Definição do SUMO](https://eclipse.dev/sumo/docs/Simulation/Output/TripInfo.html)
- **Maior fila contínua.** A cada passo de 1 s, o simulador mede, por faixa de aproximação semafórica, a distância da linha de retenção à traseira do último veículo da sequência. Considera carros e ônibus a menos de 0,1 m/s, com até 10 m entre a linha de retenção e o primeiro veículo e entre veículos sucessivos. Exclui veículos em parada programada e segue pelas faixas a montante enquanto a fila estiver conectada. O valor em `queues.json` é o máximo do pico, incluindo os cinco minutos iniciais. Na linha dos dois picos, usa-se o maior valor de cada cenário. [Coleta das filas](onda_verde_senoidal/simulate.py) · [Algoritmo de medição](onda_verde_senoidal/queues.py)

## KPIs por trecho

Os trechos correspondem às três avenidas do painel, agrupadas pelos segmentos motorizados que têm o mesmo nome na rede SUMO. Uma passagem pode percorrer apenas parte da avenida. [Definição dos corredores](onda_verde_senoidal/network.py)

| Pico | Trecho | Passagens | Tempo médio no trecho (s) | Atraso médio (s) | Maior fila contínua (m) |
| --- | --- | ---: | ---: | ---: | ---: |
| Manhã | Av. Presidente Kennedy | 600 → 605 | 108,40 → 107,36 (−0,96%) | 43,57 → 43,10 (−1,07%) | 48,11 → 50,81 (+5,61%) |
| Manhã | Av. Sete de Setembro | 760 → 741 | 273,80 → 279,45 (+2,06%) | 238,08 → 243,62 (+2,33%) | 252,77 → 261,94 (+3,63%) |
| Manhã | Av. Marechal Floriano Peixoto | 676 → 671 | 93,21 → 74,14 (−20,46%) | 52,98 → 33,57 (−36,65%) | 82,58 → 112,15 (+35,80%) |
| Tarde | Av. Presidente Kennedy | 564 → 595 | 98,99 → 98,50 (−0,49%) | 43,86 → 43,46 (−0,91%) | 95,78 → 63,02 (−34,21%) |
| Tarde | Av. Sete de Setembro | 578 → 621 | 225,84 → 187,77 (−16,86%) | 190,51 → 152,44 (−19,98%) | 248,49 → 314,62 (+26,62%) |
| Tarde | Av. Marechal Floriano Peixoto | 694 → 661 | 90,85 → 83,88 (−7,67%) | 45,14 → 40,85 (−9,51%) | 106,31 → 102,80 (−3,30%) |

- **Tempo médio no trecho.** Para cada carro ou ônibus, o replay identifica o instante de entrada e o de saída observados na avenida. A permanência é `tempo da saída − tempo da entrada`. Os quadros são gravados a cada 2 s, a última via externa é mantida enquanto o veículo cruza um segmento interno da interseção e só entram na média as passagens com entrada e saída observadas depois de 300 s de aquecimento. A amostra é calculada em cada cenário e pode conter números diferentes de passagens. [Coleta dos quadros](onda_verde_senoidal/simulate.py) · [Cálculo das passagens](onda_verde_senoidal/report.py)
- **Atraso médio no trecho.** Nas mesmas passagens usadas para a permanência, foi registrado o `timeLoss` acumulado por veículo via TraCI/libsumo. Para cada passagem, calculou-se `timeLoss na saída − timeLoss na entrada` e, em seguida, a média das diferenças. A leitura usa os mesmos quadros de 2 s da permanência. [Variável `timeLoss` no TraCI](https://eclipse.dev/sumo/docs/TraCI/Vehicle_Value_Retrieval.html#overview_retrievable_vehicle_variables)
- **Maior fila contínua no trecho.** Aplica a mesma medição da malha às faixas de aproximação semafórica pertencentes à avenida. A extensão pode alcançar segmentos a montante conectados à fila. Em `queues.json`, as chaves são `kennedy`, `sete` e `floriano`. [Medição de filas](onda_verde_senoidal/simulate.py) · [Algoritmo de medição](onda_verde_senoidal/queues.py)

## Emissões na malha

| Substância (kg) | Manhã | Tarde | Dois picos |
| --- | ---: | ---: | ---: |
| CO₂ · dióxido de carbono | 20.814,53 → 19.869,49 (−4,54%) | 18.555,14 → 16.925,03 (−8,79%) | 39.369,66 → 36.794,52 (−6,54%) |
| CO · monóxido de carbono | 300,34 → 271,43 (−9,63%) | 327,56 → 259,67 (−20,73%) | 627,90 → 531,10 (−15,42%) |
| HC · hidrocarbonetos | 7,94 → 6,85 (−13,68%) | 6,61 → 5,52 (−16,44%) | 14,54 → 12,37 (−14,93%) |
| NOₓ · óxidos de nitrogênio | 110,29 → 99,91 (−9,42%) | 88,82 → 79,41 (−10,60%) | 199,12 → 179,32 (−9,94%) |
| PMₓ · material particulado | 3,08 → 2,69 (−12,64%) | 2,46 → 2,11 (−14,01%) | 5,53 → 4,80 (−13,25%) |

O total simulado de CO₂ caiu **2.575,14 kg** nos dois picos somados. O material particulado aparece como indicador complementar aos gases.

- **Totais da malha.** O dispositivo de emissões foi habilitado para todos os veículos com `--device.emissions.probability 1`. Em cada `trips.xml`, foram somados os atributos `CO2_abs`, `CO_abs`, `HC_abs`, `NOx_abs` e `PMx_abs` dos elementos `<emissions>` dos carros e ônibus, identificados pelos prefixos `car-` e `bus-`. Divide-se a soma em miligramas por 1.000.000 para obter quilogramas. A soma inclui as emissões registradas desde o início da simulação, inclusive de viagens ainda em curso ao término do pico e de veículos que sofreram teletransporte. Os dois picos são somados antes do arredondamento. O CO₂ foi conferido com o total do relatório do lote. [Configuração da coleta](onda_verde_senoidal/simulate.py) · [Campos e unidades do SUMO](https://eclipse.dev/sumo/docs/Simulation/Output/TripInfo.html)
- **Modelo de emissões.** Os tipos da demanda usam `HBEFA3/PC_G_EU5` para os carros flex representados por um veículo a gasolina, `HBEFA3/PC_D_EU5` para carros a diesel, `HBEFA3/Bus` para ônibus e `Zero/default` para carros elétricos. Os valores representam as emissões veiculares estimadas pelo modelo na simulação. [Tipos no arquivo de demanda](onda_verde_senoidal/results_refinado/manha/101/referencia/demand.rou.xml) · [Modelos de emissões do SUMO](https://eclipse.dev/sumo/docs/Models/Emissions.html)

## Emissões por trecho

| Pico | Trecho | CO₂ | CO | HC | NOₓ | PMₓ |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Manhã | Av. Presidente Kennedy | 330,487 → 334,660 (+1,26%) | 1,848 → 1,666 (−9,87%) | 0,099 → 0,095 (−3,51%) | 1,874 → 1,893 (+1,02%) | 0,044 → 0,043 (−1,12%) |
| Manhã | Av. Sete de Setembro | 1.479,621 → 1.590,988 (+7,53%) | 10,929 → 10,843 (−0,79%) | 1,103 → 1,210 (+9,71%) | 14,367 → 15,741 (+9,56%) | 0,455 → 0,500 (+9,92%) |
| Manhã | Av. Marechal Floriano Peixoto | 232,879 → 197,362 (−15,25%) | 2,522 → 1,601 (−36,50%) | 0,086 → 0,063 (−26,83%) | 1,396 → 1,144 (−18,03%) | 0,036 → 0,028 (−23,26%) |
| Tarde | Av. Presidente Kennedy | 238,022 → 241,488 (+1,46%) | 1,468 → 1,446 (−1,51%) | 0,067 → 0,067 (−0,68%) | 1,270 → 1,273 (+0,26%) | 0,029 → 0,029 (−0,43%) |
| Tarde | Av. Sete de Setembro | 1.142,766 → 1.033,092 (−9,60%) | 11,492 → 7,850 (−31,69%) | 0,807 → 0,738 (−8,54%) | 10,379 → 9,735 (−6,21%) | 0,328 → 0,305 (−7,03%) |
| Tarde | Av. Marechal Floriano Peixoto | 242,026 → 223,908 (−7,49%) | 2,441 → 2,157 (−11,65%) | 0,092 → 0,082 (−10,67%) | 1,456 → 1,348 (−7,46%) | 0,038 → 0,035 (−9,55%) |

Todos os valores estão em **kg**. Nas reexecuções, a coleta `<edgeData type="emissions">` registrou as massas por segmento externo da malha, do início ao fim de cada pico, com filtro pelos quatro tipos de carro e ônibus da demanda. Os campos em mg foram somados pelos IDs dos segmentos de cada avenida e divididos por 1.000.000. A soma cobre toda a circulação nesses segmentos, incluindo passagens parciais. As ligações internas de cruzamento e as demais vias compõem a diferença de cobertura em relação à tabela da malha. [Definição dos corredores](onda_verde_senoidal/network.py) · [Saída de emissões por segmento do SUMO](https://eclipse.dev/sumo/docs/Simulation/Output/Lane-_or_Edge-based_Emissions_Measures.html)

As medições locais foram feitas em uma reexecução dos quatro cenários com libsumo 1.28.0. Na reexecução dos cenários preditivos, a entrega integral e ordenada das mensagens do ensaio foi reproduzida em memória. Foram conferidos os insumos, os IDs e indicadores das viagens concluídas, as filas máximas, as contagens de mensagens e de ajustes semafóricos e o número e a duração média das passagens por avenida. [Simulação e coleta](onda_verde_senoidal/simulate.py) · [Controle preditivo](onda_verde_senoidal/control.py) · [Resultados originais](onda_verde_senoidal/results_refinado/report.json)

## Arquivos de origem

| Pico | Antes | Depois |
| --- | --- | --- |
| Manhã | [Viagens](onda_verde_senoidal/results_refinado/manha/101/referencia/trips.xml) · [Viagens concluídas](onda_verde_senoidal/results_refinado/manha/101/referencia/completed.json) · [Filas](onda_verde_senoidal/results_refinado/manha/101/referencia/queues.json) | [Viagens](onda_verde_senoidal/results_refinado/manha/101/revisado/trips.xml) · [Viagens concluídas](onda_verde_senoidal/results_refinado/manha/101/revisado/completed.json) · [Filas](onda_verde_senoidal/results_refinado/manha/101/revisado/queues.json) |
| Tarde | [Viagens](onda_verde_senoidal/results_refinado/tarde/101/referencia/trips.xml) · [Viagens concluídas](onda_verde_senoidal/results_refinado/tarde/101/referencia/completed.json) · [Filas](onda_verde_senoidal/results_refinado/tarde/101/referencia/queues.json) | [Viagens](onda_verde_senoidal/results_refinado/tarde/101/revisado/trips.xml) · [Viagens concluídas](onda_verde_senoidal/results_refinado/tarde/101/revisado/completed.json) · [Filas](onda_verde_senoidal/results_refinado/tarde/101/revisado/queues.json) |

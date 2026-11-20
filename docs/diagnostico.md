# Diagnóstico do cenário de referência

## Execução mensal com a matriz O/D

Os dois picos de julho de 2026 foram concluídos com as medianas e a matriz O/D do TomTom MOVE, usando o GPS da URBS de 31/07/2026. A matriz foi calculada para nove zonas. Cada combinação inclui o par de zonas e o tipo de origem ou destino externo. As viagens dos carros são amostradas entre as combinações com rota na malha.

| Indicador simulado | Manhã 06:30–09:00 | Tarde 17:00–19:00 |
|---|---:|---:|
| Peso da matriz O/D representado por rotas na malha | 94,98% | 94,57% |
| Viagens de carro concluídas | 5.197 | 4.708 |
| Maior fila contínua | 431,28 m | 272,76 m |
| Entradas nas faixas de pedestres da XV | 666 | 2.583 |
| Viagens de bicicleta concluídas | 80 | 64 |

Os resultados ficam nas execuções `mensal-2026-07-manha-20261119-015247-214710` e `mensal-2026-07-tarde-20261119-015247-214710`. A cobertura da matriz mede o peso da amostra que recebeu uma rota viável. A calibração do volume absoluto requer contagens independentes.

## Estado da evidência

O cenário reproduz a topologia importada da área de estudo, tráfego individual baseado em velocidades históricas, itinerários de ônibus derivados do GPS e deslocamentos ativos. As simulações preliminares usam dados observados da URBS de **16 de novembro de 2026** nos dois picos. A demanda de automóveis foi estimada a partir dos relatórios TomTom de agosto de 2024 e das premissas em `config/curitiba.json`. O plano fixo foi gerado pelo SUMO a partir da malha OSM. A coleta TomTom autenticada foi verificada em horário posterior aos picos simulados e está disponível no painel com o seu horário efetivo.

Nos arquivos do C3SL, o nome segue a data de publicação. O campo `DTHR` do GPS fornece o horário da observação. A coleta contém os cinco arquivos de cada dia de 10 a 16 de novembro e o GPS publicado em 17 de novembro. Esse último arquivo contém as posições do dia 16. Foram verificadas posições com `DTHR` em todos os sete dias de 10 a 16.

| Data da posição | Registros de GPS na cidade | Registros no envelope de estudo |
|---|---:|---:|
| 10/11 | 3.602.261 | 494.903 |
| 11/11 | 3.563.487 | 486.454 |
| 12/11 | 3.580.365 | 489.539 |
| 13/11 | 3.561.922 | 491.013 |
| 14/11 | 2.077.342 | 290.154 |
| 15/11 | 1.608.932 | 209.024 |
| 16/11 | 3.544.735 | 484.204 |

A camada do GeoCuritiba forneceu 58 feições cicloviárias operacionais no envelope. O mapa reúne a rede SUMO, os corredores do enunciado, as faixas da XV e as posições observadas e simuladas dos ônibus no horário da reprodução. [C3SL/UFPR](https://dadosabertos.c3sl.ufpr.br/curitibaurbs/) · [GeoCuritiba](https://geocuritiba.ippuc.org.br/server/rest/services/GeoCuritiba/CICLOVIA_dashboard/FeatureServer/0) · [TomTom Traffic Flow](https://docs.tomtom.com/traffic-api/documentation/tomtom-maps/v1/traffic-flow/flow-segment-data)

## Resultados simulados em 16 de novembro

| Indicador | Manhã 06:30–09:00 | Tarde 17:00–19:00 |
|---|---:|---:|
| Rotas de ônibus reconstruídas | 1.551 | 1.581 |
| Pontos GPS observados no envelope e na janela | 91.915 | 75.156 |
| Pontos associados em rotas aceitas | 56.362 | 48.474 |
| Mediana do erro espacial mediano por rota de ônibus | 3,47 m | 3,59 m |
| Viagens concluídas de carros | 5.317 | 4.835 |
| Viagens concluídas de ônibus | 1.378 | 1.370 |
| Tempo médio de viagem dos carros | 572,27 s | 590,99 s |
| Tempo médio da rota observada de ônibus, simulada no recorte | 692,25 s | 548,14 s |
| Atraso médio dos carros | 329,45 s | 347,33 s |
| Atraso médio dos ônibus | 418,71 s | 342,57 s |
| Maior fila, com alcance de detecção de 100 m | 100 m | 100 m |
| Travessias na XV, total das duas faixas | 666 | 2.583 |
| Veículos com teleporte detectado no SUMO | 124 | 181 |

A mediana espacial descreve o ajuste dos pontos aceitos aos trechos. A validação temporal das viagens de ônibus exige comparar as trajetórias persistidas e o tempo de passagem em pontos de controle. Os teleportes são eventos de desbloqueio do simulador e podem refletir saturação ou conexões problemáticas da malha. Com a escolha periódica de rota para os carros, o número de veículos afetados caiu de 772 para 124 de manhã e de 806 para 181 à tarde, mantendo a demanda nominal. Esse ajuste é uma premissa comportamental, com validação real pendente.

| Massa de escapamento | Manhã (kg) | Tarde (kg) |
|---|---:|---:|
| CO₂, total | 19.043,910 | 17.332,675 |
| CO₂, carros | 8.349,837 | 8.128,345 |
| CO₂, ônibus | 10.694,073 | 9.204,331 |
| CO, total | 269,279 | 268,311 |
| NOₓ, total | 105,033 | 92,803 |
| HC, total | 7,272 | 6,660 |
| PMx, total | 2,879 | 2,586 |

| Cruzamento de maior fluxo | Passagens manhã / tarde | LAeq manhã / tarde | Pico de Lp,A manhã / tarde |
|---|---:|---:|---:|
| Av. Água Verde × Rua Brigadeiro Franco × Rua Chile | 773 / 685 | 65,9 / 66,2 dB(A) | 94,6 / 87,9 dB(A) |
| Rua Brigadeiro Franco × Rua Piauí | 596 / 553 | 68,0 / 68,2 dB(A) | 89,4 / 89,6 dB(A) |
| Rua Brigadeiro Franco × Rua João Parolin | 547 / 503 | 67,9 / 68,0 dB(A) | 93,1 / 92,7 dB(A) |

Resultados locais em `runs/curitiba-manha` e `runs/curitiba-tarde`. A API HTTP permite calcular indicadores por intervalo e consultar a comparação de velocidades, as rotas e as fontes. [Arquitetura](arquitetura.md)

## Validação do cenário

- O GEH está **sem contagens**. Faltam contagens direcionais de carros e ônibus para os mesmos locais e horários de novembro de 2026. O relatório do IPPUC de 2017 serve como referência metodológica para a campanha de contagem. [Pesquisas do IPPUC](https://ippuc.org.br/pesquisas)
- O LAeq calculado representa contribuição estimada do tráfego. As medições residuais e totais com procedimento ABNT NBR 10151 ainda precisam ser coletadas. As fórmulas, distâncias e receptores estão no [Memorial](memorial.md).
- A demanda de travessia usa a pesquisa de campo de 2016 como perfil e aplica uma fração de travessia estimada. Os dois pontos e as permissões das faixas foram verificados no modelo `striping`. [Leitoles, seção 3.3](https://fileserver-az.core.ac.uk/download/pdf/94926054.pdf)
- Os cálculos de emissões representam escapamento e usam proxies HBEFA3 para a frota. Rotas, volumes contemporâneos, composição da frota e planos semafóricos levantados em campo são necessários para a calibração operacional da cidade.

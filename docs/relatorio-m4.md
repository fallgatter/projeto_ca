# Controle semafórico adaptativo no Quadrilátero Central de Curitiba

**Relatório executivo · Ciências do Ambiente · UTFPR · Marcos 3 e 4**

[Comparação complementar com a Onda Verde estimada e o plano histórico da Setran](onda-verde.md)

## Resultado da comparação

O **perfil por pico (`by-peak`)** aplica **atuação por presença de manhã** e **prioridade BRT seletiva à tarde**. Cada modo obteve a melhor pontuação no seu pico. O perfil alcançou +5,08 pontos na média dos dois horários. Entre as estratégias avaliadas para uso nos dois picos, a atuação por presença liderou com +3,27 pontos.

A pontuação é a média das variações percentuais no atraso de carros e ônibus, na fila média, na velocidade da rede e no atraso BRT das viagens comuns aos dois cenários. Uma melhora recebe sinal positivo, inclusive quando vem da redução de um indicador. O cenário precisa preservar pelo menos 98% das viagens motorizadas concluídas em cada pico. A maior fila, as emissões, o ruído e os demais indicadores complementam a análise.

| Estratégia | Pico | Atraso motor | Fila média | Velocidade | Atraso BRT pareado | Viagens motoras concluídas | Pontuação |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Atuação por presença | Manhã | +0,2% | −14,7% | +4,6% | −7,1% | +1,4% | +3,27 |
| Atuação por presença | Tarde | −0,8% | −0,6% | +0,6% | +2,1% | +0,3% |  |
| Pressão local | Manhã | −1,8% | −9,2% | +2,0% | −5,7% | +0,5% | +2,97 |
| Pressão local | Tarde | −1,9% | −2,2% | +1,5% | +0,6% | +0,7% |  |
| Prioridade BRT seletiva | Manhã | +0,8% | −10,6% | +2,1% | +4,0% | +0,5% | +2,78 |
| Prioridade BRT seletiva | Tarde | +0,5% | −3,7% | +0,7% | −10,5% | +1,0% |  |
| Atuação por fila | Manhã | +1,0% | −12,7% | +2,6% | −5,1% | +0,9% | +1,24 |
| Atuação por fila | Tarde | −1,8% | +2,2% | +0,1% | +9,1% | +0,3% |  |
| Pressão e chegada de pelotões | Manhã | +1,1% | −6,0% | +1,3% | +8,2% | +0,6% | −0,18 |
| Pressão e chegada de pelotões | Tarde | −1,8% | +0,2% | +0,5% | +1,4% | +0,6% |  |

Execuções As-Is `m4-manha-fixed` e `m4-tarde-fixed`. Execuções To-Be selecionadas `m4-manha-gap` e `m4-tarde-transit`. O perfil usa esses dois resultados, pois cada janela foi simulada de forma independente. A seleção foi feita na própria amostra comparada.

### Mobilidade e ambiente no To-Be selecionado

| Indicador | Manhã · Fixo → Presença | Variação | Tarde · Fixo → BRT seletivo | Variação |
| --- | ---: | ---: | ---: | ---: |
| Atraso médio motor (s) | 334,4 → 335,0 | +0,2% | 323,7 → 325,2 | +0,5% |
| Tempo médio de viagem motor (s) | 718,2 → 718,5 | +0,04% | 722,3 → 725,6 | +0,4% |
| Velocidade de rede (km/h) | 12,95 → 13,56 | +4,6% | 12,17 → 12,26 | +0,7% |
| Fila média (m) | 4,81 → 4,10 | −14,7% | 4,05 → 3,90 | −3,7% |
| Maior fila (m) | 431,3 → 338,4 | −21,5% | 272,8 → 253,6 | −7,0% |
| Viagens motorizadas concluídas | 6.368 → 6.457 | +1,4% | 5.996 → 6.055 | +1,0% |
| Teletransportes | 174 → 120 | −31,0% | 79 → 60 | −24,1% |
| Atraso médio de ônibus (s) | 486,1 → 534,4 | +9,9% | 387,6 → 384,2 | −0,9% |
| Atraso BRT, todas as viagens concluídas (s) | 935,6 → 1.058,0 | +13,1% | 680,7 → 649,3 | −4,6% |
| Viagens BRT concluídas | 178 → 212 | +19,1% | 237 → 255 | +7,6% |
| Atraso BRT nas mesmas viagens (s) | 898,9 → 835,0 | −7,1% | 662,8 → 593,5 | −10,5% |
| Viagens BRT comuns aos cenários | 166 → 166 | 0,0% | 230 → 230 | 0,0% |
| Travessias monitoradas | 666 → 666 | 0,0% | 2.583 → 2.583 | 0,0% |
| Viagens de pedestres concluídas | 656 → 656 | 0,0% | 2.553 → 2.553 | 0,0% |
| Espera média de pedestres (s) | 39,14 → 39,14 | 0,0% | 39,52 → 39,50 | <0,1% de redução |
| Viagens de bicicleta concluídas | 80 → 80 | 0,0% | 64 → 64 | 0,0% |
| CO₂ (kg) | 20.099,5 → 19.189,3 | −4,5% | 16.188,9 → 16.096,8 | −0,6% |
| CO (kg) | 306,50 → 293,22 | −4,3% | 292,79 → 292,90 | +0,04% |
| NOₓ (kg) | 124,74 → 115,91 | −7,1% | 89,20 → 87,82 | −1,5% |
| HC (kg) | 9,093 → 8,323 | −8,5% | 6,534 → 6,413 | −1,8% |
| PMx (kg) | 3,566 → 3,265 | −8,4% | 2,482 → 2,433 | −2,0% |
| LAeq em 650 receptores (dB(A)) | 67,44 → 67,31 | −0,13 dB | 67,48 → 67,38 | −0,10 dB |

O perfil reduziu a fila média e a maior fila nos dois horários, ao custo de um pequeno aumento do atraso médio de carros e ônibus. A pressão local reduziu esse atraso nos dois picos, com aumento do comprimento da maior fila em ambos. De manhã, o atraso no grupo fixo de 166 viagens BRT caiu 7,1%, enquanto a média de todos os BRT concluídos subiu de 935,6 para 1.058,0 s e o número de viagens concluídas cresceu de 178 para 212. As duas médias respondem a perguntas diferentes e usam conjuntos diferentes de viagens.

Nos dois picos, o perfil evitou aproximadamente 1,0 t de CO₂ e 0,35 kg de PMx de escapamento no recorte simulado. A variação estimada no LAeq conjunto foi de décimos de decibel. As travessias monitoradas e as viagens de bicicleta concluídas tiveram a mesma contagem em cada par.

## Desenho do experimento

O cenário As-Is usa o programa fixo produzido pelo SUMO para a malha OpenStreetMap. Cada To-Be repete a mesma janela, arquivo de demanda, malha, plano inicial e limites de velocidade, com semente 42 e SUMO 1.28.0. A edição do verde é a intervenção comparada. As simulações representam os picos de 06h30–09h00 e 17h00–19h00 em horário de Curitiba. A demanda sintética de automóveis usa o Traffic Stats e o O/D Analysis de julho de 2026. A demanda de ônibus usa GPS, itinerários e paradas da URBS/C3SL de 31 de julho. As estimativas para pedestres e ciclistas permanecem iguais em cada par.

| Partidas programadas | Manhã | Tarde |
| --- | ---: | ---: |
| Automóveis | 5.750 | 5.400 |
| Ônibus | 1.448 | 1.465 |
| Pedestres | 666 | 2.588 |
| Bicicletas | 80 | 64 |

Foram elegíveis 85 dos 650 semáforos monitorados no recorte. O TraCI mede o tráfego a cada segundo. O controlador altera apenas a duração de verdes elegíveis, com piso e teto por fase, mantendo a ordem do programa, os amarelos, os vermelhos integrais e as fases dedicadas a pedestres e bicicletas. Em aproximações de ônibus BRT, o controlador usa o movimento do próximo semáforo para dar prioridade. O teste em broker local confirmou telemetria MQTT QoS 1, uma extensão aceita de 3 s via TraCI e a rejeição de uma duplicata. [Arquitetura, sensores e tópicos MQTT](arquitetura.md#sinalização-e-sensoriamento-virtual)

| Estratégia | Regra testada |
| --- | --- |
| Tempo fixo | Verdes e transições conforme o programa estático do SUMO |
| Presença | Verde reduzido quando a aproximação esvazia após o mínimo. A detecção de chegadas segue a ideia de atuação por lacunas do SUMO. |
| Fila | Duração do verde proporcional à demanda observada na aproximação, combinando veículos lentos e veículos que se aproximam |
| Pressão local | Regra de fila com desconto pela ocupação observada nas faixas de saída, inspirada em controle por pressão |
| Pressão e chegada de pelotões | Regra de pressão local com estímulo adicional a grupos de veículos que podem chegar ao verde em até 15 s |
| Prioridade BRT seletiva | O programa fixo prevalece sem ônibus elegível. A presença de um BRT pode prolongar seu verde em 6 s ou abreviar o verde corrente se a próxima fase estável atender seu movimento. |

As regras foram implementadas em Python para respeitar as mesmas restrições de fase. As variantes de pressão usam contagens por faixa, sem estimativa de proporções de conversão. [Atuação por presença no SUMO](https://eclipse.dev/sumo/docs/Simulation/Traffic_Lights.html#type-actuated) · [Albdairi e Almusawi, controle por fila em SUMO](https://doi.org/10.3390/futuretransp6020092) · [Anderson et al., pressão por ciclo](https://doi.org/10.3934/nhm.2018011) · [Ahmed et al., pressão coordenada por pelotões](https://arxiv.org/abs/2407.01421) · [Prioridade semafórica para ônibus, FHWA](https://ops.fhwa.dot.gov/publications/fhwahop08024/chapter9.htm)

## Cálculo dos indicadores

- **Atraso e tempo de viagem** usam `timeLoss` e o intervalo entre partida efetiva e chegada. Entram nas médias as viagens motorizadas concluídas sem teletransporte. Para BRT, também se compara o atraso nas mesmas viagens que concluíram nos dois cenários, usando `timeLoss` do `trips.xml`. Viagens concluídas e teletransportes ajudam a identificar mudanças de composição da amostra. [TripInfo no SUMO](https://eclipse.dev/sumo/docs/Simulation/Output/TripInfo.html)
- **Velocidade da rede** é a média das velocidades de carros e ônibus por veículo-segundo no recorte, incluindo filas. **Fila média** é a média, no tempo e entre cruzamentos, da maior fila conectada de cada cruzamento a cada segundo. **Maior fila** é o máximo observado no pico.
- **Mobilidade ativa** usa os registros de entrada nas travessias para passagens e o `waitingTime` do SUMO nas viagens a pé concluídas. A contagem de bicicletas considera as viagens concluídas.
- **Emissões de escapamento** somam os fluxos de cada veículo de carro e ônibus, em kg, dentro do recorte. O SUMO fornece CO₂, CO, NOₓ, HC e PMx com o modelo HBEFA3. O indicador PMx é agregado. A base utilizada não permite distinguir PM₂,₅ de PM₁₀ nem calcular ressuspensão e desgaste. [Emissões no SUMO](https://eclipse.dev/sumo/docs/Models/Emissions.html)
- **Ruído** usa emissão Harmonoise por veículo e atenuação com a distância. O LAeq conjunto é calculado a partir da energia média por tempo e pelos receptores comuns, aplicando 10 log₁₀ ao final. A diferença é apresentada em dB. O cálculo inclui a contribuição do tráfego e aproxima a propagação sem representar fachadas, reflexões ou níveis residuais medidos. [Ruído no SUMO](https://eclipse.dev/sumo/docs/Simulation/Output/index.html) · [Memorial acústico](memorial.md)

## Viabilidade em Curitiba

A regra local exige detecção por aproximação, acesso aos movimentos comandados pelo semáforo e identificação do ônibus que se aproxima. A implantação exigiria validar os tempos e conflitos do programa real em cada cruzamento, medir a ocupação e integrar a posição de ônibus com os controladores nos corredores. O receptor MQTT testado representa a integração em laboratório. O experimento comparativo usou o controle autônomo via TraCI.

As duas janelas usam uma semente e um dia útil de GPS. As taxas de partida de automóveis são premissas do cenário. As execuções não incluem contagens contemporâneas para o teste GEH nem medições acústicas para conferir os receptores. Os resultados caracterizam o cenário simulado. Uma avaliação de implantação dependeria de um piloto com contagens direcionais, atraso por modal, níveis sonoros e checagem de tempos de travessia em campo.

## Reprodução

Os arquivos `metadata.json` registram a execução de origem e os SHA-256 da demanda, rede, plano, configuração e alvos de velocidade. `summary.json` contém os agregados, `frames.jsonl` contém os blocos de 30 s e `trips.xml` contém as viagens do SUMO. O painel compara os resultados pareados em **Mais dados → As-Is × To-Be**.

```powershell
python -m ca replay mensal-2026-07-manha-20261119-235229-202742 --name novo-manha-fixo --control fixed --summary-only
python -m ca replay mensal-2026-07-manha-20261119-235229-202742 --name novo-manha-adaptativo --control by-peak --summary-only
python -m ca serve
```

Para a tarde, use a execução `mensal-2026-07-tarde-20261119-235229-202742`. Para testar as outras estratégias, troque o valor de `--control` e dê um nome próprio a cada execução.

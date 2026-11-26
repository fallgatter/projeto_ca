# Revisão do fluxo e otimização semafórica

O experimento compara uma onda verde fixa, reconstruída no SUMO para o Quadrilátero de Curitiba, com um controlador que ajusta o tempo de verde durante a simulação. A série de Fourier estima o fluxo de fundo por aproximação. O controlador usa essa previsão junto com as chegadas detectadas e anunciadas pelos cruzamentos vizinhos para escolher quando encerrar o verde atual.

Os resultados deste relatório vêm de `results_refinado/`, o lote que o painel abre por padrão quando disponível. A demanda é de julho de 2026. Os picos simulados são das **6h30 às 9h** e das **17h às 19h**. O [relatório do lote anterior](../onda_verde_senoidal/results_fluxo/REVISAO.md) preserva as comparações da primeira revisão da correção de fluxo.

## 1. Calibração e execução do cenário base

A referência parte de um plano de tempos fixos. Ela aplica o plano reconstruído da Avenida Presidente Kennedy e, na manhã, usa também programas históricos adaptados da Setran. Nos demais trechos arteriais elegíveis, a defasagem entre verdes é estimada pelo tempo de percurso entre semáforos com ciclos compatíveis. O plano resultante representa a onda verde de referência no SUMO. [Construção do plano fixo](../onda_verde_senoidal/network.py)

Na calibração, quatro combinações de volume de carros e parâmetros de condução foram simuladas com a semente **17**. A escolha minimizou o erro absoluto médio entre as medianas de velocidade por trecho do SUMO e da TomTom nas vias de ajuste. Nos dois picos foi escolhido o mesmo conjunto.

| Parâmetro da simulação | Valor escolhido |
| --- | ---: |
| Multiplicador da demanda inicial de carros | 1,65 |
| Aceleração (`accel`) | 1,1 m/s² |
| Tempo de seguimento desejado (`tau`) | 1,4 s |
| Imperfeição de condução no modelo Krauß (`sigma`) | 0,65 |

As medianas TomTom servem de alvo na calibração. A circulação usa os limites de velocidade da malha e o comportamento simulado. O volume absoluto de carros é estimado. Depois de ajustar o volume, as partidas de carro são espaçadas por origem dentro de blocos de 15 minutos, com deslocamentos de até 8 s para equilibrar as entradas em janelas de 5 s. O escalonamento preserva o volume ajustado por bloco, as rotas e os horários dos demais modos. [Calibração de tráfego](../onda_verde_senoidal/results_refinado/CALIBRACAO.md) · [Escalonamento das partidas](../onda_verde_senoidal/demand.py)

## 2. Treinamento do modelo senoidal

### O que entra no treino

Uma **aproximação** é um trecho dirigido pelo qual os veículos chegam ao semáforo. Para cada aproximação, o modelo aprende a relação entre **hora do dia** e **taxa de chegada de carros e ônibus**. Essa relação descreve o fluxo de fundo observado na simulação com a onda verde fixa. O SUMO conta um veículo quando ele entra no trecho.

Os dois picos fornecem 18 blocos de treino por aproximação, dez de manhã e oito à tarde. O horário usado no ajuste é o ponto médio do bloco. As fórmulas abaixo convertem a contagem em veículos por hora e dão mais peso aos blocos com maior tempo de observação.

$$
y_i=\frac{3600\,N_i}{\Delta t_i},
\qquad w_i=\frac{\Delta t_i}{900}.
$$

$N_i$ é a contagem, $\Delta t_i$ é o tempo observado em segundos e 900 s correspondem a 15 min. Um bloco completo tem peso 1. Como os cinco primeiros minutos de cada pico são de aquecimento, o primeiro bloco tem 600 s de observação e peso 2/3. A tabela mostra duas observações reais da aproximação da Sete de Setembro com a Rua Doutor Faivre, identificada por `289957316`.

| Bloco | Horário usado no ajuste | Tempo observado | Contagem | Taxa observada | Peso |
| --- | --- | ---: | ---: | ---: | ---: |
| 6h30–6h45 | 6h37min30s | 10 min | 18 | 108 veículos/h | 2/3 |
| 7h–7h15 | 7h07min30s | 15 min | 37 | 148 veículos/h | 1 |

[Coleta de chegadas](../onda_verde_senoidal/simulate.py) · [Contagens do treino da manhã](../onda_verde_senoidal/results_refinado/manha/17/treino/summary.json)

### O que os senos e cossenos representam

A previsão de fluxo é uma soma de ondas com períodos fixos. O tempo $t$ é medido em horas desde a meia-noite.

$$
g(t)=a_0+\sum_{k=1}^{H}
\left[a_k\cos\!\left(\frac{2\pi kt}{24}\right)
+b_k\sin\!\left(\frac{2\pi kt}{24}\right)\right],
\qquad F(t)=\max\left(0,g(t)\right).
$$

O termo $a_0$ desloca a curva inteira para cima ou para baixo. Cada par $a_k,b_k$ combina seno e cosseno de mesmo período para ajustar a intensidade da oscilação e a posição dos seus picos no relógio. O primeiro harmônico oscila uma vez por dia. O segundo oscila duas vezes e ajuda a formar os picos da manhã e da tarde. A soma permite que esses picos tenham alturas e formatos diferentes. As contribuições de cada harmônico podem ser positivas ou negativas. O limite de zero vale para a previsão final $F(t)$.

Com $H=6$, os períodos são **24, 12, 8, 6, 4,8 e 4 horas**. A ordem é comum às **1.228 aproximações** do lote. Cada uma tem seus próprios **13 coeficientes**, um termo constante e seis pares de seno e cosseno. Como os períodos são divisões de 24 h, a curva nominal se repete a cada dia.

### Como o treino encontra os coeficientes

Para cada observação, o código calcula os valores dos senos e cossenos no horário central do bloco. Esses valores ficam fixos. A regressão ajusta os coeficientes que multiplicam cada termo. Por exemplo, o ponto de 7h07min30s pede que a soma das ondas se aproxime de 148 veículos/h. Os outros horários fazem o mesmo com suas próprias taxas. O ajuste encontra um único conjunto de coeficientes que melhor atende ao conjunto de pontos.

O método é **mínimos quadrados ponderados com regularização ridge**. A expressão minimizada soma o erro quadrático ponderado entre as taxas $y_i$ e a curva $g(t_i)$ com uma penalidade sobre os coeficientes dos harmônicos.

$$
\sum_i w_i\,[y_i-g(t_i)]^2
+\sum_{k=1}^{H}0{,}08\max\left(1,\left(\frac{k}{2}\right)^2\right)
\left(a_k^2+b_k^2\right).
$$

O primeiro termo aproxima a curva das observações. O segundo reduz oscilações excessivas ao penalizar coeficientes grandes, com penalidade maior nos harmônicos mais rápidos. O termo constante $a_0$ fica livre dessa penalidade. O código resolve o sistema linear resultante para cada aproximação e grava os coeficientes em `fourier.json`.

Como as observações se concentram nos dois picos, o ajuste inclui nove pontos auxiliares de peso **0,18** cada. Seus valores são frações da média das taxas de treino daquela aproximação. Por exemplo, o perfil auxiliar atribui às 3h uma taxa de 10% dessa média. Assim, a curva de 24 h tem apoio fora das janelas simuladas, onde seus valores são estimativas. [Implementação da base, regressão e perfil auxiliar](../onda_verde_senoidal/fourier.py)

### Como a ordem foi escolhida

O ajuste foi repetido para as ordens 2, 3, 4 e 6 usando a **semente 17**. Na **semente 73**, cada taxa prevista foi reconvertida em contagem para o tempo observado e comparada com a contagem do SUMO. O erro absoluto total foi dividido pela exposição em horas somada sobre todas as aproximações, produzindo o MAE em veículos/h. A ordem **6** obteve o menor MAE de validação. As contagens da referência na **semente 101** serviram como teste da previsão depois dessa escolha.

| Ordem $H$ | MAE de validação, semente 73 (veículos/h) | MAE de teste, semente 101 (veículos/h) |
| ---: | ---: | ---: |
| 2 | 9,066 | 9,059 |
| 3 | 9,115 | 8,967 |
| 4 | 9,070 | 8,906 |
| **6** | **8,823** | **8,643** |

[Coeficientes e validação](../onda_verde_senoidal/results_refinado/fourier.json) · [Resultados do teste da previsão](../onda_verde_senoidal/results_refinado/report.json)

### Como os harmônicos formam uma previsão

Na aproximação da Sete de Setembro com a Doutor Faivre, o treino encontrou $a_0=82{,}1794$. Para o harmônico de 12 h, os coeficientes são $a_2=-28{,}1197$ e $b_2=-30{,}8905$. Às 7h07min30s, os valores do cosseno e do seno desse harmônico são aproximadamente −0,8315 e −0,5556. Multiplicando pelos coeficientes e somando, a contribuição desse harmônico fica em **+40,54 veículos/h**. A mesma conta é feita para os demais harmônicos.

| Componente (veículos/h) | Às 7h07min30s | Às 7h35min22,5s |
| --- | ---: | ---: |
| Termo constante $a_0$ | 82,18 | 82,18 |
| Harmônico de 24 h | +2,85 | +7,05 |
| Harmônico de 12 h | +40,54 | +41,77 |
| Harmônico de 8 h | −0,09 | +4,07 |
| Harmônico de 6 h | +16,97 | +15,67 |
| Harmônico de 4,8 h | −8,58 | −6,60 |
| Harmônico de 4 h | +3,79 | −2,83 |
| **Previsão nominal** | **137,66** | **141,31** |

No primeiro horário, a curva ajustada estima **137,66 veículos/h** para o bloco cuja taxa observada foi **148 veículos/h**. O segundo horário é o ponto médio dos 45 segundos seguintes às 7h35. O controlador parte dessa previsão nominal e aplica a correção de fluxo descrita na seção seguinte. [Coeficientes da aproximação](../onda_verde_senoidal/results_refinado/fourier.json) · [Registro do replay](../onda_verde_senoidal/results_refinado/manha/101/revisado/forecast.json)

## 3. Correção da previsão durante a simulação

Os coeficientes permanecem fixos durante a execução. A cada minuto, o controlador atualiza um ajuste por aproximação. Para os $n$ minutos mais recentes, até cinco, ele soma as chegadas observadas ($O$) e as esperadas pela curva ($E$). A tolerância $T=2\sqrt{\max(1,E)}$ reduz a influência de variações pequenas em contagens baixas. O cálculo do erro usa apenas o excesso além dessa tolerância.

$$
e_m = \frac{60}{n}\operatorname{sgn}(O-E)\max(0,|O-E|-T),
\qquad r_m=0{,}80\,r_{m-1}+0{,}20\,e_m.
$$

O fator $60/n$ converte o desvio da janela para veículos por hora. A previsão corrigida para o horizonte de 45 s é a curva avaliada no ponto médio desse horizonte, mais $r_m$, com limite inferior de zero. [Regra de correção](../onda_verde_senoidal/flow.py) · [Atualização no controlador](../onda_verde_senoidal/control.py)

No replay da manhã, às **7h35**, a aproximação da Sete de Setembro com a Doutor Faivre registrou **4 veículos em cinco minutos**, ante **11,76 esperados**. A tolerância foi de **6,86 veículos**. O excesso gerou um erro de **−10,81 veículos/h** e a atualização suavizada resultou em **−10,35 veículos/h**. A previsão nominal de **141,31 veículos/h** passou para **130,96 veículos/h**. [Histórico da previsão e das decisões](../onda_verde_senoidal/results_refinado/manha/101/revisado/forecast.json)

## 4. Otimização do verde em horizonte móvel

Para cada cruzamento elegível, a estimativa de chegadas nos próximos **45 s** combina três fontes.

- **Detecção local.** A distância até o sinal e a velocidade dos veículos detectados nos últimos 160 m do trecho dão uma estimativa do instante de chegada. Veículos parados entram como fila imediata.
- **Comunicação entre cruzamentos.** Nos corredores, mensagens MQTT anunciam o tamanho estimado do grupo que saiu de um cruzamento vizinho e seu horário previsto de chegada.
- **Fluxo de fundo.** A previsão corrigida de Fourier acrescenta chegadas esperadas nos instantes mais distantes do horizonte. As variantes escolhidas reconciliam as fontes para reduzir a dupla contagem de veículos.

A variável de decisão é o **tempo restante do verde atual**. Para cada duração candidata, o código projeta as janelas de verde que atendem cada aproximação e estima quando a fila poderá escoar, considerando a capacidade por faixa. O custo combina a **espera prevista em veículos-segundo** com uma penalidade pela alteração em relação ao plano. As variantes também podem dar mais peso a ônibus e filas ou penalizar a liberação em direção a uma saída congestionada. O controlador aplica a opção de menor custo local e volta a avaliar com as observações seguintes. Nos cruzamentos protegidos, ele transfere tempo entre dois verdes, preservando a duração do ciclo. A ordem das fases, o amarelo e as fases exclusivas de travessia são preservados. [Modelo de atendimento e busca das durações candidatas](../onda_verde_senoidal/control.py)

Às **7h35min57s**, no mesmo cruzamento do exemplo, restavam **34 s** de verde. O controlador avaliou as seguintes durações. Escolheu **44 s** pelo menor custo previsto e descontou os 10 s adicionais de outro verde do ciclo. [Decisão registrada no replay da manhã](../onda_verde_senoidal/results_refinado/manha/101/revisado/forecast.json)

| Verde restante candidato (s) | Custo previsto |
| ---: | ---: |
| 24 | 73,46 |
| 29 | 71,50 |
| 34 | 31,52 |
| 39 | 33,06 |
| **44** | **3,71** |

## 5. Seleção das variantes e resultado otimizado

Os pesos, tempos e regras do controlador foram definidos em **12 variantes** e comparados na semente **101**. Cada par manteve a mesma malha, demanda, semente, limites de velocidade e plano inicial. O primeiro critério foi atingir **10% de redução no atraso médio da malha**. Em seguida, a seleção considerou quantos dos nove indicadores foram atingidos, incluindo tempo de viagem, tempo de permanência por via e maiores filas. Em caso de empate, considerou primeiro o pior resultado entre os indicadores e depois a soma dos ganhos. Pela manhã foi escolhido `atuado`, que leva em conta lacunas nas chegadas ao verde atual. À tarde foi escolhido `reservas_ciclo`, que usa as maiores filas medidas na referência para ponderar as filas observadas e protege o ciclo em cruzamentos selecionados. [Critério de seleção](../onda_verde_senoidal/improve.py) · [Comparação das 12 variantes](../onda_verde_senoidal/results_refinado/KPIS.md)

O atraso e a duração são calculados sobre os mesmos carros e ônibus que concluíram suas viagens sem teletransporte em ambos os cenários. O atraso usa o indicador `timeLoss` do SUMO, que registra o tempo perdido ao circular abaixo da velocidade ideal. A maior fila contínua é medida a partir da linha de retenção, com veículos abaixo de 0,1 m/s, distância de até 10 m entre eles e exclusão das paradas programadas. [Definição de `timeLoss` no SUMO](https://eclipse.dev/sumo/docs/Simulation/Output/TripInfo.html) · [Medição de filas](../onda_verde_senoidal/queues.py)

| Pico | Variante | Viagens pareadas | Atraso médio (s) | Duração média (s) | Maior fila contínua (m) |
| --- | --- | ---: | ---: | ---: | ---: |
| Manhã | `atuado` | 9.973 | 248,99 → 223,31 (**−10,32%**) | 469,95 → 443,97 | 260,54 → 284,43 |
| Tarde | `reservas_ciclo` | 9.092 | 237,77 → 198,92 (**−16,34%**) | 441,01 → 401,61 | 256,34 → 314,62 |

A meta de atraso foi atingida nos dois picos, com aumento da fila máxima da malha em ambos. A semente 101 foi reservada para testar a previsão de Fourier e foi usada para escolher as variantes do controlador. Os ganhos de atraso, portanto, descrevem o ensaio de seleção das variantes.

### Resultados por corredor

A permanência média considera passagens com entrada e saída observadas após o aquecimento. A maior fila é medida nas aproximações do corredor. As setas indicam a passagem da referência para o cenário preditivo.

| Pico | Corredor | Permanência média (s) | Maior fila contínua (m) |
| --- | --- | ---: | ---: |
| Manhã | Presidente Kennedy | 108,40 → 107,36 | 48,11 → 50,81 |
| Manhã | Sete de Setembro | 273,80 → 279,45 | 252,77 → 261,94 |
| Manhã | Marechal Floriano Peixoto | 93,21 → 74,14 | 82,58 → 112,15 |
| Tarde | Presidente Kennedy | 98,99 → 98,50 | 95,78 → 63,02 |
| Tarde | Sete de Setembro | 225,84 → 187,77 | 248,49 → 314,62 |
| Tarde | Marechal Floriano Peixoto | 90,85 → 83,88 | 106,31 → 102,80 |

Os dados do lote refinado também registram a distribuição das viagens pareadas, o tempo desde a partida programada, os percursos de pedestres e a comparação com o GPS dos ônibus na referência. [Indicadores por via e variante](../onda_verde_senoidal/results_refinado/KPIS.md) · [Tabelas detalhadas do lote refinado](../onda_verde_senoidal/results_refinado/REVISAO.md#distribuição-das-viagens-pareadas)

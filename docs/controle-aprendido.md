# Aprendizado sobre a Onda Verde

## Referência e alternativas

O cenário padrão usa a Onda Verde da Av. Presidente Kennedy e os demais programas fixos da malha. A referência é o plano da Kennedy reconstruído para o projeto. Os resultados se referem a essa reconstrução simulada. [Origem e comparação com dados históricos](onda-verde.md)

O modo `ml` usa um **bandit contextual por ciclo**. A cada início de ciclo, sinais elegíveis observam o desequilíbrio de filas entre duas fases, o volume aproximado, a ocupação a jusante e a presença de BRT. O modelo escolhe entre manter a alocação ou transferir 8 s de verde de uma fase para a outra. A compensação preserva a duração do ciclo e a hora em que ele volta a começar. A regra só admite fases com verdes nominais de pelo menos 20 s, aproximações distintas e sem verde de travessia de pedestres ou faixa exclusiva de bicicleta. Os programas adicionais, inclusive os oito da Onda Verde, são preservados por inteiro. A implementação usa TraCI e registra desvios do início nominal de ciclo.

O aprendizado registra, por estado e ação, quantas vezes a ação foi usada e a redução do custo local ao longo do ciclo. O custo combina fila, aproximação e prioridade BRT, com um desconto pela ocupação de saída usado para calcular a demanda atendível. Durante o treino, a exploração amostra ações aleatoriamente em 65% das decisões com demanda. O modelo congelado mantém o verde nominal quando o contexto tem menos evidência ou o benefício estimado fica abaixo do limite. Poluição, ruído, viagens, filas de rede e atraso BRT são medidos à parte no teste. [CycLight, coordenação no nível de ciclo](https://arxiv.org/abs/2401.08121) · [Controle híbrido de corredores com restrições](https://arxiv.org/abs/2508.20102)

`cycle-pressure` aplica uma regra determinística de pressão com o mesmo conjunto de ações e as mesmas restrições. `by-peak` representa o controlador anterior, que adapta a duração dos ciclos elegíveis. Essas comparações permitem avaliar o efeito do aprendizado e das restrições de coordenação separadamente.

## Desenho do experimento

O treino usa os arquivos de demanda `mensal-2026-07-{manha,tarde}-20261119-000410-273288`. Os testes recebem os arquivos `mensal-2026-07-{manha,tarde}-20261119-235229-202742`, com SHA-256 de rotas diferentes dos arquivos de treino. Cada pico tem um modelo próprio, congelado antes da avaliação. Todas as alternativas de teste usam a mesma demanda, semente 42, limites de velocidade, plano da Kennedy e períodos de 6h30–9h e 17h–19h. As duas demandas são do mesmo mês e foram testadas com uma semente de simulação.

## Resultados dos picos pareados

O modelo aprendido reduziu o atraso das viagens BRT comuns e as emissões de CO₂ nos dois picos, com vantagem sobre a regra determinística que usa as mesmas restrições. Houve contrapartidas. Na manhã, o atraso geral subiu 0,4% e os teletransportes passaram de 138 para 155. À tarde, a fila máxima nos oito sinais da Kennedy passou de 50,5 para 58,0 m, e os teletransportes passaram de 77 para 87. A fila na Kennedy pode variar mesmo com os oito programas preservados, porque as decisões tomadas fora do corredor alteram as chegadas.

O perfil por regras `by-peak` entregou a maior redução de atraso BRT nos dois picos e a maior redução de atraso geral pela manhã. O modelo aprendido obteve uma redução um pouco maior no atraso geral da tarde. As duas opções aumentaram a fila máxima da rede à tarde. Para a exigência de evitar piora em qualquer indicador testado, a Onda Verde serve como referência fixa e nenhuma das três alternativas cumpriu o critério.

As tabelas usam um único conjunto comum de viagens BRT nos quatro cenários de cada pico. O painel calcula a interseção entre a alternativa selecionada e a Onda Verde, então sua amostra BRT pode ser diferente.

### Manhã

A comparação BRT usa 157 viagens concluídas sem teletransporte nos quatro cenários. O modelo recebeu 293 amostras de treino, atuou em até 11 sinais elegíveis e executou 270 alterações de verde.

| Indicador | Onda Verde | ML | Pressão com ciclo fixo | Regras por pico |
| --- | ---: | ---: | ---: | ---: |
| Atraso médio de carros e ônibus (s) | 345,5 | 346,9 | 340,8 | 318,9 |
| Tempo médio de viagem (s) | 729,6 | 730,4 | 724,3 | 701,9 |
| Velocidade média da rede (km/h) | 13,05 | 13,15 | 13,03 | 13,27 |
| Fila média da rede (m) | 4,52 | 4,48 | 4,59 | 4,55 |
| Maior fila da rede (m) | 338,2 | 338,2 | 338,3 | 353,5 |
| Maior fila nos oito sinais da Kennedy (m) | 41,1 | 34,1 | 35,1 | 35,1 |
| Viagens motorizadas concluídas | 6.416 | 6.392 | 6.383 | 6.393 |
| Teletransportes | 138 | 155 | 171 | 169 |
| Atraso nas mesmas viagens BRT (s) | 986,2 | 862,6 | 917,8 | 813,6 |
| Viagens BRT concluídas | 204 | 209 | 192 | 187 |
| Travessias monitoradas | 666 | 666 | 666 | 666 |
| Viagens a pé concluídas | 656 | 656 | 656 | 656 |
| Espera média de pedestres (s) | 39,14 | 39,14 | 39,14 | 39,14 |
| Viagens de bicicleta concluídas | 80 | 80 | 80 | 80 |
| CO₂ (kg) | 20.019,6 | 19.677,7 | 19.939,7 | 19.676,3 |
| CO (kg) | 304,70 | 304,43 | 306,37 | 294,82 |
| NOₓ (kg) | 123,91 | 119,97 | 122,78 | 121,97 |
| HC (kg) | 9,007 | 8,703 | 8,940 | 8,833 |
| PMx (kg) | 3,534 | 3,406 | 3,501 | 3,474 |
| LAeq conjunto em 650 receptores (dB(A)) | 67,47 | 67,48 | 67,51 | 67,31 |

### Tarde

A comparação BRT usa 213 viagens concluídas sem teletransporte nos quatro cenários. O modelo recebeu 295 amostras de treino, atuou em até 11 sinais elegíveis e executou 138 alterações de verde.

| Indicador | Onda Verde | ML | Pressão com ciclo fixo | Regras por pico |
| --- | ---: | ---: | ---: | ---: |
| Atraso médio de carros e ônibus (s) | 330,5 | 324,1 | 331,5 | 325,5 |
| Tempo médio de viagem (s) | 730,0 | 724,1 | 730,7 | 725,9 |
| Velocidade média da rede (km/h) | 12,05 | 12,13 | 12,01 | 12,15 |
| Fila média da rede (m) | 4,19 | 4,15 | 4,21 | 4,06 |
| Maior fila da rede (m) | 260,4 | 270,2 | 265,2 | 267,2 |
| Maior fila nos oito sinais da Kennedy (m) | 50,5 | 58,0 | 57,5 | 57,6 |
| Viagens motorizadas concluídas | 6.001 | 6.011 | 5.990 | 6.010 |
| Teletransportes | 77 | 87 | 85 | 81 |
| Atraso nas mesmas viagens BRT (s) | 714,6 | 652,6 | 712,8 | 622,3 |
| Viagens BRT concluídas | 234 | 235 | 236 | 240 |
| Travessias monitoradas | 2.583 | 2.583 | 2.583 | 2.583 |
| Viagens a pé concluídas | 2.553 | 2.553 | 2.553 | 2.553 |
| Espera média de pedestres (s) | 39,48 | 39,53 | 39,45 | 39,52 |
| Viagens de bicicleta concluídas | 64 | 64 | 64 | 64 |
| CO₂ (kg) | 16.416,1 | 16.272,9 | 16.443,7 | 16.218,8 |
| CO (kg) | 296,23 | 294,71 | 297,07 | 294,22 |
| NOₓ (kg) | 91,22 | 89,75 | 91,42 | 89,28 |
| HC (kg) | 6,699 | 6,579 | 6,720 | 6,547 |
| PMx (kg) | 2,548 | 2,499 | 2,555 | 2,485 |
| LAeq conjunto em 650 receptores (dB(A)) | 67,47 | 67,49 | 67,56 | 67,42 |

## Reprodução

```powershell
python -m ca replay mensal-2026-07-manha-20261119-000410-273288 --name novo-treino-manha --control ml --train --signals config/signals/onda-verde-kennedy.add.xml --summary-only
python -m ca replay mensal-2026-07-manha-20261119-235229-202742 --name novo-teste-manha --control ml --model runs/novo-treino-manha/signal-model.json --signals config/signals/onda-verde-kennedy.add.xml --summary-only
```

A avaliação integrada pode usar os modelos incluídos em `config/models/` com `python -m ca run --month 2026-07 --control ml`. A referência fixa usa o mesmo comando com `--control fixed` ou sem o argumento de controle.

## Aprendizado online

`--control ml-online` parte do mesmo modelo usado em `ml` e combina suas estimativas com o que observa durante a execução. A cada ciclo concluído com demanda, o controlador compara o custo observado no início com a média das amostras a cada 5 s simulados. Ele atualiza a estimativa da ação executada naquele contexto. A evidência recente perde metade do peso a cada 15 min simulados, enquanto o modelo inicial mantém um peso de referência. Em 7% das decisões com demanda leve e sem BRT detectado, o controlador testa outra ação para renovar a evidência. A exploração ocorre no SUMO e usa as mesmas três ações limitadas. [Motivação para ponderação temporal em bandits](https://arxiv.org/abs/0805.3415)

O modo online mantém a duração do ciclo, as fases de transição e os oito programas da Onda Verde. Os indicadores de aprendizado aparecem em `online_control` a cada bloco de 30 s e no painel. O arquivo `signal-online-evidence.json` registra a evidência ponderada ao fim da execução. Cada execução começa com o modelo de referência, permitindo comparar cenários a partir do mesmo ponto.

### Comparação online × congelado

As duas execuções de ML partem do mesmo modelo por pico. A Onda Verde, as rotas, a semente e os limites de velocidade são idênticos. As viagens BRT foram pareadas nos três cenários de cada pico.

O aprendizado online alterou decisões nos dois picos. Frente ao modelo congelado, a fila máxima da Kennedy caiu 16,3% de manhã e subiu 37,8% à tarde. O atraso das viagens BRT comuns aumentou 5,7% pela manhã e 12,8% à tarde. O CO₂ subiu 1,9% à tarde. Os resultados sustentam o uso do modo online como opção experimental na simulação. A avaliação usa uma semente e duas janelas de julho de 2026.

#### Manhã

317 atualizações com base em ciclos concluídos. A evidência recente alterou 67 decisões em relação ao modelo congelado sob o mesmo estado observado. Houve 21 explorações e zero desvios do início dos ciclos. A amostra BRT contém 175 viagens.

| Indicador | Onda Verde fixa | ML congelado | ML online | Online × congelado |
| --- | ---: | ---: | ---: | ---: |
| Atraso médio de carros e ônibus (s) | 345,5 | 346,9 | 346,6 | −0,1% |
| Tempo médio de viagem (s) | 729,6 | 730,4 | 729,9 | −0,1% |
| Velocidade média da rede (km/h) | 13,05 | 13,15 | 13,13 | −0,1% |
| Fila média da rede (m) | 4,52 | 4,48 | 4,45 | −0,8% |
| Maior fila da rede (m) | 338,2 | 338,2 | 325,7 | −3,7% |
| Maior fila nos oito sinais da Kennedy (m) | 41,1 | 34,1 | 28,5 | −16,3% |
| Viagens motorizadas concluídas | 6.416 | 6.392 | 6.390 | 0,0% |
| Teletransportes | 138 | 155 | 137 | −11,6% |
| Atraso nas mesmas viagens BRT (s) | 1.056,4 | 927,7 | 980,8 | +5,7% |
| Viagens BRT concluídas | 204 | 209 | 195 | −6,7% |
| Travessias monitoradas | 666 | 666 | 666 | 0,0% |
| Viagens a pé concluídas | 656 | 656 | 656 | 0,0% |
| Espera média de pedestres (s) | 39,14 | 39,14 | 39,14 | 0,0% |
| Viagens de bicicleta concluídas | 80 | 80 | 80 | 0,0% |
| CO₂ (kg) | 20.019,6 | 19.677,7 | 19.681,8 | 0,0% |
| CO (kg) | 304,70 | 304,43 | 307,20 | +0,9% |
| NOₓ (kg) | 123,91 | 119,97 | 119,30 | −0,6% |
| HC (kg) | 9,007 | 8,703 | 8,650 | −0,6% |
| PMx (kg) | 3,534 | 3,406 | 3,381 | −0,7% |
| LAeq conjunto (dB(A)) | 67,47 | 67,48 | 67,46 | −0,02 dB |

#### Tarde

309 atualizações com base em ciclos concluídos. A evidência recente alterou 12 decisões em relação ao modelo congelado sob o mesmo estado observado. Houve 20 explorações e zero desvios do início dos ciclos. A amostra BRT contém 216 viagens.

| Indicador | Onda Verde fixa | ML congelado | ML online | Online × congelado |
| --- | ---: | ---: | ---: | ---: |
| Atraso médio de carros e ônibus (s) | 330,5 | 324,1 | 330,1 | +1,9% |
| Tempo médio de viagem (s) | 730,0 | 724,1 | 731,2 | +1,0% |
| Velocidade média da rede (km/h) | 12,05 | 12,13 | 11,96 | −1,4% |
| Fila média da rede (m) | 4,19 | 4,15 | 4,29 | +3,3% |
| Maior fila da rede (m) | 260,4 | 270,2 | 325,6 | +20,5% |
| Maior fila nos oito sinais da Kennedy (m) | 50,5 | 58,0 | 80,0 | +37,8% |
| Viagens motorizadas concluídas | 6.001 | 6.011 | 6.003 | −0,1% |
| Teletransportes | 77 | 87 | 95 | +9,2% |
| Atraso nas mesmas viagens BRT (s) | 711,9 | 644,9 | 727,5 | +12,8% |
| Viagens BRT concluídas | 234 | 235 | 235 | 0,0% |
| Travessias monitoradas | 2.583 | 2.583 | 2.583 | 0,0% |
| Viagens a pé concluídas | 2.553 | 2.553 | 2.553 | 0,0% |
| Espera média de pedestres (s) | 39,48 | 39,53 | 39,49 | −0,1% |
| Viagens de bicicleta concluídas | 64 | 64 | 64 | 0,0% |
| CO₂ (kg) | 16.416,1 | 16.272,9 | 16.589,7 | +1,9% |
| CO (kg) | 296,23 | 294,71 | 296,51 | +0,6% |
| NOₓ (kg) | 91,22 | 89,75 | 93,28 | +3,9% |
| HC (kg) | 6,699 | 6,579 | 6,856 | +4,2% |
| PMx (kg) | 2,548 | 2,499 | 2,614 | +4,6% |
| LAeq conjunto (dB(A)) | 67,47 | 67,49 | 67,56 | +0,08 dB |

```powershell
python -m ca run --month 2026-07 --control ml-online
```

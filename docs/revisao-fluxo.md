# Resultados do experimento

Controle preditivo coordenado com revisão do fluxo de fundo em janelas de cinco minutos.

O mapa contém 7245 segmentos motorizados e 649 semáforos.
Cada comparação usou a mesma malha, demanda, limites de velocidade, semente e plano inicial.
O atraso da rede considera os mesmos veículos concluídos sem teletransporte nos dois cenários.
A fração de tempo parado por via inclui carros e ônibus após 5 minutos de aquecimento.
Paradas programadas de ônibus integram o tempo parado.

| Pico | Semente | Atraso de viagem (s) | Kennedy, parado (%) | Sete, parado (%) | Floriano, parado (%) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Manhã | 101 | 264,54 → 231,52 | 10,26 → 6,64 | 80,45 → 84,83 | 28,64 → 14,51 |
| Tarde | 101 | 286,16 → 231,36 | 12,60 → 7,96 | 72,00 → 75,05 | 27,84 → 16,54 |

| Pico | Semente | Viagens concluídas | Teletransportes | CO₂ (kg) | MQTT entregues | Ajustes de verde |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Manhã | 101 | 6555 → 6593 | 57 → 68 | 17308,00 → 16748,42 | 1131/1131 | 50996 |
| Tarde | 101 | 6073 → 6133 | 52 → 54 | 15232,98 → 14385,73 | 1223/1223 | 48535 |

## Distribuição das viagens pareadas

| Pico | Semente | Viagens comuns | Medida (s) | Média | Mínimo | Mediana | P90 | P95 | Máximo |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| manha | 101 | 6486 | Atraso | 264,54 → 231,52 | 2,25 → 2,60 | 205,05 → 181,40 | 485,15 → 431,24 | 646,99 → 543,23 | 3275,32 → 4138,64 |
| manha | 101 | 6486 | Duração | 647,72 → 614,81 | 8,00 → 9,00 | 579,00 → 552,00 | 1176,00 → 1104,00 | 1365,00 → 1262,75 | 4450,00 → 5070,00 |
| tarde | 101 | 6003 | Atraso | 286,16 → 231,36 | 1,86 → 2,49 | 217,59 → 179,54 | 545,47 → 441,67 | 711,84 → 558,20 | 3795,44 → 3210,00 |
| tarde | 101 | 6003 | Duração | 686,07 → 630,88 | 8,00 → 8,00 | 609,00 → 568,00 | 1285,00 → 1183,00 | 1496,00 → 1374,00 | 4772,00 → 4019,00 |

## Meta de 10% de redução do atraso médio

| Pico | Semente | Ganho sobre onda verde | Meta atingida |
| --- | ---: | ---: | --- |
| manha | 101 | 12.48% | Sim |
| tarde | 101 | 19.15% | Sim |

As sementes 42 e 73 orientaram o ajuste. A semente 101, quando presente, avalia a política já definida sobre a mesma demanda com outra realização do SUMO.

| Grupo | Ocorrências de viagens pareadas | Atraso médio ponderado (s) | Redução |
| --- | ---: | ---: | ---: |
| Avaliação reservada | 12489 | 274,93 → 231,45 | 15.82% |
| Todos os ensaios | 12489 | 274,93 → 231,45 | 15.82% |

## Permanência nas três vias

Cada passagem requer entrada e saída observadas após cinco minutos de aquecimento. Os grupos de passagens podem ter tamanhos diferentes. A resolução do replay é de 2 s.

| Pico | Semente | Via | Passagens | Média (s) | Mínimo (s) | Mediana (s) | P95 (s) | Máximo (s) |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| manha | 101 | Avenida Presidente Kennedy | 368 → 373 | 121,46 → 122,61 | 2,00 → 2,00 | 96,00 → 114,00 | 266,00 → 252,80 | 544,00 → 346,00 |
| manha | 101 | Avenida Sete de Setembro | 566 → 535 | 339,41 → 347,57 | 4,00 → 4,00 | 93,00 → 90,00 | 1414,50 → 1573,00 | 3258,00 → 3914,00 |
| manha | 101 | Avenida Marechal Floriano Peixoto | 489 → 473 | 128,16 → 108,06 | 14,00 → 12,00 | 76,00 → 64,00 | 407,20 → 370,80 | 658,00 → 760,00 |
| tarde | 101 | Avenida Presidente Kennedy | 347 → 355 | 116,56 → 116,12 | 2,00 → 2,00 | 104,00 → 98,00 | 276,00 → 306,60 | 312,00 → 364,00 |
| tarde | 101 | Avenida Sete de Setembro | 517 → 503 | 289,36 → 303,28 | 2,00 → 2,00 | 94,00 → 86,00 | 1126,40 → 1337,80 | 2570,00 → 2986,00 |
| tarde | 101 | Avenida Marechal Floriano Peixoto | 456 → 462 | 140,21 → 123,33 | 10,00 → 6,00 | 78,00 → 76,00 | 502,50 → 429,90 | 670,00 → 694,00 |

## Todas as partidas programadas

Tempo médio desde a partida programada até uma chegada válida, em segundos. Para quem ficou pendente ou sofreu teletransporte, a contagem vai até o fim do pico.

| Pico | Semente | Referência → preditivo (s) |
| --- | ---: | ---: |
| manha | 101 | 696,26 → 667,50 |
| tarde | 101 | 718,88 → 661,35 |

## Pedestres simulados na XV de Novembro

| Pico | Semente | Percursos comuns | Duração média (s) | P95 (s) |
| --- | ---: | ---: | ---: | ---: |
| manha | 101 | 658 | 77,01 → 77,01 | 118,00 → 118,00 |
| tarde | 101 | 2566 | 81,14 → 81,14 | 122,00 → 122,00 |

## Aderência da referência aos dados locais

| Pico | Semente | Ônibus pareados | Mediana GPS (s) | Mediana SUMO (s) | Erro pareado mediano (s) | Erro absoluto mediano (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| manha | 101 | 1284/1448 | 565.0 | 492.0 | -31.5 | 165.0 |
| tarde | 101 | 1299/1465 | 490 | 372.0 | -69.0 | 172.0 |

O pareamento usa a duração do episódio de GPS usado na reconstrução da rota e a duração simulada do mesmo ônibus na referência.
Os volumes absolutos de carros foram assumidos. As medianas TomTom dos picos limitam a velocidade desejada e já incorporam efeitos do congestionamento observado. Filas e sinais do SUMO podem acrescentar atraso sobre esse efeito.

| Pico | Episódios de GPS na demanda | Paradas de ônibus codificadas | Intervalos com contagem de campo |
| --- | ---: | ---: | ---: |
| manha | 1448 | 149 | 0 |
| tarde | 1465 | 113 | 0 |

O tempo de embarque depende das paradas detectáveis no GPS. Os planos semafóricos mesclam registros históricos e defasagens inferidas dos tempos de percurso.

P90 e P95 usam interpolação linear. Cada extremo identifica o menor ou maior valor do grupo em cada cenário.
Os valores reportados são resultados do SUMO para a demanda de julho de 2026.

## Demanda escalonada e ordem de Fourier

As partidas de carro foram espaçadas por origem em blocos de 15 minutos, com uma fase sorteada por origem e bloco. Pequenos deslocamentos de até 8 s reduzem extremos em janelas de 5 s. A malha, o volume por bloco, as rotas e os horários dos demais modos foram preservados. Carros que entram pelo perímetro passam a usar a velocidade de inserção segura do SUMO.

Ordem adotada pelo erro absoluto médio de validação: **6**.

Validação, semente [73]: ordem 2: 6.401, ordem 3: 6.370, ordem 4: 6.326, ordem 6: 6.197 veíc./h.

Teste reservado, semente [101]: ordem 2: 6.432, ordem 3: 6.396, ordem 4: 6.353, ordem 6: 6.198 veíc./h.

| Pico | Intervalos avaliados | Intervalos menores que 5 s | Intervalos maiores que 120 s | P90 do intervalo (s) | Janelas de 5 s sem entrada na malha | Pico de entradas em 5 s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| manha | 1402 → 1402 | 97 → 1 | 194 → 90 | 142,0 → 107,9 | 77 → 2 | 10 → 9 |
| tarde | 1093 → 1093 | 86 → 0 | 185 → 57 | 157,0 → 106,8 | 29 → 0 | 11 → 10 |

Os intervalos são medidos nas dez origens de carro com maior demanda na referência original, com o mesmo plano fixo e a mesma semente. As janelas de 5 s abrangem todas as origens. O escalonamento controla a demanda gerada. A aderência dos intervalos à rua depende de medições de campo.

## Revisão da correção de fluxo

A contagem observada continua registrada por minuto. A revisão corrige a demanda de fundo com até cinco minutos de contagens acumuladas. O erro só contribui acima da tolerância de duas vezes a raiz do maior valor entre um e a contagem prevista. A tolerância é uma heurística para evitar que eventos isolados dominem o ajuste.

| Pico | Observações com Fourier até 30 veíc./h | Sem veículo | Um veículo | MAE em 5 min, antes → revisão | Saltos de pelo menos 10 veíc./h, antes → revisão |
| --- | ---: | ---: | ---: | ---: | ---: |
| manha | 115360 | 100274 | 13295 | 8,20 → 7,02 | 7984 → 9 |
| tarde | 87492 | 75121 | 10633 | 8,90 → 7,48 | 6475 → 4 |

Esse diagnóstico reaplica as duas regras ao mesmo histórico, com alvo igual à média dos cinco minutos seguintes. As tabelas anteriores apresentam as novas execuções do simulador.

| Pico | Viagens comuns aos três cenários | Atraso na referência | Atraso coordenado | Atraso revisado |
| --- | ---: | ---: | ---: | ---: |
| manha | 6425 | 258,77 | 236,39 | 223,94 |
| tarde | 5960 | 283,27 | 230,59 | 228,37 |

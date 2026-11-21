# Resultados do experimento

Primeira versão do controle preditivo de horizonte móvel.

O mapa contém 7245 segmentos motorizados e 649 semáforos.
Cada comparação usou a mesma malha, demanda, limites de velocidade, semente e plano inicial.
O atraso da rede considera os mesmos veículos concluídos sem teletransporte nos dois cenários.
A fração de tempo parado por via inclui carros e ônibus após 5 minutos de aquecimento.
Paradas programadas de ônibus integram o tempo parado.

| Pico | Semente | Atraso de viagem (s) | Kennedy, parado (%) | Sete, parado (%) | Floriano, parado (%) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Manhã | 42 | 257,21 → 242,20 | 10,41 → 9,28 | 82,95 → 89,18 | 29,29 → 13,37 |
| Manhã | 73 | 258,49 → 235,92 | 11,70 → 7,96 | 84,21 → 89,22 | 32,04 → 15,89 |
| Tarde | 42 | 278,31 → 230,06 | 10,35 → 17,86 | 71,81 → 83,41 | 28,78 → 16,46 |
| Tarde | 73 | 267,43 → 228,26 | 12,35 → 10,75 | 73,23 → 85,08 | 28,67 → 22,19 |

| Pico | Semente | Viagens concluídas | Teletransportes | CO₂ (kg) | MQTT entregues | Ajustes de verde |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Manhã | 42 | 6552 → 6405 | 90 → 181 | 17703,14 → 18389,51 | 1067/1067 | 55404 |
| Manhã | 73 | 6566 → 6436 | 72 → 201 | 17740,53 → 18279,20 | 1068/1068 | 55346 |
| Tarde | 42 | 6083 → 6008 | 46 → 161 | 15334,21 → 15026,28 | 1193/1193 | 52947 |
| Tarde | 73 | 6100 → 6024 | 61 → 146 | 15176,28 → 15177,84 | 1199/1199 | 52835 |

## Distribuição das viagens pareadas

| Pico | Semente | Viagens comuns | Medida (s) | Média | Mínimo | Mediana | P90 | P95 | Máximo |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| manha | 42 | 6324 | Atraso | 257,21 → 242,20 | 1,66 → 1,66 | 205,97 → 180,27 | 480,87 → 439,66 | 602,25 → 567,72 | 4594,25 → 4890,33 |
| manha | 42 | 6324 | Duração | 639,12 → 624,30 | 9,00 → 7,00 | 579,00 → 563,00 | 1160,00 → 1115,00 | 1344,00 → 1289,00 | 5361,00 → 5612,00 |
| manha | 73 | 6358 | Atraso | 258,49 → 235,92 | 2,02 → 2,02 | 208,12 → 182,53 | 491,90 → 435,66 | 630,35 → 563,92 | 3539,31 → 6231,92 |
| manha | 73 | 6358 | Duração | 639,32 → 616,84 | 8,00 → 8,00 | 582,00 → 562,00 | 1166,00 → 1112,30 | 1357,00 → 1289,00 | 4174,00 → 7357,00 |
| tarde | 42 | 5880 | Atraso | 278,31 → 230,06 | 1,86 → 1,96 | 218,22 → 182,30 | 552,50 → 442,43 | 711,70 → 590,23 | 2915,04 → 3182,76 |
| tarde | 42 | 5880 | Duração | 678,82 → 630,17 | 8,00 → 8,00 | 608,00 → 573,00 | 1276,00 → 1185,20 | 1496,00 → 1355,10 | 3845,00 → 3466,00 |
| tarde | 73 | 5911 | Atraso | 267,43 → 228,26 | 2,11 → 1,52 | 214,87 → 181,19 | 532,80 → 436,67 | 654,53 → 550,64 | 3182,19 → 5208,67 |
| tarde | 73 | 5911 | Duração | 667,22 → 627,90 | 8,00 → 7,00 | 603,00 → 573,00 | 1267,00 → 1160,00 | 1462,00 → 1340,00 | 4112,00 → 5797,00 |

## Meta de 10% de redução do atraso médio

| Pico | Semente | Ganho sobre onda verde | Meta atingida |
| --- | ---: | ---: | --- |
| manha | 42 | 5.84% | Não |
| manha | 73 | 8.73% | Não |
| tarde | 42 | 17.34% | Sim |
| tarde | 73 | 14.65% | Sim |

As sementes 42 e 73 orientaram o ajuste. A semente 101, quando presente, avalia a política já definida sobre a mesma demanda com outra realização do SUMO.

| Grupo | Ocorrências de viagens pareadas | Atraso médio ponderado (s) | Redução |
| --- | ---: | ---: | ---: |
| Ajuste | 24473 | 265,08 → 234,28 | 11.62% |
| Todos os ensaios | 24473 | 265,08 → 234,28 | 11.62% |

## Comparação com a versão anterior

| Pico | Semente | Viagens nos três cenários | Referência (s) | Anterior (s) | Preditivo (s) |
| --- | ---: | ---: | ---: | ---: | ---: |
| manha | 42 | 6267 | 255.78 | 259.62 | 240.15 |
| manha | 73 | 6295 | 255.51 | 258.29 | 233.14 |
| tarde | 42 | 5843 | 273.80 | 264.62 | 225.96 |
| tarde | 73 | 5864 | 263.93 | 264.29 | 226.27 |

## Permanência nas três vias

Cada passagem requer entrada e saída observadas após cinco minutos de aquecimento. Os grupos de passagens podem ter tamanhos diferentes. A resolução do replay é de 2 s.

| Pico | Semente | Via | Passagens | Média (s) | Mínimo (s) | Mediana (s) | P95 (s) | Máximo (s) |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| manha | 42 | Avenida Presidente Kennedy | 374 → 363 | 121,16 → 131,77 | 2,00 → 2,00 | 94,00 → 114,00 | 264,00 → 281,80 | 542,00 → 368,00 |
| manha | 42 | Avenida Sete de Setembro | 534 → 469 | 356,65 → 360,23 | 4,00 → 2,00 | 84,00 → 94,00 | 1598,20 → 1532,80 | 4990,00 → 5314,00 |
| manha | 42 | Avenida Marechal Floriano Peixoto | 495 → 468 | 130,07 → 116,09 | 14,00 → 4,00 | 80,00 → 64,00 | 432,00 → 420,60 | 658,00 → 626,00 |
| manha | 73 | Avenida Presidente Kennedy | 380 → 359 | 122,26 → 123,21 | 2,00 → 2,00 | 96,00 → 106,00 | 258,00 → 278,20 | 300,00 → 336,00 |
| manha | 73 | Avenida Sete de Setembro | 565 → 484 | 376,12 → 344,32 | 4,00 → 4,00 | 84,00 → 82,00 | 1683,60 → 2011,30 | 5166,00 → 5766,00 |
| manha | 73 | Avenida Marechal Floriano Peixoto | 498 → 470 | 132,57 → 119,33 | 14,00 → 14,00 | 79,00 → 66,00 | 453,20 → 427,10 | 776,00 → 736,00 |
| tarde | 42 | Avenida Presidente Kennedy | 343 → 343 | 115,72 → 131,38 | 2,00 → 2,00 | 108,00 → 104,00 | 277,60 → 317,80 | 312,00 → 664,00 |
| tarde | 42 | Avenida Sete de Setembro | 511 → 444 | 307,76 → 221,96 | 2,00 → 2,00 | 108,00 → 94,00 | 1530,00 → 991,10 | 3414,00 → 2996,00 |
| tarde | 42 | Avenida Marechal Floriano Peixoto | 460 → 457 | 142,07 → 129,65 | 10,00 → 4,00 | 79,00 → 78,00 | 506,20 → 436,40 | 908,00 → 686,00 |
| tarde | 73 | Avenida Presidente Kennedy | 350 → 345 | 116,34 → 116,27 | 2,00 → 2,00 | 111,00 → 112,00 | 277,10 → 271,20 | 380,00 → 398,00 |
| tarde | 73 | Avenida Sete de Setembro | 485 → 430 | 294,73 → 289,11 | 2,00 → 2,00 | 86,00 → 89,00 | 1462,40 → 1537,20 | 3280,00 → 4834,00 |
| tarde | 73 | Avenida Marechal Floriano Peixoto | 466 → 449 | 144,00 → 137,14 | 10,00 → 4,00 | 78,00 → 80,00 | 532,50 → 486,00 | 760,00 → 794,00 |

## Todas as partidas programadas

Tempo médio desde a partida programada até uma chegada válida, em segundos. Para quem ficou pendente ou sofreu teletransporte, a contagem vai até o fim do pico.

| Pico | Semente | Referência → preditivo (s) |
| --- | ---: | ---: |
| manha | 42 | 723,75 → 757,84 |
| manha | 73 | 719,49 → 773,76 |
| tarde | 42 | 725,33 → 715,94 |
| tarde | 73 | 712,63 → 721,08 |

## Pedestres simulados na XV de Novembro

| Pico | Semente | Percursos comuns | Duração média (s) | P95 (s) |
| --- | ---: | ---: | ---: | ---: |
| manha | 42 | 659 | 77,51 → 77,51 | 120,00 → 120,00 |
| manha | 73 | 659 | 76,63 → 76,63 | 117,10 → 117,10 |
| tarde | 42 | 2565 | 81,36 → 81,27 | 122,00 → 122,00 |
| tarde | 73 | 2566 | 81,29 → 81,13 | 122,00 → 121,00 |

## Aderência da referência aos dados locais

| Pico | Semente | Ônibus pareados | Mediana GPS (s) | Mediana SUMO (s) | Erro pareado mediano (s) | Erro absoluto mediano (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| manha | 42 | 1259/1448 | 550 | 478.0 | -32.0 | 166.0 |
| manha | 73 | 1270/1448 | 560.0 | 484.0 | -29.5 | 162.0 |
| tarde | 42 | 1295/1465 | 485 | 375.0 | -64.0 | 172.0 |
| tarde | 73 | 1296/1465 | 487.5 | 377.0 | -72.5 | 169.0 |

O pareamento usa a duração do episódio de GPS usado na reconstrução da rota e a duração simulada do mesmo ônibus na referência.
Os volumes absolutos de carros foram assumidos. As medianas TomTom dos picos limitam a velocidade desejada e já incorporam efeitos do congestionamento observado. Filas e sinais do SUMO podem acrescentar atraso sobre esse efeito.

| Pico | Episódios de GPS na demanda | Paradas de ônibus codificadas | Intervalos com contagem de campo |
| --- | ---: | ---: | ---: |
| manha | 1448 | 149 | 0 |
| tarde | 1465 | 113 | 0 |

O tempo de embarque depende das paradas detectáveis no GPS. Os planos semafóricos mesclam registros históricos e defasagens inferidas dos tempos de percurso.

P90 e P95 usam interpolação linear. Cada extremo identifica o menor ou maior valor do grupo em cada cenário.
Os valores reportados são resultados do SUMO para a demanda de julho de 2026.

# Comparação com planos semafóricos coordenados em Curitiba

**Complemento aos Marcos 3 e 4 · SUMO 1.28.0**

## Resultados

Frente à Onda Verde estimada da Kennedy, o controle adaptativo reduziu o atraso médio de carros e ônibus, o atraso das viagens BRT comuns e as emissões de CO₂ nos dois picos. O plano coordenado teve a menor fila máxima entre os dois modos nos oito sinais da Kennedy, com a maior diferença à tarde. Frente ao plano histórico adaptado, o controle adaptativo reduziu as filas máximas e o atraso BRT entre 7h e 9h, com um aumento de 0,8% no atraso médio de carros e ônibus.

### Manhã · 6h30–9h

Execuções `m4-manha-fixed`, `onda-manha-kennedy`, `m4-manha-gap`. Atraso BRT calculado sobre 161 viagens concluídas sem teletransporte nos três cenários. O máximo de fila no recorte local considera 8 cruzamentos.

| Indicador | Fixo SUMO | Onda Verde estimada | Adaptativo | Adaptativo × Onda Verde |
| --- | ---: | ---: | ---: | ---: |
| Atraso médio de carros e ônibus (s) | 334,4 | 345,5 | 335,0 | −3,0% |
| Tempo médio de viagem (s) | 718,2 | 729,6 | 718,5 | −1,5% |
| Velocidade média da rede (km/h) | 12,95 | 13,05 | 13,56 | +3,9% |
| Fila média da rede (m) | 4,81 | 4,52 | 4,10 | −9,1% |
| Maior fila da rede (m) | 431,3 | 338,2 | 338,4 | +0,1% |
| Maior fila nos sinais do plano (m) | 28,5 | 41,1 | 42,0 | +2,1% |
| Viagens motorizadas concluídas | 6.368 | 6.416 | 6.457 | +0,6% |
| Atraso nas mesmas viagens BRT (s) | 862,9 | 923,0 | 813,9 | −11,8% |
| Teletransportes | 174 | 138 | 120 | −13,0% |
| CO₂ (kg) | 20.099,5 | 20.019,6 | 19.189,3 | −4,1% |
| CO (kg) | 306,50 | 304,70 | 293,22 | −3,8% |
| NOₓ (kg) | 124,74 | 123,91 | 115,91 | −6,5% |
| HC (kg) | 9,093 | 9,007 | 8,323 | −7,6% |
| PMx (kg) | 3,566 | 3,534 | 3,265 | −7,6% |
| LAeq conjunto (dB(A)) | 67,44 | 67,47 | 67,31 | −0,16 dB |

### Tarde · 17h–19h

Execuções `m4-tarde-fixed`, `onda-tarde-kennedy`, `m4-tarde-transit`. Atraso BRT calculado sobre 221 viagens concluídas sem teletransporte nos três cenários. O máximo de fila no recorte local considera 8 cruzamentos.

| Indicador | Fixo SUMO | Onda Verde estimada | Adaptativo | Adaptativo × Onda Verde |
| --- | ---: | ---: | ---: | ---: |
| Atraso médio de carros e ônibus (s) | 323,7 | 330,5 | 325,2 | −1,6% |
| Tempo médio de viagem (s) | 722,3 | 730,0 | 725,6 | −0,6% |
| Velocidade média da rede (km/h) | 12,17 | 12,05 | 12,26 | +1,7% |
| Fila média da rede (m) | 4,05 | 4,19 | 3,90 | −6,8% |
| Maior fila da rede (m) | 272,8 | 260,4 | 253,6 | −2,6% |
| Maior fila nos sinais do plano (m) | 80,1 | 50,5 | 65,0 | +28,7% |
| Viagens motorizadas concluídas | 5.996 | 6.001 | 6.055 | +0,9% |
| Atraso nas mesmas viagens BRT (s) | 628,2 | 717,2 | 565,5 | −21,2% |
| Teletransportes | 79 | 77 | 60 | −22,1% |
| CO₂ (kg) | 16.188,9 | 16.416,1 | 16.096,8 | −1,9% |
| CO (kg) | 292,79 | 296,23 | 292,90 | −1,1% |
| NOₓ (kg) | 89,20 | 91,22 | 87,82 | −3,7% |
| HC (kg) | 6,534 | 6,699 | 6,413 | −4,3% |
| PMx (kg) | 2,482 | 2,548 | 2,433 | −4,5% |
| LAeq conjunto (dB(A)) | 67,48 | 67,47 | 67,38 | −0,09 dB |

### Plano histórico · 7h–9h

Execuções `m4-manha-fixed`, `onda-manha-setran-2015`, `m4-manha-gap`. Atraso BRT calculado sobre 125 viagens concluídas sem teletransporte nos três cenários. O máximo de fila no recorte local considera 18 nós SUMO associados a 14 cruzamentos da tabela histórica.

| Indicador | Fixo SUMO | Setran 2015 adaptado | Adaptativo | Adaptativo × Setran 2015 |
| --- | ---: | ---: | ---: | ---: |
| Atraso médio de carros e ônibus (s) | 352,6 | 352,0 | 354,6 | +0,8% |
| Tempo médio de viagem (s) | 749,2 | 748,0 | 750,3 | +0,3% |
| Maior fila da rede (m) | 431,3 | 387,8 | 338,4 | −12,7% |
| Maior fila nos sinais do plano (m) | 77,1 | 77,6 | 64,4 | −17,0% |
| Viagens motorizadas concluídas | 5.452 | 5.450 | 5.509 | +1,1% |
| Atraso nas mesmas viagens BRT (s) | 1.004,3 | 1.087,5 | 956,2 | −12,1% |
| CO₂ (kg) | 16.959,5 | 17.113,2 | 16.098,4 | −5,9% |
| CO (kg) | 261,20 | 262,64 | 249,69 | −4,9% |
| NOₓ (kg) | 106,10 | 107,71 | 97,71 | −9,3% |
| HC (kg) | 7,835 | 7,968 | 7,115 | −10,7% |
| PMx (kg) | 3,063 | 3,117 | 2,780 | −10,8% |
| LAeq conjunto (dB(A)) | 67,60 | 67,66 | 67,45 | −0,21 dB |

As variações usam a alternativa coordenada de cada tabela como denominador. O comparativo histórico usa os blocos completos de 7h a 9h. Os indicadores de viagem se referem ao trajeto completo das viagens concluídas nessa janela. A velocidade e a fila média instantânea estão disponíveis para o pico completo nas execuções de referência. A fila máxima usa a mesma definição e os mesmos cruzamentos em cada trio. O LAeq soma a energia antes de converter a média para decibéis, com os mesmos 650 receptores.

## Dados municipais encontrados

Pando e Fuchs publicaram na UTFPR, em 2015, os tempos fornecidos pela Setran para a área semafórica SA-14, no Rebouças. A tabela 9 apresenta o plano de dias úteis das 7h às 9h, com ciclo comum de 90 s, defasagens e verdes de 18 cruzamentos. A Prefeitura também documenta sincronismo entre três sinais para ônibus na Av. Sete de Setembro, mas a publicação descreve a operação sem informar os tempos e as defasagens por cruzamento. A busca nas fontes públicas consultadas não encontrou as programações vigentes de 2026 para os dois corredores e picos. [Pando e Fuchs, tabela 9](https://repositorio.utfpr.edu.br/jspui/bitstream/1/8124/1/CT_ENGCOMP_2015_1_09.pdf#page=77) · [Prefeitura de Curitiba](https://www.curitiba.pr.gov.br/noticias/transporte-coletivo-tem-prioridade-de-passagem-pelos-semaforos-de-canaletas/36786) · [Portal de Dados Abertos](https://dadosabertos.curitiba.pr.gov.br/)

## Cenários e comparabilidade

- **Fixo SUMO.** Mesmos programas da comparação dos Marcos 3 e 4, gerados na rede do projeto com defasagem zero.
- **Onda Verde estimada da Kennedy.** Oito programas da Av. Presidente Kennedy no sentido sudoeste → nordeste, entre Rua Rio de Janeiro e Av. Marechal Floriano Peixoto. A versão atual usa os IDs e as fases da malha do projeto. A defasagem vem da distância acumulada entre cruzamentos, aproximada por segmentos em linha reta em coordenadas da rede, e da hipótese de 50 km/h do projeto original. A diferença entre o tempo de chegada estimado e o início nominal do verde de referência determina a defasagem do ciclo de 90 s. Os estados e as durações são os da malha. [Plano SUMO estimado](../config/signals/onda-verde-kennedy.add.xml)
- **Plano histórico adaptado do Rebouças.** Foi possível representar 14 dos 18 cruzamentos da fonte, em 18 programas SUMO. Alguns cruzamentos históricos correspondem a mais de um controlador na malha. As defasagens da tabela foram referenciadas ao verde da primeira via listada. Os tempos históricos foram usados como proporções para repartir o verde disponível no ciclo de 90 s, mantendo os estados, a sequência e as durações de transição da malha atual. Os cruzamentos 173 e 174 ficaram sem correspondência confirmada. Os cruzamentos 533 e 180 têm fases de conversão que diferem das representadas na malha atual. A adaptação rodou desde 6h30 para iniciar a medição das 7h com tráfego presente. [Plano SUMO adaptado](../config/signals/setran-reboucas-2015.add.xml)
- **Adaptativo por pico.** Resultados já executados do perfil `by-peak`, com presença pela manhã e prioridade BRT seletiva à tarde. O controlador pode atuar em até 85 sinais elegíveis. As intervenções coordenadas operam em recortes menores. A comparação mede o efeito de cada cenário na rede com sua cobertura específica. [Relatório executivo M4](relatorio-m4.md)

As repetições usam a mesma rede, os mesmos arquivos de demanda, limites, semente 42 e janelas de julho de 2026 dos Marcos 3 e 4. O SHA-256 identifica a rede, a demanda e os alvos de velocidade comuns e registra o plano adicional. O TraCI confirmou o programa, a fase inicial e o momento da primeira troca em todos os sinais com defasagens experimentais. As três simulações mantêm o restante da malha no plano fixo do SUMO. [Carregamento de programas no SUMO](https://eclipse.dev/sumo/docs/Simulation/Traffic_Lights.html)

## Reprodução

```powershell
python -m ca replay mensal-2026-07-manha-20261119-235229-202742 --name nova-onda-manha --control fixed --signals config/signals/onda-verde-kennedy.add.xml --summary-only
python -m ca replay mensal-2026-07-tarde-20261119-235229-202742 --name nova-onda-tarde --control fixed --signals config/signals/onda-verde-kennedy.add.xml --summary-only
python -m ca replay mensal-2026-07-manha-20261119-235229-202742 --name novo-setran-manha --control fixed --signals config/signals/setran-reboucas-2015.add.xml --summary-only
```

## Pedido dos planos municipais de 2026

A Prefeitura recebe pedidos pelo SIC com acesso pelo e-Cidadão. O texto abaixo especifica os arquivos necessários para repetir a comparação com a operação real. [Serviço de Informação ao Cidadão](https://www.curitiba.pr.gov.br/conteudo/guia-de-uso-lei-de-acesso-a-informacao/3474)

> Para reprodução em simulação acadêmica, solicito cópia dos planos semafóricos existentes para dias úteis nos picos de 6h30–9h e 17h–19h na Av. Presidente Kennedy, entre a Rua Rio de Janeiro e a Av. Marechal Floriano Peixoto, e na Av. Sete de Setembro, no trecho com sincronismo dos semáforos entre estações do BRT. Solicito os planos vigentes em 31/07/2026 e, caso tenham mudado, os planos vigentes na data da resposta, com ciclo, ordem e duração de estágios, defasagens e sua referência, horários de ativação, identificação de cruzamentos e movimentos por sentido. Solicito também o registro existente das regras de prioridade para ônibus nos trechos indicados. Se disponível, peço o envio no formato digital já utilizado pela Setran.

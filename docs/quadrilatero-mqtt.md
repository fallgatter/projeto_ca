# Controle do Quadrilátero por câmeras virtuais e MQTT

## Referência e critério de escolha

O experimento usa toda a malha do Quadrilátero Central de Curitiba. A referência combina a Onda Verde reconstruída para oito semáforos da Avenida Presidente Kennedy com os programas fixos do SUMO nos demais sinais. O objetivo principal é reduzir os segundos perdidos por viagem de carro ou ônibus. Para interpretar essa média, acompanhamos também viagens concluídas, veículos teletransportados, filas na rede e na Kennedy, atraso do BRT, pedestres, bicicletas e CO₂. [Origem da Onda Verde](onda-verde.md)

Em cada pico, os controladores recebem o mesmo arquivo de viagens de 31 de julho de 2026, com medianas mensais do TomTom e GPS da URBS. Cada cenário cobre 6h30–9h ou 17h–19h. Os arquivos de cada par têm as mesmas assinaturas de malha, demanda, velocidades e plano semafórico. A semente 42 permite comparar com as alternativas já avaliadas. A semente 73 repete as partidas e altera a aleatoriedade interna do SUMO. O desenho mede sensibilidade à simulação dentro de um dia de demanda.

## Integração da Kennedy ao controle MQTT

O modo `mqtt-adaptive` inclui as oito interseções com o programa `kennedy50` junto aos 82 sinais elegíveis do restante da rede. Para a Kennedy, o controlador calcula o horário nominal de fim do verde longo da avenida a partir das defasagens do plano e do ciclo de referência de 90 s. Na janela final de 10 s, o mesmo broker recebe as observações de demanda e devolve a decisão para cada cruzamento.

A política escolhe terminar o verde da avenida 4 s antes, no horário nominal ou 4 s depois. Usa a fila com espaço para escoar, a demanda da fase concorrente e a presença de BRT. A diferença em relação ao plano pode ir de −4 s a +4 s. Se o horário anterior estava em um extremo e a nova observação pede o outro, a mudança na duração do verde chega a 8 s. O atuador verifica o limite a cada ciclo com o relógio nominal como referência, evitando acumular defasagens. Se o MQTT não devolver uma decisão a tempo, o SUMO executa a troca já programada.

A atuação na Kennedy se limita a um verde veicular longo por ciclo. Em alguns sinais, o verde longo atende veículos e pedestres em paralelo. O encurtamento desse verde no SUMO é de até 8 s. A ordem das fases, os amarelos, os vermelhos integrais e as fases curtas de travessia ou liberação seguem o plano original. O campo `signal_control.kennedy_signals` de `summary.json` registra observações, encurtamentos, extensões e desvio aplicado por sinal.

### Resultados com a Kennedy integrada

Os quatro replays completos usaram as mesmas rotas, velocidades, malha, plano inicial e sementes dos ensaios históricos. Em cada replay, os oito sinais da Kennedy enviaram observações e foram avaliados pelo MQTT, com pelo menos uma mudança em quatro a sete sinais. No conjunto dos quatro replays, houve 393 mudanças de verde no corredor e nenhum lote sem resposta. O teste com decisões controladas também confirmou no SUMO que os oito sinais podem variar o fim do verde e que as demais fases cumprem suas durações programadas.

| Pico · semente | Atraso no plano fixo (s) | Atraso no MQTT com Kennedy fixa (s) | Atraso no MQTT integrado (s) | Maior fila da rede, MQTT anterior → integrado (m) | Veículos teletransportados, MQTT anterior → integrado | Sinais da Kennedy com alteração |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Manhã · 42 | 345,5 | 329,3 | 323,0 | 416,8 → 431,3 | 142 → 165 | 6/8 |
| Manhã · 73 | 344,9 | 320,9 | 330,4 | 340,0 → 387,8 | 162 → 166 | 6/8 |
| Tarde · 42 | 330,5 | 320,8 | 319,1 | 271,1 → 325,7 | 74 → 90 | 4/8 |
| Tarde · 73 | 332,4 | 317,5 | 313,4 | 252,0 → 264,1 | 81 → 80 | 7/8 |

O MQTT integrado reduziu o atraso médio em 3,4% a 6,5% frente ao plano fixo. Frente ao MQTT com a Kennedy fixa, o atraso caiu em três dos quatro pares, a maior fila da rede cresceu nos quatro e houve menos viagens concluídas nos quatro. A contagem de veículos teletransportados cresceu em três pares. O maior ganho adicional de atraso foi de 6,3 s por viagem na manhã da semente 42, enquanto a manhã da semente 73 perdeu 9,5 s por viagem.

As execuções estão em `runs/kennedy-integrada-{manha,tarde}-mqtt-s{42,73}`. No painel, elas aparecem com o sufixo **MQTT em 8 sinais da Kennedy**.

## Resultados históricos com a Kennedy fixa

Os quatro pares completos usam SUMO e um broker MQTT 5 local MQTTools 0.50.0. Em cada célula, a seta indica Onda Verde fixa → controle MQTT. O atraso e a fila média caíram nos quatro pares. A maior fila da rede subiu em três deles. A redução no atraso também aparece quando se comparam somente viagens presentes nos dois cenários.

| Pico · semente | Atraso (s) | Variação | Fila média (m) | Fila máxima (m) | Conclusões motorizadas | Veículos teletransportados |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Manhã · 42 | 345,5 → 329,3 | -4,7% | 4,52 → 4,16 | 338,2 → 416,8 | 6.416 → 6.419 | 138 → 142 |
| Tarde · 42 | 330,5 → 320,8 | -2,9% | 4,19 → 3,96 | 260,4 → 271,1 | 6.001 → 6.024 | 77 → 74 |
| Manhã · 73 | 344,9 → 320,9 | -6,9% | 4,55 → 4,36 | 338,2 → 340,0 | 6.395 → 6.406 | 162 → 162 |
| Tarde · 73 | 332,4 → 317,5 | -4,5% | 4,14 → 3,86 | 260,5 → 252,0 | 6.025 → 6.019 | 62 → 81 |

| Pico · semente | Viagens motorizadas comuns | Atraso nessas viagens (s) | Viagens BRT comuns | Atraso nesses BRTs (s) | Fila máxima na Kennedy (m) | CO₂ (kg) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Manhã · 42 | 6.319 | 331,6 → 312,8 | 188 | 1.086,5 → 973,7 | 41,1 → 35,0 | 20.020 → 19.435 |
| Tarde · 42 | 5.917 | 322,6 → 309,3 | 224 | 720,0 → 690,6 | 50,5 → 31,8 | 16.416 → 16.141 |
| Manhã · 73 | 6.277 | 321,3 → 305,5 | 169 | 997,6 → 796,6 | 35,0 → 28,0 | 19.966 → 19.652 |
| Tarde · 73 | 5.929 | 322,6 → 309,6 | 236 | 719,7 → 640,0 | 72,6 → 43,0 | 16.297 → 16.022 |

| Pico · semente | Lotes publicados | Lotes sem resposta | Verdes encurtados | Verdes estendidos | Espera de pedestres (s) | Bicicletas concluídas |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Manhã · 42 | 8.902 | 0 | 14.141 | 43 | 39,14 → 39,14 | 80 → 80 |
| Tarde · 42 | 7.114 | 0 | 11.271 | 35 | 39,48 → 39,72 | 64 → 64 |
| Manhã · 73 | 8.909 | 0 | 14.115 | 56 | 38,37 → 38,37 | 80 → 80 |
| Tarde · 73 | 7.120 | 0 | 11.239 | 49 | 39,65 → 39,67 | 64 → 64 |

O alcance foi de 82 semáforos elegíveis. O modo local `feedback` ainda teve menor atraso médio que o novo modo MQTT nos dois picos da semente 42. Já o MQTT teve menor fila média nos dois. A manhã com semente 42 merece atenção especial pela fila máxima de 416,8 m. À tarde com semente 73, os teletransportes aumentaram de 62 para 81, com seis viagens concluídas a menos. A escolha da política depende de quanto se aceita concentrar fila para reduzir o atraso médio.

As execuções adaptativas estão em `runs/quadrilatero-{manha,tarde}-mqtt` e nas pastas de mesmo nome terminadas em `-s73`. As referências fixas são `onda-{manha,tarde}-kennedy` e `quadrilatero-{manha,tarde}-fixed-s73`. O pareamento usa somente viagens concluídas sem teletransporte nos dois braços de cada par. As duas sementes cobrem a mesma demanda e os detectores são ideais.

## Plano para implementar o modelo simples

**Hipótese a testar.** Se o verde atual estiver vazio e houver um veículo aguardando a próxima fase, antecipar a troca pode recuperar parte do atraso perdido. Nos quatro ensaios do controlador completo, 50.766 das 50.949 intervenções encurtaram verdes. Essa contagem motiva testar a antecipação isoladamente. Só o novo ensaio vai mostrar quanto ela explica do ganho.

1. **Definir a política `mqtt-simple`.** Usar apenas presença na aproximação verde atual e fila na próxima fase motorizada prevista. A decisão é manter ou finalizar o verde em 1 s. Uma câmera cobrindo as faixas de entrada, ou detectores de presença por faixa, fornece as duas observações. Começar com os sensores virtuais que já existem.
2. **Reaproveitar os contadores do SUMO.** Em `ca/mqtt_feedback.py`, montar `current_present` com qualquer veículo no detector de 70 m das faixas verdes atuais. Montar `next_waiting` com ao menos um veículo abaixo de 2 m/s nos 70 m das faixas que ganham verde na próxima fase. Excluir as faixas já servidas no verde atual para evitar uma troca sem benefício. Levar esses dois booleanos, a fase, o tempo restante e `can_shorten` no lote da política simples. A primeira versão dispensa identificação de ônibus, ocupação da saída e treinamento.
3. **Ligar a regra ao MQTT existente.** Passar a função de decisão para `MqttLoop` na criação do cliente e selecioná-la em `ca/signals.py`. Registrar o modo e o rótulo em `ca/signal_control.py`. Fazer `ca/simulate.py` e a validação de `ca/__main__.py` reconhecerem ambos os modos MQTT. Reutilizar tópicos, validação de fase, tempo mínimo, proteção da Kennedy, transições e tratamento de respostas perdidas. Manter a Onda Verde fixa como padrão de referência.
4. **Testar a decisão e o caminho completo.** Com 8 s restantes, verde mínimo cumprido, aproximação vazia e alguém esperando na próxima fase, a resposta deve ser `-7` s. Com veículo chegando no verde, próxima fase vazia ou mínimo ainda em curso, deve ser `0`. Cobrir fase vencida e resposta ausente nos testes do atuador. Em uma janela curta de desenvolvimento com `simulate --start ... --end ...`, verificar que houve observações, respostas e ao menos um encurtamento sob demanda apropriada.
5. **Comparar os três modos.** Repetir os dois picos com sementes 42 e 73 usando `--control mqtt-simple`, os arquivos de origem e o plano da seção de reprodução. Comparar com o fixo e com `mqtt-adaptive` em cada par. Anotar atraso nas mesmas viagens, fila média e máxima, conclusões, teletransportes e espera de pedestres. Na semente 42, os alvos de referência para o atraso geral são 345,5 s de manhã e 330,5 s à tarde no fixo, contra 329,3 s e 320,8 s no MQTT completo.

```python
def simple_action(row):
    if row['can_shorten'] and not row['current_present'] and row['next_waiting']:
        return 1 - row['remaining_s']
    return 0
```

**Critério de escolha sugerido.** Verificar se o atraso cai nos dois picos e se o sinal do ganho se mantém na segunda semente. Se a média cair enquanto aumentam filas máximas ou teletransportes, localizar o cruzamento e verificar a capacidade da saída antes de acrescentar outra regra. Se o objetivo seguinte for regularidade do BRT, testar a extensão seletiva como uma segunda mudança isolada.

**Primeira tarefa para um assistente de código menor.** “Em `ca/mqtt_feedback.py`, implemente a função pura `simple_action(row)` conforme o plano. Em `tests/test_mqtt_feedback.py`, teste os quatro casos da etapa 4. Deixe a integração MQTT para a próxima tarefa.” Em seguida, use uma etapa por solicitação e exija o resultado dos testes antes de passar à avaliação.

## Da observação à próxima decisão

1. A cada segundo, o TraCI observa os veículos em cada faixa. Até 70 m antes da retenção, o detector conta veículos em aproximação e veículos com velocidade abaixo de 2 m/s. Um ônibus em parada programada fica fora dessa contagem. Nas saídas, a soma de comprimentos ocupados, com 2,5 m por veículo para espaçamento, estima a fração da faixa ocupada. O BRT é identificado pela linha e pelo movimento previsto até 50 m antes do sinal.
2. O cliente que representa os cruzamentos calcula a demanda de cada fase como a soma dos veículos lentos mais 0,35 por veículo em aproximação. Para estimar a demanda que pode escoar, multiplica a demanda de cada entrada pela fração livre média das suas saídas. Ele publica as observações das fases elegíveis em lote. Isso permite comparar um verde com fila e saída livre a outro em que a fila está presa a jusante.
3. Um segundo cliente recebe o lote pelo broker. Recomenda encerrar o verde após o próximo segundo quando a aproximação está vazia, quando a saída bloqueia o escoamento e há demanda concorrente, quando a próxima fase tem demanda atendível muito maior, ou quando ela pode servir um BRT. Um BRT atendível no verde atual tem prioridade. Perto da troca, a política pode acrescentar 6 s para um BRT ou para uma fila com espaço e pressão dominante.
4. Nos sinais fora da Kennedy, o atuador aceita uma alteração por ocorrência de verde, confirma a fase e respeita o mínimo do modelo (60% do nominal, limitado a 12 s como limiar) e o máximo do nominal mais 6 s. Em caso de perda da resposta, o SUMO segue a troca já programada. A próxima leitura realimenta o controle. Na Kennedy, vale a regra de horário de fim do verde longo descrita acima.

As decisões são reavaliadas a cada 3 s simulados durante verdes elegíveis até a primeira alteração. A política admite extensão nos últimos 3 s. Para antecipação por pressão, exige pressão concorrente de pelo menos 1 e escoamento atual abaixo de 45% da demanda, ou pressão concorrente maior que o dobro da atual mais 2. Para prolongar um verde por fila, exige pressão atual de pelo menos 3 e superior ao dobro da concorrente, sem BRT elegível na próxima fase. Para o BRT, ao menos uma saída do movimento deve estar abaixo de 72% de ocupação. Esses limiares são hipóteses do experimento.

### Transporte e reprodução

O modo `mqtt-adaptive` inicia os dois clientes no mesmo processo. Os dois sentidos passam pelo broker MQTT 5 local. O tópico `curitiba/v1/{run}/adaptive/observations` leva a sessão, o segundo simulado e as observações por sinal. Em `curitiba/v1/{run}/adaptive/decisions`, cada sinal solicitado vem com o índice da fase e a variação do verde em segundos. Os lotes usam QoS 0, sem retenção. A confirmação da política pode conter zero ações. O atuador aguarda até 500 ms de relógio real, descarta respostas atrasadas, de outra sessão ou duplicadas e registra lotes perdidos. O relógio da simulação fica parado durante a troca. Latência de um sistema físico precisa de um ensaio próprio.

Em um terminal, inicie um broker local MQTT 5. A configuração do projeto liga o Mosquitto apenas ao loopback.

```powershell
mosquitto -c config/mosquitto.conf
```

Em outro terminal com as dependências do projeto, os comandos abaixo reproduzem os pares fixo e adaptativo com os dados locais de julho de 2026. Cada nome de execução precisa estar livre. O exemplo usa a semente 73. Para a semente original, use 42 nos dois braços e ajuste o nome. Os arquivos de rotas permanecem os mesmos ao mudar a semente do SUMO.

```powershell
foreach ($pico in 'manha', 'tarde') {
    $origem = "mensal-2026-07-${pico}-20261119-235229-202742"
    $plano = 'config/signals/onda-verde-kennedy.add.xml'
    python -m ca replay $origem --name "ensaio-${pico}-fixo-73" --signals $plano --control fixed --sumo-seed 73 --summary-only
    python -m ca replay $origem --name "ensaio-${pico}-mqtt-73" --signals $plano --control mqtt-adaptive --mqtt 127.0.0.1:1883 --sumo-seed 73 --summary-only
}
python -m ca serve
```

No painel, compare **Como está hoje** e **Melhor resultado** nos mapas lado a lado. A barra de reprodução controla os dois mapas, e o quadro **Indicadores** resume o pico completo. O painel escolhe o par com a maior redução relativa de atraso médio de carros e ônibus entre os replays com os oito sinais da Kennedy integrados ao MQTT. O par usa a mesma origem, malha, rotas, velocidades, plano e semente. [Instalação e preparação dos dados](../README.md)

## Alternativas avaliadas e pesquisadas

Os replays arquivados da semente 42 já permitem comparar sete estratégias sobre a mesma Onda Verde. A fila é a média temporal dos comprimentos medidos por cruzamento. O atraso médio considera viagens motorizadas concluídas sem teletransporte no pico. Por isso, o número de conclusões e os veículos que o SUMO precisou reposicionar entram na leitura de cada resultado.

| Controle | Atraso manhã (s) | Atraso tarde (s) | Fila manhã / tarde (m) | Conclusões manhã / tarde | Veículos teletransportados manhã / tarde |
| --- | ---: | ---: | ---: | ---: | ---: |
| Onda Verde fixa | 345,49 | 330,48 | 4,52 / 4,19 | 6.416 / 6.001 | 138 / 77 |
| Presença de manhã, prioridade BRT à tarde | 318,95 | 325,46 | 4,55 / 4,06 | 6.393 / 6.010 | 169 / 81 |
| Realimentação local por filas e BRT | 324,42 | 315,71 | 4,31 / 3,98 | 6.406 / 6.012 | 160 / 86 |
| Realimentação local seletiva para BRT | 342,83 | 324,27 | 4,17 / 4,11 | 6.421 / 5.962 | 128 / 99 |
| Pressão com ciclo fixo | 340,79 | 331,50 | 4,59 / 4,21 | 6.383 / 6.010 | 171 / 85 |
| Bandit contextual congelado | 346,89 | 324,11 | 4,48 / 4,15 | 6.392 / 6.011 | 155 / 87 |
| Bandit contextual online | 346,56 | 330,12 | 4,45 / 4,29 | 6.390 / 6.003 | 137 / 95 |

Os modelos por ciclo atuam num conjunto mais restrito de sinais. A comparação entre estratégias combina diferenças de cobertura, de ações permitidas e de regra de decisão. [Experimento de aprendizado](controle-aprendido.md) · [Experimento em malha fechada](malha-fechada.md)

### Opções para a próxima rodada de otimização

| Alternativa | Como entraria no Quadrilátero | Evidência disponível |
| --- | --- | --- |
| Atuação por presença e prioridade BRT | Encerrar verde vazio pela manhã ou antecipar a passagem de um BRT à tarde. | O perfil `by-peak` e o modo `feedback` têm resultados salvos para os dois picos. [Comparação local](malha-fechada.md) |
| Controle por pressão | Usar as filas adjacentes ao cruzamento para decidir onde liberar fluxo. A implementação MQTT usa a fração livre das saídas e conserva a ordem de fases do projeto. | A literatura analisa políticas de pressão sob hipóteses específicas de rede. A regra implementada é uma adaptação experimental. [Lioris e Varaiya](https://connected-corridors.berkeley.edu/sites/default/files/Variants%20of%20Max%20Pressure%20Control%20for%20Signalized%20Intersections.pdf) |
| Aprendizado por ciclo | O bandit contextual do projeto aprende quando transferir 8 s entre duas fases. Há versões congelada e online. | Os resultados dependem do pico e da métrica. O modo online piorou a fila máxima da Kennedy à tarde frente ao modelo congelado. [Experimento local](controle-aprendido.md) |
| Aprendizado por reforço com pressão | Usar um agente por cruzamento, com parâmetros compartilhados onde os movimentos forem compatíveis. Testar recompensa por pressão e restringir ações ao verde elegível. | PressLight fundamenta o desenho de estado e recompensa. Um teste local exigiria demandas separadas para treino e avaliação, múltiplas sementes e comparação com a regra determinística usando o mesmo conjunto de ações. [Wei et al., PressLight](https://faculty.ist.psu.edu/jessieli/Publications/2019-KDD-presslight.pdf) · [Ault e Sharon, RESCO](https://openreview.net/pdf?id=LqRSh6V0vR) |
| Previsão de chegada de pelotões | Cada cruzamento comunica aos vizinhos quantos veículos liberou e a previsão de chegada. Na Kennedy, serviria para prever quando uma fila lateral vai bloquear a passagem de um pelotão. | O SURTRAC usa planejamento distribuído com previsões de descarga. Sua avaliação de campo foi feita em Pittsburgh. O ganho em Curitiba precisaria ser medido. [Smith et al., SURTRAC](https://publications.ri.cmu.edu/smart-urban-signal-networks-initial-application-of-the-surtrac-adaptive-traffic-signal-control-system) |

**Revisão do PPO do projeto de referência.** O ambiente em `Sumo-CAmbiente-main/src/rl/env.py` seleciona o primeiro semáforo com várias fases, oferece todos os índices como ações, usa espera local como recompensa e corta o episódio em 3.600 s. A opção `baseline` daquele projeto chama o plano padrão do SUMO, e a Onda Verde usa a opção `green_wave`. Para medir PPO em toda a malha, seria necessário representar os cruzamentos elegíveis, restringir ações, incluir as transições e usar a mesma janela da referência. As medições do novo controle usam a malha e os picos completos de `projeto_ca`.

**Experimento de reforço proposto.** O mesmo lote de observações MQTT pode alimentar uma política aprendida. Em cada sinal, as ações seriam manter, antecipar ou prolongar o verde dentro dos limites já verificados pelo atuador. Uma recompensa inicial seria o negativo dos veículos-segundo em fila nas entradas e nas saídas adjacentes. Avaliar atraso de viagem, demanda ainda sem entrar e viagens pendentes ao fim do pico ajuda a detectar políticas que apenas deslocam filas para fora da área observada. O treino ocorreria em outros dias e níveis de demanda. Na avaliação, a política ficaria congelada, com o mesmo alcance de detecção e os mesmos semáforos elegíveis do controlador MQTT. Um braço adicional com previsões dos pelotões permitiria medir o ganho da comunicação entre cruzamentos.

**Hipótese de implantação.** Câmeras com zonas calibradas por faixa poderiam estimar contagem, velocidade e ocupação de saída. Um serviço embarcado publicaria agregados, e o GPS da frota forneceria linha, aproximação e previsão de chegada do BRT. O experimento usa observações ideais do SUMO. Para dimensionar o ganho de campo, seria preciso medir erro na chuva, à noite e sob oclusão, atraso das mensagens e cobertura das saídas longas. Contagens independentes permitiriam recalibrar a demanda sintética e comparar filas observadas e simuladas.

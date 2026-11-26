# Onda verde senoidal no Quadrilátero de Curitiba

Simulação do Quadrilátero de Curitiba que compara uma onda verde reconstruída com o controle preditivo por série de Fourier e comunicação MQTT. O painel abre com os dois cenários sincronizados. Use as abas **Presidente Kennedy**, **Sete de Setembro**, **Marechal Floriano** ou **Toda a malha**. Os controles permitem saltar no tempo, mudar a velocidade do replay, movimentar os dois mapas e inspecionar um semáforo nas duas simulações. O mapa da direita também mostra as mensagens MQTT entregues entre cruzamentos.

## Abertura do painel

Na raiz do repositório, crie o ambiente Python e instale as dependências. Com os replays disponíveis, inicie o painel:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m onda_verde_senoidal serve
```

Abra [o painel local](http://127.0.0.1:8077). O servidor abre o lote com limites municipais quando o relatório estiver consolidado. Use `serve --profile escalonado` para voltar ao replay com o teto histórico. A reprodução lê posições SUMO a cada 2 s e interpola as posições entre amostras. Os tópicos e horários MQTT vêm dos pacotes que chegaram ao cliente de destino durante a simulação.

Se a instalação no Windows com Python 3.15 falhar por falta de `windows-curses`, instale as dependências usadas pelo painel, pela simulação e pelo broker embutido diretamente:

```powershell
.venv/Scripts/python.exe -m pip install "paho-mqtt>=2,<3" "pyproj>=3.7,<4" tzdata bitstruct humanfriendly
.venv/Scripts/python.exe -m pip install --no-deps mqttools==0.50.0
```

## Demanda escalonada e seleção da ordem

```powershell
.venv/Scripts/python.exe -m onda_verde_senoidal batch --profile escalonado --seeds 101
```

Em cada origem e janela de 15 minutos, os carros são espalhados em posições com fase e variação aleatórias. O espaçamento preserva o número de carros, suas rotas e o volume por origem e janela. Para reduzir lacunas e aglomerações da soma das origens, o escalonador pode deslocar uma partida em até 8 s entre janelas de 5 s, respeitando o bloco original. Os carros que entram pelo perímetro usam a velocidade de inserção segura do SUMO. Ônibus, pedestres e ciclistas mantêm suas partidas. Os semáforos e o trânsito ainda podem formar pelotões durante a circulação. [Inserção de veículos no SUMO](https://eclipse.dev/sumo/docs/Simulation/VehicleInsertion.html)

As ordens candidatas de Fourier são 2, 3, 4 e 6. A semente 17 ajusta os coeficientes e a semente 73 seleciona a ordem com menor erro absoluto médio de fluxo por aproximação. A semente 101, exibida no painel, verifica o erro em uma simulação reservada e compara a onda verde ao controlador com a mesma demanda escalonada. Os parâmetros de espaçamento são experimentais, pois o projeto ainda carece de contagens locais de chegadas.

## Previsões no inspetor

Clique em um semáforo e selecione uma aproximação. O gráfico de 24 horas sobrepõe a curva de Fourier, a previsão corrigida e a média observada móvel de cinco minutos. Logo abaixo, a contagem inteira registra o último minuto, com carros e ônibus separados nos replays gravados com essa informação. A escala vertical usa log(1 + fluxo), com rótulos em veículos por hora. A malha destaca o sentido da aproximação e as barras mostram quanto cada harmônico e a correção somam ou subtraem da previsão no minuto escolhido. Use **Fórmulas e coeficientes** para ver a substituição numérica.

As setas do mapa otimizado partem do remetente e apontam para o receptor. O ponto em movimento representa a mensagem entregue durante a execução.

Em **Preditivo revisado · 5 min**, a correção da demanda de fundo usa até cinco minutos de contagens acumuladas. A diferença entre observado e esperado só contribui além da tolerância de duas vezes a raiz do maior valor entre um e a contagem esperada. A correção continua sendo atualizada a cada minuto. Os veículos detectados e os horários recebidos via MQTT continuam alimentando a previsão de chegadas imediatas. O [relatório da revisão](../docs/revisao-fluxo.md) compara a previsão e os indicadores no SUMO.

O resultado exibe os três KPIs de tráfego do enunciado. A maior fila contínua é medida em metros a partir da linha de retenção, com velocidade abaixo de 0,1 m/s, distância máxima de 10 m entre veículos e exclusão das paradas programadas. As abas das avenidas mostram o tempo médio de permanência na via e a maior fila nas suas aproximações. O atraso médio refere-se às viagens pareadas na malha.

Novas execuções preditivas registram esse histórico automaticamente. O comando abaixo repete um ensaio coordenado arquivado para adicionar o histórico por aproximação. Ele associa as medições ao replay após comparar a configuração, os resultados por veículo, as métricas dos corredores e o resumo do controlador.

```powershell
.venv/Scripts/python.exe -m onda_verde_senoidal monitor manha --seed 101
```

## Referência e recorte

- A simulação mantém todos os segmentos e tipos de usuário da malha do projeto. O mapa desenha os segmentos acessíveis a carros ou ônibus. As rotas de julho de 2026 reaproveitam dados de origem e destino e velocidades TomTom, além de itinerários e GPS URBS/C3SL. As partidas de carro são simuladas.
- A referência reaproveita o plano reconstruído da Kennedy e, no pico da manhã, os programas históricos adaptados da Setran. Três sinais compartilhados adotam o plano histórico pela manhã. Nos demais trechos elegíveis, as defasagens são inferidas do percurso e dos limites de velocidade entre semáforos consecutivos de uma arterial. O algoritmo respeita os ciclos e escolhe uma ligação por vez em caso de restrições concorrentes. Sinais sem uma ligação compatível mantêm a programação fixa da malha. [Planos disponíveis e método de origem](../docs/onda-verde.md)
- O município documenta sincronização da canaleta da Sete de Setembro entre estações. Os horários, offsets e durações municipais vigentes para toda a área ainda precisam de confirmação. A referência representa uma **reconstrução em SUMO**. É possível carregar um arquivo oficial de programas estáticos usando `run --signals` nos dois braços do par. [Prefeitura de Curitiba](https://www.curitiba.pr.gov.br/noticias/transporte-coletivo-tem-prioridade-de-passagem-pelos-semaforos-de-canaletas/36786)
- Os três corredores foram escolhidos pela sua relevância no tráfego e no transporte coletivo. O controle preditivo atua nos cruzamentos elegíveis de toda a malha. Os semáforos elegíveis dos três corredores também recebem previsões dos vizinhos por MQTT. A demanda e a circulação de todas as vias continuam presentes em ambos os cenários.

## Previsão, aprendizado e controle

Por aproximação, o modelo prevê veículos por hora com regressão ponderada. Para ordem H, a fórmula é:

```text
q(t) = max(0, a0 + soma de k = 1 até H de [ak cos(kwt) + bk sen(kwt)])
w = 2π / 24 h
```

Os coeficientes vêm de entradas observadas no SUMO em janelas de 15 minutos, nos picos de 6h30–9h e 17h–19h. O treinamento usa a semente 17. Um perfil diário auxiliar de peso reduzido ancora as horas fora dos picos. A curva dessas horas tem caráter estimado. A regularização cresce com a ordem do harmônico para limitar oscilações quando há poucas observações.

A cada minuto, o controlador atualiza a correção da previsão de Fourier com o erro recente por aproximação. A cada 5 s, em um verde elegível, ele estima as chegadas nos próximos 45 s pela distância e pela velocidade medidas até 160 m do sinal. Incorpora as chegadas anunciadas por MQTT nos corredores e a demanda de fundo estimada pela série de Fourier. Para cada duração candidata do verde, projeta as janelas de atendimento e a espera da fila, considerando uma vazão de uma passagem a cada 2 s por faixa. Aplica a duração com menor custo de espera prevista, com pequena penalidade por retiming. Mantém a ordem de fases, o amarelo e os intervalos exclusivos de travessia. Os verdes elegíveis têm mínimo de 10 s e extensão limitada a 15 s sobre a duração nominal.

A variante **Preditivo coordenado** estima a fração da capacidade das saídas ocupada por veículos parados. Usa 7,5 m por veículo/faixa e reduz a descarga prevista quando a ocupação supera 45%. Na faixa de 240 m em torno dos semáforos da Sete de Setembro, mantém a duração do ciclo e a abertura do verde principal, com transferências compensadas de até 4 s entre dois verdes. A faixa de proteção foi escolhida após observar o aumento das filas no primeiro ensaio preditivo. As duas políticas podem ser comparadas nas mesmas sementes.

### Referências acadêmicas

- Joner e Volpi (2013) estudaram a sincronização de artérias de Curitiba, considerando velocidade, ciclo e defasagem para ampliar a janela de passagem contínua. O trabalho fundamenta a distinção entre manter a progressão ao longo da avenida e reduzir a espera em um único cruzamento. [Artigo na HOLOS](https://doi.org/10.15628/holos.2013.1254)
- Smith, Barlow, Xie e Rubinstein estudaram o compartilhamento de previsões de saída entre cruzamentos no SURTRAC. O nosso cenário usa essa ideia para transmitir o tamanho do pelotão e seu horário previsto de chegada por MQTT. [Artigo do Robotics Institute, Carnegie Mellon](https://publications.ri.cmu.edu/storage/publications/pub_files/2013/6/icaps2013.pdf)
- *Model based urban traffic control, part I* avalia instantes alternativos de troca de sinal por meio de um modelo local de tráfego e um horizonte de previsão. Aqui, o custo comparado entre candidatos é a espera prevista em veículos-segundo. [Publicação no repositório da Universidade de Gante](https://biblio.ugent.be/publication/8638946)
- Aboudolas e colaboradores estudaram a redistribuição de verde em horizonte móvel para controlar filas em Chania. Neste experimento, o horizonte móvel opera no nível do cruzamento, com nova decisão a cada 5 s nos sinais sem proteção da onda verde. [Manuscrito depositado na Universidade de Glasgow](https://eprints.gla.ac.uk/81373/)

## Comparação e visualização

A meta é reduzir em pelo menos 10% o atraso médio SUMO das mesmas viagens concluídas sem teletransporte. Cada pico e semente forma um par independente de cenários. O painel exibe os KPIs dos dois picos da semente 101. Os relatórios trazem média, mediana, mínimo, máximo, P90 e P95 do atraso e da duração das viagens da malha, usando os mesmos IDs em cada par. Os percentis usam interpolação linear sobre a lista ordenada.

A opção **Isolar somente esta via nos dois mapas** filtra a geometria, as aproximações semafóricas, os veículos e as mensagens do corredor selecionado. O replay registra a via pelo segmento SUMO. Dentro do cruzamento, a identificação acompanha o segmento de entrada até o veículo alcançar o segmento de saída.

O seletor **Permanência nesta via** mede a duração das passagens em que o replay observou a entrada e a saída depois do aquecimento. O painel informa o número de passagens de cada cenário. Para verificar a sensibilidade à seleção das viagens concluídas, **Toda a malha** também traz o tempo por partida programada até a chegada válida ou o fim da janela. O relatório inclui durações de pedestres e compara os tempos da referência com os episódios GPS da URBS. Os mesmos episódios orientam a construção das rotas e servem como diagnóstico de aderência.

## Reprodução e resultados

Os ensaios refinados ajustam a aceleração, o intervalo de seguimento e a variação de condução do modelo Krauß. As variantes do preditivo usam a extensão das filas e a disponibilidade das saídas na avaliação das próximas fases. [Parâmetros do SUMO](https://sumo.dlr.de/docs/Car-Following-Models.html) · [Controle por pressão de filas](https://www.sciencedirect.com/science/article/pii/S0968090X13001782)

```powershell
.venv/Scripts/python.exe -m onda_verde_senoidal.improve calibrate
.venv/Scripts/python.exe -m onda_verde_senoidal.improve benchmark --variants revisado pressao progressao filas descarga arteriais prioridade sincronia atuado atuado_prioritario reservas reservas_ciclo
```

Os resultados ficam em `results_refinado/`. O arquivo `KPIS.md` registra a meta de 10% no atraso médio, o tempo na malha e as filas e tempos por via. A seleção compara as variantes na semente 101. A generalização do controlador para outras sementes exige ensaios adicionais.

O perfil `municipal` usa os limites cadastrados pelo GeoCuritiba quando o nome da via e três pontos ao longo do trecho permitem associá-lo a um mesmo limite. Os demais trechos conservam seus limites na malha. As medianas históricas da TomTom são usadas para escolher o multiplicador de demanda da referência por pico. A escolha é feita na semente 17. O relatório registra o erro em vias reservadas e na semente 101. [GeoCuritiba, camada Trecho de Arruamento](https://geocuritiba.ippuc.org.br/server/rest/services/GeoCuritiba/Publico_Interno_GeoCuritiba_BaseCartografica_para_BC/MapServer/76)

```powershell
.venv/Scripts/python.exe -m onda_verde_senoidal.road_limits onda_verde_senoidal/results_calibrado/limites-geocuritiba.geojson
.venv/Scripts/python.exe -m onda_verde_senoidal calibrate
.venv/Scripts/python.exe -m onda_verde_senoidal batch --profile municipal --seeds 101 --policies revisado
```

Os novos replays ficam em `results_municipal/`, junto com `CALIBRACAO.md` e `REVISAO.md`. Os dois braços usam o mesmo arquivo de rotas e a mesma velocidade limite. O perfil `calibrado` serve para comparar o ajuste com a malha anterior, sem a atualização de limites. Os replays com o teto histórico da TomTom continuam disponíveis em `results_fluxo/`.

Para gerar os replays em um checkout novo, instale o SUMO e coloque-o no `PATH` ou configure `SUMO_HOME`. Copie os insumos das execuções de julho de 2026 para estes caminhos:

| Insumo | Caminho na raiz do repositório |
| --- | --- |
| Rede SUMO | `data/cache/network/curitiba.net.xml` |
| Demanda, metadados e alvos de velocidade da manhã | `runs/mensal-2026-07-manha-20261119-235229-202742/` |
| Demanda, metadados e alvos de velocidade da tarde | `runs/mensal-2026-07-tarde-20261119-235229-202742/` |

Cada pasta mensal deve conter `demand.rou.xml`, `metadata.json` e `traffic-targets.json`. O relatório também utiliza `bus-journeys.json` quando disponível. Esses insumos e os replays são locais e ficam fora do Git. Para abrir o painel com replays já gerados, basta copiar a pasta `onda_verde_senoidal/results_fluxo/` para o mesmo caminho no checkout novo.

Para gerar a comparação revisada dos dois picos na semente 101:

```powershell
.venv/Scripts/python.exe -m onda_verde_senoidal batch --profile escalonado --seeds 101 --policies coordenado revisado
```

O lote usa o broker local MQTT 5 e retoma a partir dos cenários que ainda estiverem pendentes. Por padrão, lê a rede em `data/cache/network/curitiba.net.xml` e as execuções mensais `mensal-2026-07-{manha,tarde}-20261119-235229-202742`. A ajuda de `run` lista opções para caminhos alternativos, broker e planos semafóricos. A opção `--signals` precisa ser aplicada também ao treino para recalibrar a previsão sob outro plano. A consolidação verifica os hashes da rede, das rotas, dos alvos de velocidade e do plano inicial em cada par.

Consulte [as tabelas do experimento](../docs/resultados.md) ou selecione o pico e a via no painel. O atraso da rede compara as mesmas viagens concluídas sem teletransporte. O relatório também abrange tempo parado, velocidade e frequência de paradas após cinco minutos de aquecimento. O limiar de parada é 1 m/s. O tempo parado inclui embarque programado dos ônibus e cada entrada conta um segmento percorrido.

As sementes 42 e 73 foram usadas para comparar as políticas e ajustar a proteção da Sete. A semente 101 foi reservada para avaliar a política coordenada já definida nos dois picos. Ela varia a aleatoriedade microscópica do SUMO sobre as mesmas rotas. Os dados da primeira versão preditiva estão [no relatório do ensaio inicial](../docs/mpc-inicial.md).

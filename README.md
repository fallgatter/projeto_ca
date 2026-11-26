# Painel Onda Verde · Quadrilátero de Curitiba

Dashboard de replay que compara a onda verde de referência com o controle preditivo. Os mapas sincronizados mostram carros, ônibus, semáforos e mensagens MQTT registradas na simulação.

## Abrir o painel

Na raiz do repositório, execute com Python 3.10 ou superior:

```powershell
python -m onda_verde_senoidal.server
```

Abra [o painel local](http://127.0.0.1:8077). O servidor usa somente a biblioteca padrão do Python.

O servidor procura os replays locais da semente 101 em `onda_verde_senoidal/results_refinado/`, `onda_verde_senoidal/results_municipal/`, `onda_verde_senoidal/results_calibrado/` e `onda_verde_senoidal/results_fluxo/`, nessa ordem. Em outra máquina, copie a pasta desejada para o mesmo caminho ou indique sua localização com `--data CAMINHO`. A pasta deve conter `map.json`, `report.json`, `fourier.json` e os replays dos dois picos, nas subpastas `manha/` e `tarde/`.

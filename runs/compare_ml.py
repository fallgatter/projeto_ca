import json
from pathlib import Path
from statistics import mean
from xml.etree.ElementTree import parse

from ca.io import read_json
from ca.metrics import signal_kpis
from ca.results import RunResults


store = RunResults()
codes = frozenset(read_json('config/curitiba.json')['brt_lines'])
wave = parse('config/signals/onda-verde-kennedy.add.xml')
signals = {p.get('id') for p in wave.getroot().findall('tlLogic')}
alternatives = ('ml', 'cycle-pressure', 'by-peak')
measures = (
    ('Atraso médio de carros e ônibus (s)', 'delay_s', 1, -1),
    ('Tempo médio de viagem (s)', 'travel_s', 1, -1),
    ('Velocidade média da rede (km/h)', 'speed_kmh', 2, 1),
    ('Fila média da rede (m)', 'mean_queue_m', 2, -1),
    ('Maior fila da rede (m)', 'peak_queue_m', 1, -1),
    ('Maior fila nos oito sinais da Kennedy (m)', 'kennedy_queue_m', 1, -1),
    ('Viagens motorizadas concluídas', 'completed', 0, 1),
    ('Teletransportes', 'teleports', 0, -1),
    ('Atraso nas mesmas viagens BRT (s)', 'paired_brt_s', 1, -1),
    ('Viagens BRT concluídas', 'brt_completed', 0, 1),
    ('Travessias monitoradas', 'ped_crossings', 0, 1),
    ('Viagens a pé concluídas', 'ped_completed', 0, 1),
    ('Espera média de pedestres (s)', 'ped_wait_s', 2, -1),
    ('Viagens de bicicleta concluídas', 'bike_completed', 0, 1),
    ('CO₂ (kg)', 'co2', 1, -1),
    ('CO (kg)', 'co', 2, -1),
    ('NOₓ (kg)', 'nox', 2, -1),
    ('HC (kg)', 'hc', 3, -1),
    ('PMx (kg)', 'pmx', 3, -1),
    ('LAeq conjunto em 650 receptores (dB(A))', 'laeq_dba', 2, -1),
)


def display(value, precision):
    return f'{value:,.{precision}f}'.replace(',', '|').replace('.', ',').replace('|', '.')


def compare(peak, duration):
    runs = (f'onda-{peak}-kennedy', *(f'apr-{peak}-{alt}' for alt in alternatives))
    meta = [store.data(r, 'metadata.json') for r in runs]
    summary = [store.data(r, 'summary.json') for r in runs]
    trained = store.data(f'treino-{peak}-ml', 'metadata.json')
    assert trained['inputs_sha256']['demand'] != meta[0]['inputs_sha256']['demand']
    assert len({m['reference_run'] for m in meta}) == 1
    for m, s in zip(meta, summary):
        assert m['inputs_sha256'] == meta[0]['inputs_sha256']
        assert s['totals']['duration_s'] == duration
    nodes = store.data(runs[0], 'map.json')['intersections']
    affected = {n for n, row in nodes.items() if signals.intersection(row['signal_ids'])}
    assert len(affected) == 8
    out = []
    losses = []
    for r, s in zip(runs, summary):
        assert store.data(r, 'status.json')['state'] == 'complete'
        assert store.data(r, 'map.json')['intersections'].keys() == nodes.keys()
        if s['signal_control']['strategy'] in ('ml', 'cycle-pressure'):
            assert s['signal_control']['green_adjustments'] > 0, s['signal_control']
            assert not s['signal_control']['cycle_timing_errors']
        x = signal_kpis(s, nodes)
        x['kennedy_queue_m'] = max(s['totals']['intersections'].get(n, {}).get('peak_queue_m', 0) for n in affected)
        out.append(x)
        brt = {j['id'] for j in store.data(r, 'bus-journeys.json')['journeys'] if j['line_id'] in codes}
        losses.append(store.brt_delays(r, s, brt))
    shared = set.intersection(*(set(loss) for loss in losses))
    for x, ls in zip(out, losses):
        x['paired_brt_s'] = mean(ls[j] for j in shared)
    stats = [s['signal_control'] for s in summary]
    return out, stats, len(shared)


tables = ['## Resultados dos picos pareados']
for peak, duration, name in (('manha', 9000, 'Manhã'), ('tarde', 7200, 'Tarde')):
    measures_by_run, stats, matched = compare(peak, duration)
    tables.extend(['', f'### {name}', '',
                   f'A comparação BRT usa {matched} viagens concluídas sem teletransporte nos quatro cenários. '
                   f'O modelo recebeu {stats[1]["trained_samples"]} amostras de treino, atuou em até '
                   f'{stats[1]["controlled_signals"]} sinais elegíveis e executou {stats[1]["green_adjustments"]} alterações de verde.',
                   '',
                   '| Indicador | Onda Verde | ML | Pressão com ciclo fixo | Regras por pico |',
                   '| --- | ---: | ---: | ---: | ---: |'])
    for label, key, precision, _ in measures:
        values = [display(x[key], precision) for x in measures_by_run]
        tables.append('| ' + ' | '.join([label, *values]) + ' |')
    print(peak, json.dumps(measures_by_run, ensure_ascii=False))
    print(peak, 'atuações', stats)
    base = measures_by_run[0]
    for alt, candidate in zip(alternatives, measures_by_run[1:]):
        change = {key: 100 * (candidate[key]-base[key])/base[key] for _, key, _, _ in measures}
        wins = [key for _, key, _, sign in measures if sign*change[key] > 0.001]
        losses = [key for _, key, _, sign in measures if sign*change[key] < -0.001]
        print(peak, alt, len(wins), len(losses), {k: round(v, 3) for k,v in change.items()})

report = Path('docs/controle-aprendido.md')
data = report.read_text(encoding='utf-8')
assert '<!-- RESULTADOS_APRENDIZADO -->' in data
report.write_text(data.replace('<!-- RESULTADOS_APRENDIZADO -->', '\n'.join(tables)), encoding='utf-8')

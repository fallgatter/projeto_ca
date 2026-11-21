from pathlib import Path
from statistics import mean
from xml.etree.ElementTree import parse

from ca.io import read_json
from ca.metrics import signal_kpis
from ca.results import RunResults


store = RunResults()
brt_codes = set(read_json('config/curitiba.json')['brt_lines'])
plan = parse('config/signals/onda-verde-kennedy.add.xml')
plan_signals = {p.get('id') for p in plan.getroot().findall('tlLogic')}
metrics = (
    ('Atraso médio de carros e ônibus (s)', 'delay_s', 1),
    ('Tempo médio de viagem (s)', 'travel_s', 1),
    ('Velocidade média da rede (km/h)', 'speed_kmh', 2),
    ('Fila média da rede (m)', 'mean_queue_m', 2),
    ('Maior fila da rede (m)', 'peak_queue_m', 1),
    ('Maior fila nos oito sinais da Kennedy (m)', 'kennedy_queue_m', 1),
    ('Viagens motorizadas concluídas', 'completed', 0),
    ('Teletransportes', 'teleports', 0),
    ('Atraso nas mesmas viagens BRT (s)', 'same_brt_delay_s', 1),
    ('Viagens BRT concluídas', 'brt_completed', 0),
    ('Travessias monitoradas', 'ped_crossings', 0),
    ('Viagens a pé concluídas', 'ped_completed', 0),
    ('Espera média de pedestres (s)', 'ped_wait_s', 2),
    ('Viagens de bicicleta concluídas', 'bike_completed', 0),
    ('CO₂ (kg)', 'co2', 1),
    ('CO (kg)', 'co', 2),
    ('NOₓ (kg)', 'nox', 2),
    ('HC (kg)', 'hc', 3),
    ('PMx (kg)', 'pmx', 3),
    ('LAeq conjunto (dB(A))', 'laeq_dba', 2),
)


def fmt(value, precision=1, signed=False):
    rounded = round(value, precision)
    prefix = '−' if rounded < 0 else '+' if rounded > 0 and signed else ''
    return prefix + f'{abs(rounded):,.{precision}f}'.replace(',', '|').replace('.', ',').replace('|', '.')


sections = ['### Comparação online × congelado', '',
            'As duas execuções de ML partem do mesmo modelo por pico. A Onda Verde, as rotas, a semente e os limites '
            'de velocidade são idênticos. As viagens BRT foram pareadas nos três cenários de cada pico.']

for peak, name, duration in [('manha', 'Manhã', 9000), ('tarde', 'Tarde', 7200)]:
    runs = [f'onda-{peak}-kennedy', f'apr-{peak}-ml', f'apr-{peak}-ml-online']
    metadata = [store.data(r, 'metadata.json') for r in runs]
    assert all(meta['inputs_sha256'] == metadata[0]['inputs_sha256'] for meta in metadata)
    models = [meta['signal_control'].get('model_sha256') for meta in metadata[1:]]
    assert models[0] and models[0] == models[1]
    nodes = store.data(runs[0], 'map.json')['intersections']
    kennedy = {n for n, row in nodes.items() if plan_signals.intersection(row['signal_ids'])}
    aggregates, losses = [], []
    for run in runs:
        assert store.data(run, 'status.json')['state'] == 'complete'
        s = store.data(run, 'summary.json')
        assert s['totals']['duration_s'] == duration
        values = signal_kpis(s, nodes)
        values['kennedy_queue_m'] = max(s['totals']['intersections'].get(n, {}).get('peak_queue_m', 0) for n in kennedy)
        aggregates.append(values)
        journeys = store.data(run, 'bus-journeys.json')['journeys']
        losses.append(store.brt_delays(run, s, {j['id'] for j in journeys if j['line_id'] in brt_codes}))
    shared = set.intersection(*(set(ls) for ls in losses))
    for values, ls in zip(aggregates, losses):
        values['same_brt_delay_s'] = mean(ls[j] for j in shared)
    stats = s['signal_control']
    evidence = store.data(runs[-1], 'signal-online-evidence.json')
    frames = store.frames(runs[-1])
    assert stats['online_updates'] > 0 and stats['online_policy_changes'] > 0
    assert stats['cycle_timing_errors'] == 0 and evidence['time_s'] == duration
    assert evidence['states'] and frames[-1]['online_control']['online_updates'] == stats['online_updates']
    assert any(frame['online_control']['online_updates'] > 0 for frame in frames[:-1])
    sections.extend(['', f'#### {name}', '',
                     f'{stats["online_updates"]} atualizações com base em ciclos concluídos. A evidência recente alterou '
                     f'{stats["online_policy_changes"]} decisões em relação ao modelo congelado sob o mesmo estado observado. '
                     f'Houve {stats["online_explorations"]} explorações e zero desvios do início dos ciclos. '
                     f'A amostra BRT contém {len(shared)} viagens.',
                     '',
                     '| Indicador | Onda Verde fixa | ML congelado | ML online | Online × congelado |',
                     '| --- | ---: | ---: | ---: | ---: |'])
    print(name, stats)
    changes = {}
    for label, key, precision in metrics:
        base, frozen, online = (result[key] for result in aggregates)
        change = online-frozen if key == 'laeq_dba' else 100 * (online-frozen)/frozen
        changes[key] = round(change, 3)
        unit = ' dB' if key == 'laeq_dba' else '%'
        sections.append('| ' + ' | '.join([label, *(fmt(v, precision) for v in (base, frozen, online)),
                                         fmt(change, 2 if key == 'laeq_dba' else 1, True) + unit]) + ' |')
    print(name, 'Online × congelado:', changes)

report = Path('docs/controle-aprendido.md')
previous = report.read_text(encoding='utf-8')
assert '<!-- RESULTADOS_ONLINE -->' in previous
report.write_text(previous.replace('<!-- RESULTADOS_ONLINE -->', '\n'.join(sections)), encoding='utf-8')

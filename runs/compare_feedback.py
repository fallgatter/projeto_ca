from pathlib import Path
from statistics import mean
from xml.etree.ElementTree import parse

from ca.io import read_json
from ca.metrics import signal_kpis
from ca.results import RunResults


store = RunResults()
codes = set(read_json('config/curitiba.json')['brt_lines'])
plan = parse('config/signals/onda-verde-kennedy.add.xml')
wave_signals = {p.get('id') for p in plan.getroot().findall('tlLogic')}
alternatives = ('feedback', 'feedback-transit', 'by-peak')
metrics = (
    ('Atraso médio de carros e ônibus (s)', 'delay_s', 1),
    ('Tempo médio de viagem (s)', 'travel_s', 1),
    ('Velocidade média da rede (km/h)', 'speed_kmh', 2),
    ('Fila média da rede (m)', 'mean_queue_m', 2),
    ('Maior fila da rede (m)', 'peak_queue_m', 1),
    ('Maior fila nos oito sinais da Kennedy (m)', 'kennedy_queue_m', 1),
    ('Viagens motorizadas concluídas', 'completed', 0),
    ('Teletransportes', 'teleports', 0),
    ('Atraso nas mesmas viagens BRT (s)', 'shared_brt_s', 1),
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
priority = {'delay_s': -1, 'mean_queue_m': -1, 'speed_kmh': 1, 'shared_brt_s': -1}


def fmt(value, precision=1):
    return f'{value:,.{precision}f}'.replace(',', '|').replace('.', ',').replace('|', '.')


def data(peak, duration):
    runs = [f'onda-{peak}-kennedy', f'malha-{peak}-feedback', f'malha-{peak}-feedback-transit', f'apr-{peak}-by-peak']
    meta = [store.data(r, 'metadata.json') for r in runs]
    assert all(m['inputs_sha256'] == meta[0]['inputs_sha256'] for m in meta)
    nodes = store.data(runs[0], 'map.json')['intersections']
    wave_nodes = {n for n, row in nodes.items() if wave_signals.intersection(row['signal_ids'])}
    assert len(wave_nodes) == 8
    rows, brts, stats = [], [], []
    for run in runs:
        assert store.data(run, 'status.json')['state'] == 'complete'
        s = store.data(run, 'summary.json')
        assert s['totals']['duration_s'] == duration
        kpi = signal_kpis(s, nodes)
        kpi['kennedy_queue_m'] = max(s['totals']['intersections'].get(n, {}).get('peak_queue_m', 0) for n in wave_nodes)
        journeys = store.data(run, 'bus-journeys.json')['journeys']
        brts.append(store.brt_delays(run, s, {j['id'] for j in journeys if j['line_id'] in codes}))
        rows.append(kpi)
        stats.append(s['signal_control'])
    matched = set.intersection(*(set(b) for b in brts))
    for row, times in zip(rows, brts):
        row['shared_brt_s'] = mean(times[i] for i in matched)
    return rows, stats, len(matched)


lines = ['### Resultados por pico']
scores = {s: {} for s in alternatives}
for peak, duration, label in [('manha', 9000, 'Manhã'), ('tarde', 7200, 'Tarde')]:
    rows, stats, matched = data(peak, duration)
    for s in stats[1:3]:
        assert s['feedback_checks'] and s['green_adjustments']
    lines.extend(['', f'#### {label}', '',
                  f'A amostra BRT contém {matched} viagens concluídas sem teletransporte nos quatro cenários. '
                  f'Os dois controladores novos verificaram a realimentação {fmt(stats[1]["feedback_checks"],0)} e '
                  f'{fmt(stats[2]["feedback_checks"],0)} vezes, respectivamente.',
                  '',
                  '| Indicador | Onda Verde fixa | Filas e BRT | Prioridade BRT | Regras por pico anteriores |',
                  '| --- | ---: | ---: | ---: | ---: |'])
    for name, key, precision in metrics:
        lines.append('| ' + ' | '.join([name, *(fmt(row[key], precision) for row in rows)]) + ' |')
    print(peak, 'atuações:', stats[1:3])
    for variant, row in zip(alternatives, rows[1:]):
        changes = {key: round(100*(row[key]/rows[0][key]-1), 3) for _, key, _ in metrics}
        score = mean(sign*changes[key] for key, sign in priority.items())
        scores[variant][peak] = score
        print(peak, variant, round(score,3), changes)
lines.extend(['','| Estratégia | Pontuação manhã | Pontuação tarde | Média |','| --- | ---: | ---: | ---: |'])
for name, s in scores.items():
    lines.append(f'| {name} | {fmt(s["manha"],2)} | {fmt(s["tarde"],2)} | {fmt(mean(s.values()),2)} |')
print('Pontuações:', scores)
report = Path('docs/malha-fechada.md')
text = report.read_text(encoding='utf-8')
assert '<!-- RESULTADOS_MALHA -->' in text
report.write_text(text.replace('<!-- RESULTADOS_MALHA -->', '\n'.join(lines)), encoding='utf-8')

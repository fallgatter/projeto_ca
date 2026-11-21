import json
from pathlib import Path
from statistics import mean
from xml.etree.ElementTree import iterparse, parse

from ca.io import read_json
from ca.metrics import signal_kpis, window_summary
from ca.results import RunResults


store = RunResults()
codes = frozenset(read_json('config/curitiba.json')['brt_lines'])
full_kpis = (
    ('Atraso médio de carros e ônibus (s)', 'delay_s', 1),
    ('Tempo médio de viagem (s)', 'travel_s', 1),
    ('Velocidade média da rede (km/h)', 'speed_kmh', 2),
    ('Fila média da rede (m)', 'mean_queue_m', 2),
    ('Maior fila da rede (m)', 'peak_queue_m', 1),
    ('Maior fila nos sinais do plano (m)', 'plan_peak_queue_m', 1),
    ('Viagens motorizadas concluídas', 'completed', 0),
    ('Atraso nas mesmas viagens BRT (s)', 'matched_brt_delay_s', 1),
    ('Teletransportes', 'teleports', 0),
    ('CO₂ (kg)', 'co2', 1),
    ('CO (kg)', 'co', 2),
    ('NOₓ (kg)', 'nox', 2),
    ('HC (kg)', 'hc', 3),
    ('PMx (kg)', 'pmx', 3),
    ('LAeq conjunto (dB(A))', 'laeq_dba', 2),
)
window_kpis = tuple(row for row in full_kpis if row[1] not in ('speed_kmh', 'mean_queue_m', 'teleports'))


def total_in_window(run, start, end):
    with (store.path(run)/'frames.jsonl').open(encoding='utf-8') as stream:
        rows = (json.loads(line) for line in stream)
        total = window_summary(f for f in rows if f['start_s'] >= start and f['end_s'] <= end)
    assert total['duration_s'] == end-start, run
    return total


def brt_in_window(run, summary, start, end):
    journeys = store.data(run, 'bus-journeys.json')['journeys']
    ids = {j['id'] for j in journeys if j['line_id'] in codes}
    if start:
        arrivals = set()
        for _, item in iterparse(store.path(run)/'trips.xml'):
            if item.tag == 'tripinfo' and item.get('id') in ids and start <= float(item.get('arrival')) < end:
                arrivals.add(item.get('id'))
            item.clear()
        ids.intersection_update(arrivals)
    return store.brt_delays(run, summary, ids)


def metrics(runs, start, end):
    data = [store.data(run, 'metadata.json') for run in runs]
    for run, other in zip(runs, data):
        assert store.data(run, 'status.json')['state'] == 'complete', run
        assert other['reference_run'] == data[0]['reference_run'], run
        for key in ('network', 'demand', 'traffic_targets', 'sumocfg'):
            assert other['inputs_sha256'][key] == data[0]['inputs_sha256'][key], (run, key)
    assert data[1]['inputs_sha256']['signals'] and not data[0]['inputs_sha256']['signals']
    names = [store.data(r, 'map.json')['intersections'] for r in runs]
    receivers = set.intersection(*(set(n) for n in names))
    plan = parse(store.path(runs[1])/'signal-plan.add.xml')
    tls = {p.get('id') for p in plan.getroot().findall('tlLogic')}
    nodes = {node for node in receivers if tls.intersection(names[0][node]['signal_ids'])}
    assert nodes and len(receivers) == 650

    aggregates, buses = [], []
    for run in runs:
        summary = store.data(run, 'summary.json')
        buses.append(brt_in_window(run, summary, start, end))
        if start:
            summary = {**summary, 'totals': total_in_window(run, start, end)}
        kpi = signal_kpis(summary, receivers)
        intersections = summary['totals']['intersections']
        kpi['plan_peak_queue_m'] = max(intersections.get(node, {}).get('peak_queue_m', 0) for node in nodes)
        aggregates.append(kpi)

    shared = set.intersection(*(set(b) for b in buses))
    assert shared
    for result, losses in zip(aggregates, buses):
        result['matched_brt_delay_s'] = mean(losses[key] for key in shared)
    return aggregates, len(shared), len(nodes)


def formatted(value, precision, sign=False):
    rounded = round(value, precision)
    prefix = '−' if rounded < 0 else '+' if rounded > 0 and sign else ''
    return prefix + f'{abs(rounded):,.{precision}f}'.replace(',', '|').replace('.', ',').replace('|', '.')


def table(title, runs, coordinated, label, start, end):
    records, buses, nodes = metrics(runs, start, end)
    lines = [f'### {title}', '',
             f'Execuções {", ".join(chr(96) + run + chr(96) for run in runs)}. '
             f'Atraso BRT calculado sobre {buses} viagens concluídas sem teletransporte nos três cenários. '
             f'O máximo de fila no recorte local considera {nodes} cruzamentos.',
             '',
             f'| Indicador | Fixo SUMO | {coordinated} | Adaptativo | Adaptativo × {label} |',
             '| --- | ---: | ---: | ---: | ---: |']
    for description, key, precision in (window_kpis if start else full_kpis):
        base, wave, adaptive = (result[key] for result in records)
        if key == 'laeq_dba':
            delta = formatted(adaptive-wave, 2, True) + ' dB'
        else:
            delta = formatted(100*(adaptive-wave)/wave, 1, True) + '%' if wave else '—'
        lines.append('| ' + ' | '.join([description, *(formatted(v, precision) for v in (base, wave, adaptive)), delta]) + ' |')
    print(title)
    print(json.dumps(records, ensure_ascii=False))
    return '\n'.join(lines)


parts = [
    '## Resultados efetivamente simulados',
    table('Manhã · 6h30–9h', ('m4-manha-fixed', 'onda-manha-kennedy', 'm4-manha-gap'),
          'Onda Verde estimada', 'Onda Verde', 0, 9000),
    table('Tarde · 17h–19h', ('m4-tarde-fixed', 'onda-tarde-kennedy', 'm4-tarde-transit'),
          'Onda Verde estimada', 'Onda Verde', 0, 7200),
    table('Plano histórico · 7h–9h', ('m4-manha-fixed', 'onda-manha-setran-2015', 'm4-manha-gap'),
          'Setran 2015 adaptado', 'Setran 2015', 1800, 9000),
    'As variações usam a alternativa coordenada de cada tabela como denominador. '
    'O comparativo histórico usa os blocos completos de 7h a 9h. A velocidade e a fila média instantânea estão disponíveis '
    'para o pico completo nas execuções de referência. A fila máxima usa a mesma definição e os mesmos cruzamentos em '
    'cada trio. O LAeq soma a energia antes de converter a média para decibéis, com os mesmos 650 receptores.',
]
report = Path('docs/onda-verde.md')
text = report.read_text(encoding='utf-8')
assert '<!-- RESULTADOS_ONDA_VERDE -->' in text
report.write_text(text.replace('<!-- RESULTADOS_ONDA_VERDE -->', '\n\n'.join(parts)), encoding='utf-8')

from pathlib import Path
from statistics import mean
import sys

from ca.io import read_json
from ca.results import RunResults
from ca.signal_control import LABELS, STRATEGIES

store = RunResults()
peaks = ('manha', 'tarde')
keys = (('delay_s', -1), ('mean_queue_m', -1), ('speed_kmh', 1), ('brt_matched_delay_s', -1))
paired = {}


def change(pair, key):
    before, after = (pair[side][key] for side in ('baseline', 'adaptive'))
    return 100 * (after-before) / before


def fmt(value, precision=1):
    return f'{value:,.{precision}f}'.replace(',', '|').replace('.', ',').replace('|', '.')


def signed(value, precision=1):
    return ('+' if value > 0 else '−' if value < 0 else '') + fmt(abs(value), precision)


for strategy in STRATEGIES[1:]:
    for peak in peaks:
        run = f'm4-{peak}-{strategy}'
        path = Path('runs')/run/'status.json'
        if path.is_file() and read_json(path)['state'] == 'complete':
            comparison = store.signal_comparison(run)
            assert comparison and comparison['receivers'] == 650, comparison
            summary = store.data(run, 'summary.json')
            assert summary['signal_control']['controlled_signals'] == 85
            assert summary['signal_control']['green_adjustments'] > 0
            paired[peak, strategy] = comparison

scores = {}
for strategy in STRATEGIES[1:]:
    pairs = [pair for peak in peaks if (pair := paired.get((peak, strategy)))]
    for pair in pairs:
        print(pair['run_id'], {key: round(change(pair, key), 3) for key in (
            *(key for key, _ in keys), 'peak_queue_m', 'brt_delay_s', 'completed',
            'brt_completed', 'co2', 'pmx', 'teleports')})
    if len(pairs) == len(peaks):
        score = mean(sign * change(pair, key) for pair in pairs for key, sign in keys)
        scores[strategy] = (all(change(pair, 'completed') >= -2 for pair in pairs), score)
print('Pontuação:', scores)

if '--write' in sys.argv:
    assert len(scores) == len(STRATEGIES) - 1
    ordered = sorted(scores, key=scores.get, reverse=True)
    winner = ordered[0]
    assert scores[winner][0]
    configured = read_json('config/curitiba.json')['signal_control_by_peak']
    options = [strategy for strategy, (eligible, _) in scores.items() if eligible]
    per_peak = {}
    for peak in peaks:
        per_peak[peak] = max(options, key=lambda strategy: mean(
            sign * change(paired[peak, strategy], key) for key, sign in keys))
        assert per_peak[peak] == configured[peak]
    selected = [paired[peak, configured[peak]] for peak in peaks]
    profile_score = mean(sign * change(pair, key) for pair in selected for key, sign in keys)
    tick = chr(96)
    rows = [
        '## Resultado da comparação',
        '',
        f'O **perfil por pico ({tick}by-peak{tick})** aplica **atuação por presença de manhã** e **prioridade BRT seletiva à tarde**. '
        f'Cada modo obteve a melhor pontuação no seu pico. Juntos somam {signed(profile_score, 2)} pontos pela média dos dois horários. '
        f'Quando uma única estratégia é usada nos dois picos, **{LABELS[winner]} ({tick}{winner}{tick})** lidera '
        f'com {signed(scores[winner][1], 2)} pontos.',
        '',
        'A pontuação é a média das variações percentuais no atraso de carros e ônibus, na fila média, na velocidade da rede '
        'e no atraso BRT das viagens comuns aos dois cenários. Uma melhora recebe sinal positivo, inclusive quando vem da '
        'redução de um indicador. O cenário precisa preservar pelo menos 98% das viagens motorizadas concluídas em cada pico. '
        'A maior fila, as emissões, o ruído e os demais indicadores complementam a análise.',
        '',
        '| Estratégia | Pico | Atraso motor | Fila média | Velocidade | Atraso BRT pareado | Viagens motoras concluídas | Pontuação |',
        '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |',
    ]
    for strategy in ordered:
        for peak, label in zip(peaks, ('Manhã', 'Tarde')):
            pair = paired[peak, strategy]
            values = [signed(change(pair, key))+'%' for key in (*[key for key, _ in keys], 'completed')]
            position = signed(scores[strategy][1], 2) if peak == 'manha' else ''
            rows.append(f'| {LABELS[strategy]} | {label} | ' + ' | '.join([*values, position]) + ' |')
    rows.extend([
        '',
        f'Execuções As-Is {tick}m4-manha-fixed{tick} e {tick}m4-tarde-fixed{tick}. Execuções To-Be selecionadas '
        f'{tick}{selected[0]["run_id"]}{tick} e {tick}{selected[1]["run_id"]}{tick}. O perfil usa esses dois resultados, pois '
        'cada janela foi simulada de forma independente. A seleção foi feita na própria amostra comparada.',
        '',
        '### Mobilidade e ambiente no To-Be selecionado',
        '',
        '| Indicador | Manhã · Fixo → Presença | Variação | Tarde · Fixo → BRT seletivo | Variação |',
        '| --- | ---: | ---: | ---: | ---: |',
    ])
    indicators = (
        ('Atraso médio motor (s)', 'delay_s', 1),
        ('Tempo médio de viagem motor (s)', 'travel_s', 1),
        ('Velocidade de rede (km/h)', 'speed_kmh', 2),
        ('Fila média (m)', 'mean_queue_m', 2),
        ('Maior fila (m)', 'peak_queue_m', 1),
        ('Viagens motorizadas concluídas', 'completed', 0),
        ('Teletransportes', 'teleports', 0),
        ('Atraso médio de ônibus (s)', 'bus_delay_s', 1),
        ('Atraso BRT, todas as viagens concluídas (s)', 'brt_delay_s', 1),
        ('Viagens BRT concluídas', 'brt_completed', 0),
        ('Atraso BRT nas mesmas viagens (s)', 'brt_matched_delay_s', 1),
        ('Viagens BRT comuns aos cenários', 'brt_matched', 0),
        ('Travessias monitoradas', 'ped_crossings', 0),
        ('Viagens de pedestres concluídas', 'ped_completed', 0),
        ('Espera média de pedestres (s)', 'ped_wait_s', 2),
        ('Viagens de bicicleta concluídas', 'bike_completed', 0),
        ('CO₂ (kg)', 'co2', 1),
        ('CO (kg)', 'co', 2),
        ('NOₓ (kg)', 'nox', 2),
        ('HC (kg)', 'hc', 3),
        ('PMx (kg)', 'pmx', 3),
        ('LAeq em 650 receptores (dB(A))', 'laeq_dba', 2),
    )
    for label, key, precision in indicators:
        cells = [label]
        for pair in selected:
            base, adaptive = (pair[side][key] for side in ('baseline', 'adaptive'))
            cells.append(f'{fmt(base, precision)} → {fmt(adaptive, precision)}')
            cells.append(signed(adaptive-base, 2)+' dB' if key == 'laeq_dba' else signed(change(pair, key))+'%')
        rows.append('| ' + ' | '.join(cells) + ' |')
    path = Path('docs/relatorio-m4.md')
    report = path.read_text(encoding='utf-8')
    start = report.index('## Resultado da comparação')
    end = report.index('## Desenho do experimento')
    report = report[:start] + '\n'.join(rows) + '\n\n' + report[end:]
    report = report.replace(f'--name novo-manha-adaptativo --control {winner}', '--name novo-manha-adaptativo --control by-peak')
    path.write_text(report, encoding='utf-8')
    print('Selecionada:', per_peak, profile_score)

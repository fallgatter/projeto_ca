from collections import Counter, deque
import gzip
import json
from hashlib import sha256
from statistics import fmean, median
from xml.etree import ElementTree as ET

from .io import ROOT, read_json, write_json

from .demand import departure_audit
from .flow import WINDOW_MINUTES, persistent_error
from .fourier import fit_order, forecast_error, predict, windows_for
from .network import CORRIDORS
from .simulate import CHUNK, FRAME, OUTPUT, PROJECT, WARMUP


def ratio(top, bottom):
    return top/bottom if bottom else None


def road_stats(raw):
    seconds = raw.get('vehicle_s', 0)
    stopped = raw.get('stopped_s', 0)
    entries = raw.get('entries', 0)
    return dict(speed=ratio(3.6*raw.get('distance_m', 0), seconds), stopped=ratio(100*stopped, seconds),
                stop_time=ratio(stopped, entries), stops=ratio(100*raw.get('stops', 0), entries),
                entries=entries, vehicle_s=seconds)


def distribution(values):
    ordered = sorted(values)
    if not ordered:
        return {}
    def quantile(q):
        position = (len(ordered)-1)*q
        lower = int(position)
        upper = min(lower+1, len(ordered)-1)
        return ordered[lower] + (position-lower)*(ordered[upper]-ordered[lower])
    return dict(mean=fmean(ordered), minimum=ordered[0], median=quantile(.5),
                p90=quantile(.9), p95=quantile(.95), maximum=ordered[-1])


def corridor_visits(folder, chunks):
    """Measure visits with an observed entry and exit after warm-up."""
    samples = {road: {mode: [] for mode in ('carros', 'onibus')} for road in CORRIDORS}
    previous = {}
    started = {}
    for index in range(chunks):
        with gzip.open(folder/f'{index}.json.gz', 'rt', encoding='utf8') as stream:
            for now, vehicles, _, _ in json.load(stream):
                current = {}
                for actor, _, _, _, bus, _, mask in vehicles:
                    current[actor] = mask
                    old = previous.get(actor)
                    if old is None or old == mask or now <= WARMUP:
                        continue
                    for bit, road in enumerate(CORRIDORS):
                        flag = 1 << bit
                        if not (old ^ mask) & flag:
                            continue
                        if mask & flag:
                            started[actor, road] = now
                        else:
                            entry = started.pop((actor, road), None)
                            if entry is not None:
                                samples[road]['onibus' if bus else 'carros'].append(now-entry)
                for actor in previous.keys() - current.keys():
                    if previous[actor]:
                        for road in CORRIDORS:
                            started.pop((actor, road), None)
                previous = current
    result = {}
    for road, modes in samples.items():
        modes['todos'] = modes['carros'] + modes['onibus']
        result[road] = {key: dict(n=len(vals), time=distribution(vals)) for key, vals in modes.items()}
    return result


def motor_stats(run, ids):
    stats = run['network']
    distributions = {}
    for mode, prefix in (('todos', ''), ('carros', 'car-'), ('onibus', 'bus-')):
        values = [row for key, row in ids.items() if key.startswith(prefix)]
        distributions[mode] = dict(n=len(values), delay=distribution(row[0] for row in values),
                                   travel=distribution(row[1] for row in values))
    return dict(distributions=distributions, delay=fmean(x[0] for x in ids.values()) if ids else None,
                travel=fmean(x[1] for x in ids.values()) if ids else None,
                completed=stats['completed'], scheduled=stats['scheduled'], departed=stats['departed'],
                pending=stats['scheduled']-stats['completed'], co2=stats['co2_kg'],
                teleports=stats['teleports'], pairs=len(ids))


def audit_reference(reference, completed):
    """Compare simulated baseline duration to the URBS episode used for routing."""
    source = ROOT/'runs'/reference['source']
    if not (source/'bus-journeys.json').is_file() or not (source/'metadata.json').is_file():
        return None
    meta = read_json(source/'metadata.json')
    journeys = read_json(source/'bus-journeys.json')['journeys']
    observed, simulated, differences = [], [], []
    for row in journeys:
        duration = row['observed_end_s']-row['observed_start_s']
        if row['id'] in completed and duration > 0:
            actual = completed[row['id']][1]
            observed.append(duration)
            simulated.append(actual)
            differences.append(actual-duration)
    if not observed:
        return None
    return dict(n=len(observed), episodes=len(journeys), gps_median=median(observed),
                sumo_median=median(simulated), bias_median=median(differences),
                absolute_median=median(map(abs, differences)), dwell_stops=sum(j['stops'] for j in journeys),
                field_intervals=meta.get('field_count_intervals'), od=meta['demand']['origin_destination'])


def pedestrian_times(path):
    completed = {}
    for _, node in ET.iterparse(path, events=('end',)):
        if node.tag == 'personinfo':
            walks = node.findall('walk')
            if walks and float(walks[-1].get('arrival', -1)) >= 0:
                completed[node.get('id')] = float(node.get('duration'))
            node.clear()
    return completed


def time_through_horizon(folder, valid, horizon):
    """Time after scheduled departure until valid arrival or the common cutoff."""
    scheduled = {e.get('id'): float(e.get('depart')) for e in ET.parse(folder/'demand.rou.xml').getroot().findall('vehicle')
                 if e.get('id').startswith(('car-', 'bus-')) and float(e.get('depart')) < horizon}
    ends = {}
    for _, trip in ET.iterparse(folder/'trips.xml', events=('end',)):
        if trip.tag == 'tripinfo' and trip.get('id') in valid:
            ends[trip.get('id')] = float(trip.get('arrival'))
    return fmean(ends.get(actor, horizon)-start for actor, start in scheduled.items())


def review_flow(path):
    """Score both corrective rules on the same archived, minute-by-minute observations."""
    observed = read_json(path)['approaches']
    count = zero = single = 0
    errors = Counter()
    jumps = Counter()
    for rows in observed.values():
        counts = deque(maxlen=WINDOW_MINUTES)
        residual = 0.
        previous = {}
        for index, (second, nominal, actual, hourly, _, baseline, *_) in enumerate(rows):
            counts.append((hourly/60, baseline/60))
            residual = .80*residual+.20*persistent_error(counts)[3]
            estimates = dict(fourier=nominal, current=actual, reviewed=max(0., nominal+residual))
            if second >= WARMUP and nominal <= 30 and index+WINDOW_MINUTES < len(rows):
                target = fmean(row[3] for row in rows[index+1:index+1+WINDOW_MINUTES])
                count += 1
                zero += hourly == 0
                single += hourly == 60
                for key, value in estimates.items():
                    errors[key] += abs(value-target)
                    jumps[key] += abs(value-previous[key]) >= 10
            previous = estimates
    return dict(samples=count, empty=zero, single=single, mae={k:v/count for k,v in errors.items()}, jumps=dict(jumps))


def build_report(output=OUTPUT):
    model_file = output/'fourier.json'
    model = read_json(model_file)
    model_hash = sha256(model_file.read_bytes()).hexdigest()
    data = read_json(output/'map.json')
    pairs = []
    visits_by_folder = {}
    variants = ('coordenado', 'revisado', 'otimizado')
    alternatives = sorted((file for variant in variants for file in output.glob(f'*/*/{variant}/summary.json')),
                          key=lambda f: (variants.index(f.parent.name), f.parents[2].name, int(f.parents[1].name)))
    for file in alternatives:
        optimized = read_json(file)
        reference_file = file.parent.parent/'referencia'/'summary.json'
        if not reference_file.exists():
            continue
        reference = read_json(reference_file)
        if any(reference[key] != optimized[key] for key in ('inputs', 'start', 'duration', 'supply', 'backend')):
            raise ValueError(f'Os insumos dos dois cenários divergem em {file.parent.parent}.')
        if optimized['control']['model'] != model_hash:
            raise ValueError(f'O modelo usado em {file.parent} difere do ajuste disponível.')
        if not optimized['control']['delivered'] or not optimized['control']['changes']:
            raise ValueError(f'O replay {file.parent} ainda não tem mensagens MQTT e ajustes aplicados.')
        runs = [reference, optimized]
        tables = [read_json(file.parent.parent/r['scenario']/'completed.json') for r in runs]
        common = sorted(tables[0].keys() & tables[1].keys())
        pedestrian = [pedestrian_times(file.parent.parent/r['scenario']/'trips.xml') for r in runs]
        pedestrians = pedestrian[0].keys() & pedestrian[1].keys()
        items = {}
        expected = (optimized['duration']+CHUNK-1)//CHUNK
        for run, table in zip(runs, tables):
            name = run['scenario']
            folder = file.parent.parent/name
            if not all((folder/f'{i}.json.gz').is_file() for i in range(expected)):
                raise ValueError(f'Replay incompleto em {folder}.')
            if folder not in visits_by_folder:
                visits_by_folder[folder] = corridor_visits(folder, expected)
            visits = visits_by_folder[folder]
            by_road = {}
            for key, modes in run['corridors'].items():
                overall = Counter(modes['carros'])
                overall.update(modes['onibus'])
                by_road[key] = dict(todos=road_stats(overall),
                                    **{mode: road_stats(raw) for mode, raw in modes.items()})
            side = 'referencia' if name == 'referencia' else 'otimizado'
            items[side] = dict(network=motor_stats(run, {k: table[k] for k in common}), visits=visits,
                               corridors=by_road, control=run.get('control'),
                               programs=dict(Counter(run['programs'].values())),
                               path=f'{run["peak"]}/{run["seed"]}/{name}')
            items[side]['network']['time_all'] = time_through_horizon(folder, table, run['duration'])
        pair = dict(peak=optimized['peak'], policy=optimized['scenario'], seed=optimized['seed'], start=optimized['start'],
                    duration=optimized['duration'], supply=optimized['supply'], scenarios=items,
                    pedestrians=dict(n=len(pedestrians), durations=[distribution(tab[k] for k in pedestrians)
                                                                    for tab in pedestrian]),
                    audit=audit_reference(reference, tables[0]))
        archived = OUTPUT/optimized['peak']/str(optimized['seed'])/'referencia'
        if reference.get('profile') == 'escalonado' and (archived/'summary.json').is_file():
            old_inputs = read_json(archived/'summary.json')['inputs']
            if all(old_inputs[k] == reference['inputs'][k] for k in ('net', 'reference', 'targets')):
                pair['departure_audit'] = departure_audit(archived, reference_file.parent, reference['duration'])
        previous_review = file.parent.parent/'coordenado'
        if optimized['scenario'] == 'revisado' and (previous_review/'forecast.json').is_file():
            previous_summary = read_json(previous_review/'summary.json')
            if all(previous_summary[key] == reference[key] for key in ('inputs', 'start', 'duration', 'backend')):
                pair['flow_review'] = review_flow(previous_review/'forecast.json')
                previous_trips = read_json(previous_review/'completed.json')
                shared = sorted(previous_trips.keys() & set(common))
                if shared:
                    pair['review_cohort'] = dict(n=len(shared),
                        delay=[fmean(trips[k][0] for k in shared) for trips in (tables[0], previous_trips, tables[1])])
        previous_folder = PROJECT/'results'/optimized['peak']/str(optimized['seed'])/'otimizado'
        if (previous_folder/'summary.json').exists() and read_json(previous_folder/'summary.json')['inputs'] == reference['inputs']:
            old = read_json(previous_folder/'completed.json')
            shared = sorted(old.keys() & set(common))
            if shared:
                pair['three_way'] = dict(n=len(shared), delay=[fmean(table[k][0] for k in shared)
                                          for table in (tables[0], old, tables[1])])
        pairs.append(pair)
    if not pairs:
        raise ValueError('Conclua pelo menos um par referência/otimizado.')

    approaches = {key: set() for key in CORRIDORS}
    for light in data['lights'].values():
        for lane in light['approaches']:
            for key in lane[4]:
                approaches[key].add(lane[5])
    model_curves = {}
    for key, edges in {'rede': set(model['approaches']), **approaches}.items():
        series = [model['approaches'][edge] for edge in edges if edge in model['approaches']]
        model_curves[key] = [round(sum(predict(coefficients, hour*900) for coefficients in series))
                             for hour in range(97)]
    report = dict(pairs=pairs, step=FRAME, chunk=CHUNK, warmup=WARMUP, signals=len(data['lights']),
                  masks={key: 1 << i for i, key in enumerate(CORRIDORS)},
                  segments=len(data['roads']),
                  model=dict(training=model['training'], curves=model_curves, bin_minutes=15,
                             harmonics=model['harmonics']))
    if 'validation' in model:
        report['profile'] = 'escalonado'
        report['model']['validation'] = model['validation']
        fitted_seeds = {run['seed'] for run in model['training']} | set(model['validation']['seeds'])
        holdout = [read_json(file) for file in sorted(output.glob('*/*/referencia/summary.json'))
                   if int(file.parents[1].name) not in fitted_seeds]
        if holdout:
            training = [read_json(file) for file in sorted(output.glob('*/*/treino/summary.json'))]
            samples = windows_for(training)
            target = windows_for(holdout)
            orders = [int(order) for order in model['validation']['mae']]
            report['model']['holdout'] = dict(
                seeds=sorted({run['seed'] for run in holdout}),
                mae={str(order): forecast_error(model['approaches'] if order == model['harmonics']
                                                else fit_order(samples, order), target) for order in orders})
    write_json(output/'report.json', report)
    write_markdown(report, output)
    print(f'{len(pairs)} comparações verificadas. Painel disponível com o comando serve.', flush=True)


def write_markdown(report, output):
    # The dashboard keeps both policies selectable. Each printable report covers one policy.
    for policy, filename in [('otimizado', 'MPC_INICIAL.md'), ('coordenado', 'RESULTADOS.md'), ('revisado', 'REVISAO.md')]:
        selected = [pair for pair in report['pairs'] if pair['policy'] == policy]
        if selected:
            write_policy({**report, 'pairs': selected}, output/filename, policy)


def write_policy(report, filename, policy):
    lines = ['# Resultados do experimento', '',
             'Controle preditivo coordenado com revisão do fluxo de fundo em janelas de cinco minutos.'
             if policy == 'revisado' else 'Controle preditivo com proteção de coordenação e ocupação das saídas.'
             if policy == 'coordenado' else 'Primeira versão do controle preditivo de horizonte móvel.', '',
             f'O mapa contém {report["segments"]} segmentos motorizados e {report["signals"]} semáforos.',
             'Cada comparação usou a mesma malha, demanda, limites de velocidade, semente e plano inicial.',
             'O atraso da rede considera os mesmos veículos concluídos sem teletransporte nos dois cenários.',
             'A fração de tempo parado por via inclui carros e ônibus após 5 minutos de aquecimento.',
             'Paradas programadas de ônibus integram o tempo parado.', '',
             '| Pico | Semente | Atraso de viagem (s) | Kennedy, parado (%) | Sete, parado (%) | Floriano, parado (%) |',
             '| --- | ---: | ---: | ---: | ---: | ---: |']
    for pair in report['pairs']:
        before, after = (pair['scenarios'][name] for name in ('referencia', 'otimizado'))
        changes = [transition(before['network']['delay'], after['network']['delay'])]
        changes.extend(transition(before['corridors'][key]['todos']['stopped'],
                                  after['corridors'][key]['todos']['stopped']) for key in CORRIDORS)
        peak = {'manha': 'Manhã', 'tarde': 'Tarde'}[pair['peak']]
        lines.append(f'| {peak} | {pair["seed"]} | ' + ' | '.join(changes) + ' |')
    lines.extend(['', '| Pico | Semente | Viagens concluídas | Teletransportes | CO₂ (kg) | MQTT entregues | Ajustes de verde |',
                  '| --- | ---: | ---: | ---: | ---: | ---: | ---: |'])
    for pair in report['pairs']:
        before, after = (pair['scenarios'][name] for name in ('referencia', 'otimizado'))
        peak = {'manha': 'Manhã', 'tarde': 'Tarde'}[pair['peak']]
        changes = [transition(before['network'][key], after['network'][key], digits)
                   for key, digits in (('completed', 0), ('teleports', 0), ('co2', 2))]
        broker = after['control']
        lines.append(f'| {peak} | {pair["seed"]} | ' + ' | '.join(changes)
                     + f' | {broker["delivered"]}/{broker["published"]} | {sum(broker["changes"].values())} |')
    lines.extend(['', '## Distribuição das viagens pareadas', '',
                  '| Pico | Semente | Viagens comuns | Medida (s) | Média | Mínimo | Mediana | P90 | P95 | Máximo |',
                  '| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |'])
    for pair in report['pairs']:
        before, after = (pair['scenarios'][name]['network']['distributions']['todos']
                         for name in ('referencia', 'otimizado'))
        for key, name in (('delay', 'Atraso'), ('travel', 'Duração')):
            cells = [transition(before[key].get(stat), after[key].get(stat))
                     for stat in ('mean', 'minimum', 'median', 'p90', 'p95', 'maximum')]
            lines.append(f'| {pair["peak"]} | {pair["seed"]} | {before["n"]} | {name} | ' + ' | '.join(cells) + ' |')
    lines.extend(['', '## Meta de 10% de redução do atraso médio', '',
                  '| Pico | Semente | Ganho sobre onda verde | Meta atingida |',
                  '| --- | ---: | ---: | --- |'])
    for pair in report['pairs']:
        a, b = (pair['scenarios'][name]['network']['delay'] for name in ('referencia', 'otimizado'))
        gain = 100*(1-b/a) if a else None
        if gain is not None:
            lines.append(f'| {pair["peak"]} | {pair["seed"]} | {gain:.2f}% | {"Sim" if gain >= 10 else "Não"} |')
    lines.extend(['', 'As sementes 42 e 73 orientaram o ajuste. A semente 101, quando presente, avalia a política já definida sobre a mesma demanda com outra realização do SUMO.', '',
                  '| Grupo | Ocorrências de viagens pareadas | Atraso médio ponderado (s) | Redução |',
                  '| --- | ---: | ---: | ---: |'])
    groups = [('Ajuste', [p for p in report['pairs'] if p['seed'] in (42, 73)]),
              ('Avaliação reservada', [p for p in report['pairs'] if p['seed'] == 101]),
              ('Todos os ensaios', report['pairs'])]
    for label, group in groups:
        count = sum(p['scenarios']['referencia']['network']['pairs'] for p in group)
        if count:
            averages = [sum(p['scenarios'][name]['network']['delay']*p['scenarios'][name]['network']['pairs']
                            for p in group)/count for name in ('referencia', 'otimizado')]
            gain = 100 * (1 - averages[1]/averages[0])
            lines.append(f'| {label} | {count} | {transition(*averages)} | {gain:.2f}% |')
    prior = [p for p in report['pairs'] if 'three_way' in p]
    if prior:
        lines.extend(['', '## Comparação com a versão anterior', '',
                      '| Pico | Semente | Viagens nos três cenários | Referência (s) | Anterior (s) | Preditivo (s) |',
                      '| --- | ---: | ---: | ---: | ---: | ---: |'])
        for p in prior:
            stats = p['three_way']
            times = ' | '.join(f'{v:.2f}' for v in stats['delay'])
            lines.append(f'| {p["peak"]} | {p["seed"]} | {stats["n"]} | {times} |')
    lines.extend(['', '## Permanência nas três vias', '',
                  'Cada passagem requer entrada e saída observadas após cinco minutos de aquecimento. Os grupos de passagens podem ter tamanhos diferentes. A resolução do replay é de 2 s.', '',
                  '| Pico | Semente | Via | Passagens | Média (s) | Mínimo (s) | Mediana (s) | P95 (s) | Máximo (s) |',
                  '| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |'])
    for pair in report['pairs']:
        for road, label in CORRIDORS.items():
            a, b = [pair['scenarios'][name]['visits'][road]['todos'] for name in ('referencia', 'otimizado')]
            cells = [transition(a['time'].get(k), b['time'].get(k)) for k in ('mean', 'minimum', 'median', 'p95', 'maximum')]
            lines.append(f'| {pair["peak"]} | {pair["seed"]} | {label} | {a["n"]} → {b["n"]} | ' + ' | '.join(cells) + ' |')
    lines.extend(['', '## Todas as partidas programadas', '',
                  'Tempo médio desde a partida programada até uma chegada válida, em segundos. Para quem ficou pendente ou sofreu teletransporte, a contagem vai até o fim do pico.',
                  '', '| Pico | Semente | Referência → preditivo (s) |', '| --- | ---: | ---: |'])
    for pair in report['pairs']:
        values = [pair['scenarios'][name]['network']['time_all'] for name in ('referencia', 'otimizado')]
        lines.append(f'| {pair["peak"]} | {pair["seed"]} | {transition(*values)} |')
    lines.extend(['', '## Pedestres simulados na XV de Novembro', '',
                  '| Pico | Semente | Percursos comuns | Duração média (s) | P95 (s) |',
                  '| --- | ---: | ---: | ---: | ---: |'])
    for pair in report['pairs']:
        people = pair['pedestrians']
        first, last = people['durations']
        lines.append(f'| {pair["peak"]} | {pair["seed"]} | {people["n"]} | '
                     + transition(first.get('mean'), last.get('mean')) + ' | '
                     + transition(first.get('p95'), last.get('p95')) + ' |')
    lines.extend(['', '## Aderência da referência aos dados locais', '',
                  '| Pico | Semente | Ônibus pareados | Mediana GPS (s) | Mediana SUMO (s) | Erro pareado mediano (s) | Erro absoluto mediano (s) |',
                  '| --- | ---: | ---: | ---: | ---: | ---: | ---: |'])
    for pair in report['pairs']:
        if pair['audit']:
            a = pair['audit']
            lines.append(f'| {pair["peak"]} | {pair["seed"]} | {a["n"]}/{a["episodes"]} | {a["gps_median"]} | {a["sumo_median"]} | {a["bias_median"]} | {a["absolute_median"]} |')
    lines.extend(['', 'O pareamento usa a duração do episódio de GPS usado na reconstrução da rota e a duração simulada do mesmo ônibus na referência.',
                  'Os volumes absolutos de carros foram assumidos. As medianas TomTom dos picos limitam a velocidade desejada e já incorporam efeitos do congestionamento observado. Filas e sinais do SUMO podem acrescentar atraso sobre esse efeito.',
                  '', '| Pico | Episódios de GPS na demanda | Paradas de ônibus codificadas | Intervalos com contagem de campo |',
                  '| --- | ---: | ---: | ---: |'])
    audited = {}
    for pair in report['pairs']:
        if pair['audit']:
            audited.setdefault(pair['peak'], pair['audit'])
    for peak, audit in audited.items():
        intervals = audit['field_intervals'] if audit['field_intervals'] is not None else '—'
        lines.append(f'| {peak} | {audit["episodes"]} | {audit["dwell_stops"]} | {intervals} |')
    lines.extend(['', 'O tempo de embarque depende das paradas detectáveis no GPS. Os planos semafóricos mesclam registros históricos e defasagens inferidas dos tempos de percurso.',
                  '', 'P90 e P95 usam interpolação linear. Cada extremo identifica o menor ou maior valor do grupo em cada cenário.',
                  'Os valores reportados são resultados do SUMO para a demanda de julho de 2026.'])
    if 'validation' in report['model']:
        model = report['model']
        lines.extend(['', '## Demanda escalonada e ordem de Fourier', '',
                      'As partidas de carro foram espaçadas por origem em blocos de 15 minutos, com uma fase sorteada por origem e bloco. Pequenos deslocamentos de até 8 s reduzem extremos em janelas de 5 s. A malha, o volume por bloco, as rotas e os horários dos demais modos foram preservados. Carros que entram pelo perímetro passam a usar a velocidade de inserção segura do SUMO.',
                      '', f'Ordem adotada pelo erro absoluto médio de validação: **{model["harmonics"]}**.'])
        for key, label in (('validation', 'Validação'), ('holdout', 'Teste reservado')):
            if key in model:
                result = model[key]
                errors = ', '.join(f'ordem {k}: {v:.3f}' for k,v in result['mae'].items())
                lines.extend(['', f'{label}, semente {result["seeds"]}: {errors} veíc./h.'])
        lines.extend(['', '| Pico | Intervalos avaliados | Intervalos menores que 5 s | Intervalos maiores que 120 s | P90 do intervalo (s) | Janelas de 5 s sem entrada na malha | Pico de entradas em 5 s |',
                      '| --- | ---: | ---: | ---: | ---: | ---: | ---: |'])
        for pair in report['pairs']:
            if 'departure_audit' in pair:
                a, b = pair['departure_audit']
                counts = [transition(a['actual'][m], b['actual'][m], 0) for m in ('gaps', 'short', 'long')]
                counts.append(transition(a['actual']['p90'], b['actual']['p90'], 1))
                counts.extend(transition(a[m], b[m], 0) for m in ('empty_5s', 'max_5s'))
                lines.append(f'| {pair["peak"]} | ' + ' | '.join(counts) + ' |')
        lines.extend(['', 'Os intervalos são medidos nas dez origens de carro com maior demanda na referência original, com o mesmo plano fixo e a mesma semente. As janelas de 5 s abrangem todas as origens. O escalonamento controla a demanda gerada. A aderência dos intervalos à rua depende de medições de campo.'])
    reviewed = [pair for pair in report['pairs'] if 'flow_review' in pair]
    if reviewed:
        lines.extend(['', '## Revisão da correção de fluxo', '',
                      'A contagem observada continua registrada por minuto. A revisão corrige a demanda de fundo com até cinco minutos de contagens acumuladas. O erro só contribui acima da tolerância de duas vezes a raiz do maior valor entre um e a contagem prevista. A tolerância é uma heurística para evitar que eventos isolados dominem o ajuste.',
                      '', '| Pico | Observações com Fourier até 30 veíc./h | Sem veículo | Um veículo | MAE em 5 min, antes → revisão | Saltos de pelo menos 10 veíc./h, antes → revisão |',
                      '| --- | ---: | ---: | ---: | ---: | ---: |'])
        for pair in reviewed:
            flow = pair['flow_review']
            lines.append(f'| {pair["peak"]} | {flow["samples"]} | {flow["empty"]} | {flow["single"]} | '
                         + transition(flow['mae']['current'], flow['mae']['reviewed']) + ' | '
                         + transition(flow['jumps']['current'], flow['jumps']['reviewed'], 0) + ' |')
        lines.extend(['', 'Esse diagnóstico reaplica as duas regras ao mesmo histórico, com alvo igual à média dos cinco minutos seguintes. As tabelas anteriores apresentam as novas execuções do simulador.',
                      '', '| Pico | Viagens comuns aos três cenários | Atraso na referência | Atraso coordenado | Atraso revisado |',
                      '| --- | ---: | ---: | ---: | ---: |'])
        for pair in reviewed:
            if 'review_cohort' in pair:
                stats = pair['review_cohort']
                values = ' | '.join(f'{value:.2f}'.replace('.', ',') for value in stats['delay'])
                lines.append(f'| {pair["peak"]} | {stats["n"]} | {values} |')
    filename.write_text('\n'.join(lines)+'\n', encoding='utf-8')


def transition(before, after, digits=2):
    if before is None or after is None:
        return '—'
    return f'{before:.{digits}f} → {after:.{digits}f}'.replace('.', ',')

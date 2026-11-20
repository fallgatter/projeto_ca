import json
from bisect import bisect_left, bisect_right
from collections import Counter
from functools import lru_cache
from math import cos, hypot, log1p, radians

import plotly.graph_objects as go
from dash import ClientsideFunction, Dash, Input, Output, Patch, State, ctx, dcc, html, no_update
from flask import Response, abort, jsonify, request, send_from_directory

from .io import CACHE, PRESETS, ROOT, envelope, read_json
from .metrics import signal_kpis, window_summary
from .results import RunResults, current_capture, period, summary_payload

TEXT = '#173035'
TEAL = '#14776d'
BLUE = '#256eac'
HEAT_METRIC = 'traffic_density'
HEAT_TRACE = 'Tráfego acumulado'
HEAT_TICKS = (1, 5, 20, 60, 150, 400, 1000)
PLAYBACK_TICK_MS = 100
PLAYBACK_RATE = 15
PLAYBACK_SPEEDS = (.25, .5, 1, 2, 4, 8)
WINDOW_STEP_S = 60
MAP_METRICS = {HEAT_METRIC: 'Mapa de calor', 'laeq_dba': 'LAeq · dB(A)', 'passages': 'Passagens',
               'peak_queue_m': 'Maior fila · m'}
STATE_LABELS = {'preparing': 'Preparando', 'running': 'Simulação em curso', 'complete': 'Simulação concluída', 'failed': 'Falha na execução'}
CAR_TRACE = 'Carros simulados'
BUS_TRACE = 'Ônibus simulados'
GPS_TRACE = 'GPS URBS'
SIGNAL_TRACE = 'Semáforos por faixa'
MQTT_TRACE = 'Mensagens MQTT'


def formatted(value, precision=0):
    if value is None:
        return '—'
    return f'{value:,.{precision}f}'.replace(',', '|').replace('.', ',').replace('|', '.')


def help_info(label, tooltip_id, content):
    return html.Div([
        html.Button('i', type='button', className='info-button',
                    **{'aria-label': label, 'aria-describedby': tooltip_id}),
        html.Div(content, id=tooltip_id, className='info-tooltip', role='tooltip'),
    ], className='info-popover')


def layout():
    graph_config = {
        'displaylogo': False, 'scrollZoom': True, 'doubleClick': 'reset', 'displayModeBar': True,
        'modeBarButtons': [['zoomIn2d', 'zoomOut2d', 'resetScale2d']],
    }
    return html.Div([
        html.Header(html.Div([
            html.Div([html.Span('C', className='brand-icon', **{'aria-hidden': 'true'}),
                      html.Div([html.H1('Quadrilátero Central'), html.Span('Curitiba')])], className='brand'),
            html.Span('Carros e ônibus', className='motor-label'),
            html.Div([
                html.Label('Pico da simulação', htmlFor='run-peak', className='sr-only'),
                dcc.Dropdown(id='run-peak', options=[
                    {'label': f'{label} · {"–".join(PRESETS[peak])}', 'value': peak}
                    for peak, label in (('manha', 'Manhã'), ('tarde', 'Noite'))
                ], value='manha', clearable=False, searchable=False),
            ], className='peak-control'),
            html.Div(id='live-status', className='run-state'),
        ], className='shell nav')),
        html.Main([
            html.Section([
                html.Article([
                    html.Div([
                        html.Div([html.H2('Mapa do tráfego'), help_info(
                            'Como usar o mapa', 'map-help', [html.P(id='map-note'),
                             html.P('Use a roda do mouse ou os botões + e − para dar zoom. Arraste para mover o mapa. '
                                    'Clique na legenda para mostrar ou esconder uma camada.')])], className='section-title'),
                        html.Div([
                            html.Label('Camada do mapa', htmlFor='map-metric', className='sr-only'),
                            dcc.Dropdown(id='map-metric',
                                         options=[{'label': v, 'value': k} for k, v in MAP_METRICS.items()],
                                         value=HEAT_METRIC, clearable=False, searchable=False),
                            html.Button('Tela cheia', id='map-fullscreen', type='button', className='map-button',
                                        **{'aria-pressed': 'false', 'aria-controls': 'dashboard'}),
                        ], className='map-actions'),
                    ], className='map-toolbar'),
                    html.Div([
                        html.Section([html.Div([html.H2(label),
                                                html.Dl(scenario_indicators({}), id=f'kpis-{side}', className='scenario-kpis')],
                                               className='scenario-summary'),
                                      html.Div([
                                          dcc.Graph(id=f'map-{side}', responsive=True, config=graph_config,
                                                    className='map-graph'),
                                          html.Div(id='mqtt-activity', className='mqtt-activity') if side == 'adaptive' else None,
                                      ], className='scenario-plot')],
                                     className='scenario-map', **{'aria-label': label})
                        for side, label in (('baseline', 'Como está hoje'), ('adaptive', 'Melhor resultado'))
                    ], className='map-comparison'),
                    html.Div([
                        html.Button('Reproduzir', id='map-play', type='button', disabled=True),
                        html.Button('Reiniciar', id='map-restart', type='button', disabled=True),
                        html.Div([
                            html.Label('Velocidade', htmlFor='map-speed'),
                            dcc.Dropdown(id='map-speed', options=[{'label': f'{speed}×'.replace('.', ','), 'value': speed}
                                                                 for speed in PLAYBACK_SPEEDS],
                                         value=1, clearable=False, searchable=False),
                        ], className='map-speed-control'),
                        html.Div(dcc.Slider(id='map-progress', min=0, max=WINDOW_STEP_S, step=WINDOW_STEP_S,
                                            value=0, marks=None, allow_direct_input=False,
                                            updatemode='mouseup', disabled=True),
                                 className='map-seek', role='group', **{'aria-label': 'Posição na reprodução'}),
                        html.Time('—', id='map-time', **{'aria-label': 'Horário da simulação no mapa'}),
                    ], id='playback-controls', className='map-playback', role='group', **{'aria-label': 'Reprodução da simulação'}),
                    html.Div(html.Span('© OpenStreetMap · IPPUC', id='map-attribution'), className='map-meta'),
                ], id='map-panel', className='panel map-panel'),
                html.P(id='comparison-status', role='status', className='comparison-status'),
            ], className='map-layout'),
        ], className='shell content'),
        dcc.Interval(id='tick', interval=2500), dcc.Store(id='map-scrub'), dcc.Store(id='run'),
        dcc.Store(id='map-render-baseline'), dcc.Store(id='map-render-adaptive'),
        dcc.Store(id='map-gesture', data=False), dcc.Store(id='map-viewport'),
        dcc.Store(id='map-tick-disabled', data=True),
        dcc.Interval(id='map-tick', interval=PLAYBACK_TICK_MS, disabled=True), dcc.Store(id='map-playback')], id='dashboard')

def base_figure():
    fig = go.Figure()
    fig.update_layout(template='plotly_white', paper_bgcolor='#ffffff', font={'family': 'Segoe UI, sans-serif', 'color': TEXT},
                      margin={'l': 6, 'r': 6, 't': 4, 'b': 52}, hoverlabel={'bgcolor': '#fff', 'font_size': 13})
    return fig


def empty_figure(message):
    fig = base_figure()
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    fig.add_annotation(x=.5, y=.5, xref='paper', yref='paper', text=message, showarrow=False, font={'color': '#526762'})
    return fig


def junction_metrics(summary, map_data, metric):
    measured = [(key, state) for key, state in summary['intersections'].items()
                if key in map_data['intersections'] and state.get(metric) is not None]
    ordered = sorted(measured, key=lambda item: (-item[1][metric], item[0]))
    return [(map_data['intersections'][key], state) for key, state in ordered[:12]]


def playback_positions(store, run, frames, completed, time_s):
    block = min(completed, len(frames) - 1)
    samples = store.data(run, f'positions/{frames[block]["end_s"]}.json', [])
    if not samples:
        return None
    index = bisect_right(samples, time_s, key=lambda sample: sample['time_s'])
    if index:
        before = samples[index - 1]
    elif block:
        previous = store.data(run, f'positions/{frames[block-1]["end_s"]}.json', [])
        before = previous[-1] if previous else None
    else:
        before = None
    if before is None or index == len(samples) or before['time_s'] == time_s:
        return before

    after = samples[index]
    elapsed = after['time_s'] - before['time_s']
    fraction = (time_s - before['time_s']) / elapsed
    result = {'time_s': time_s}
    for mode in ('cars', 'buses'):
        points = result[mode] = {}
        for actor, (lon, lat) in before[mode].items():
            target = after[mode].get(actor)
            if target is None:
                points[actor] = (lon, lat)
                continue
            dx, dy = target[0] - lon, target[1] - lat
            distance = hypot(dx * cos(radians(lat)), dy) * 111_195
            points[actor] = ((lon + dx * fraction, lat + dy * fraction)
                             if distance <= 55 * elapsed else (lon, lat))
    return result


def map_positions(frame, samples, start, snapshot=None, bus_lines=None):
    if snapshot is not None:
        cars = snapshot['cars']
        buses = snapshot['buses']
        bus_lines = bus_lines or {}
    else:
        cars = {row['id']: row['coordinates'] for row in (frame or {}).get('cars', [])}
        buses = {row['id']: row['coordinates'] for row in (frame or {}).get('buses', [])}
        bus_lines = {row['id']: row['line_id'] for row in (frame or {}).get('buses', [])}
    gps = []
    if frame:
        end = frame['end_s']
        lower = bisect_left(samples, max(start, end-30), key=lambda row: row[0])
        upper = bisect_left(samples, end, lo=lower, key=lambda row: row[0])
        gps = list({(row[3], row[4]): row for row in samples[lower:upper]}.values())
    return {
        CAR_TRACE: {'x': [point[0] for point in cars.values()] or [None],
                    'y': [point[1] for point in cars.values()] or [None],
                    'text': list(cars) or [None]},
        BUS_TRACE: {'x': [point[0] for point in buses.values()] or [None],
                    'y': [point[1] for point in buses.values()] or [None],
                    'text': [f'Linha {bus_lines[actor]} · {actor}' if bus_lines.get(actor) else actor
                             for actor in buses] or [None]},
        GPS_TRACE: {'x': [p[1] for p in gps] or [None], 'y': [p[2] for p in gps] or [None],
                    'text': [p[4] for p in gps] or [None]},
    }


def accumulated_traffic(grid, frames, complete_blocks, time_s):
    cols, rows = grid['columns'], grid['rows']
    totals = Counter()
    for frame in frames[:complete_blocks]:
        totals.update(frame.get('traffic_cells', {}))
    if complete_blocks < len(frames):
        frame = frames[complete_blocks]
        if time_s > frame['start_s']:
            fraction = (time_s-frame['start_s']) / (frame['end_s']-frame['start_s'])
            for cell, count in frame.get('traffic_cells', {}).items():
                totals[cell] += fraction * count
    vehicle_minutes = [[0.0] * cols for _ in range(rows)]
    for cell, seconds in totals.items():
        row, col = divmod(int(cell), cols)
        vehicle_minutes[row][col] = round(seconds / 60, 2)
    intensity = [[log1p(value) for value in row] for row in vehicle_minutes]
    return {'z': intensity, 'customdata': vehicle_minutes}


def signal_activity(recording, cursor):
    end = bisect_right(recording, cursor, key=lambda row: row['time_s'])
    start = end - 1
    while start > 0 and not recording[start]['full']:
        start -= 1
    lights = {}
    for row in recording[max(0, start):end]:
        lights.update(row['lights'])
    recent = [row['mqtt'] for row in recording[max(0, end-3):end] if 'mqtt' in row and cursor-row['time_s'] < 3]
    return lights, recent


def signal_colors(approaches, states):
    colors, status = [], []
    for lane in approaches:
        program = states.get(lane['signal'], '')
        lamps = ''.join(program[i] for i in lane['links'] if i < len(program)).lower()
        if 'g' in lamps:
            color = '#18a957'
        elif any(lamp in 'yu' for lamp in lamps):
            color = '#e8a012'
        elif lamps and all(lamp in 'rs' for lamp in lamps):
            color = '#da493f'
        else:
            color = '#697a80'
        colors.append(color)
        status.append(lamps or '—')
    return colors, status


def mqtt_markers(nodes, recent):
    latest = {}
    for packet in recent:
        for signal in packet['observed']:
            latest[signal] = packet
    x, y, colors, texts = [], [], [], []
    for node in nodes.values():
        for signal in node['signal_ids']:
            packet = latest.get(signal)
            if packet is None:
                continue
            lon, lat = node['coordinates']
            delta = packet['applied'].get(signal)
            x.append(lon)
            y.append(lat)
            colors.append('#a942ce' if delta is not None else '#007cbe')
            details = ('Sem resposta' if packet['decisions'] is None else 'Resposta recebida')
            if delta is not None:
                details += f' · verde {delta:+g} s'
            texts.append(f'{node["name"]}<br>Observação MQTT em t={packet["time_s"]} s<br>{details}')
    return dict(x=x, y=y, text=texts, marker={'color': colors, 'size': 15, 'symbol': 'circle-open',
                                            'line': {'width': 2}})


def map_figure(data, ranking, positions, metric, run, heat=None):
    fig = base_figure()
    front, low, back, high = data['bbox']
    fig.update_layout(plot_bgcolor='#edf1ec', paper_bgcolor='#edf1ec', uirevision=run, dragmode='pan',
                      margin={'l': 0, 'r': 0, 't': 0, 'b': 0},
                      legend={'orientation': 'h', 'y': .15, 'x': .5, 'xanchor': 'center', 'yanchor': 'bottom',
                              'bgcolor': 'rgba(255,255,255,.9)', 'font': {'size': 11}, 'itemsizing': 'constant'})
    fig.update_xaxes(range=[front, back], minallowed=front, maxallowed=back, visible=False, constrain='domain')
    fig.update_yaxes(range=[low, high], minallowed=low, maxallowed=high, visible=False,
                     scaleanchor='x', scaleratio=1/cos(radians((low+high)/2)), constrain='domain')
    fig.add_shape(type='rect', x0=front, x1=back, y0=low, y1=high, layer='below',
                  line={'color': '#8ba198', 'width': 1.4})
    for key, label, color, width, visible in (
        ('roads', 'Vias OSM', '#d4dcd7', .85, True), ('corridors', 'Vias do enunciado', '#829992', 1.9, True),
        ('cycleways', 'Ciclovias SUMO', '#079164', 1.6, 'legendonly'),
        ('ippuc_cycleways', 'Ciclovias IPPUC', '#566ab1', 2.5, 'legendonly'),
    ):
        if key in data['roads']:
            x, y = data['roads'][key]
            fig.add_trace(go.Scattergl(x=x, y=y, mode='lines', name=label, visible=visible,
                                       hoverinfo='skip', line={'color': color, 'width': width}))
    grid = data.get('traffic_grid')
    if metric == HEAT_METRIC and grid:
        # Anchor the full raster to the grid so zooming out can reveal cells outside the current view.
        fig.add_trace(go.Heatmap(
            x0=front+(back-front)/(2*grid['columns']), dx=(back-front)/grid['columns'],
            y0=low+(high-low)/(2*grid['rows']), dy=(high-low)/grid['rows'],
            **heat, name=HEAT_TRACE, uid='traffic-density',
            zmin=0, zmax=log1p(HEAT_TICKS[-1]), zsmooth='fast',
            colorscale=[[0, 'rgba(255, 224, 150, 0)'], [.18, 'rgba(249, 210, 119, .35)'],
                        [.4, '#f6c768'], [.6, '#f29346'], [.8, '#d84939'], [1, '#751b45']],
            colorbar={'title': {'text': 'veíc.·min'}, 'thickness': 10, 'len': .34, 'x': .015, 'y': .50,
                      'outlinewidth': 0, 'tickvals': [log1p(value) for value in HEAT_TICKS],
                      'ticktext': [formatted(value) for value in HEAT_TICKS[:-1]] + ['1.000+']},
            hovertemplate='%{customdata:.2f} veíc.·min acumulados<extra></extra>'))
    elif metric == HEAT_METRIC:
        fig.add_annotation(x=.5, y=.5, xref='paper', yref='paper',
                           text='Gere uma nova execução para exibir o tráfego acumulado.',
                           showarrow=False, bgcolor='white', borderpad=7)
    if data['crossings']:
        fig.add_trace(go.Scattergl(x=[p['coordinates'][0] for p in data['crossings']],
                                   y=[p['coordinates'][1] for p in data['crossings']], mode='markers', name='Faixas na XV',
                                   text=[p['name'] for p in data['crossings']], hovertemplate='%{text}<extra>Faixa na XV</extra>',
                                   marker={'color': '#724aa2', 'size': 10, 'symbol': 'diamond'}))
    if metric == HEAT_METRIC and not data.get('signal_approaches'):
        signals = [node for node in data['intersections'].values() if node.get('signal_ids')]
        if signals:
            fig.add_trace(go.Scattergl(
                x=[node['coordinates'][0] for node in signals], y=[node['coordinates'][1] for node in signals],
                text=[node['name'] for node in signals],
                customdata=[', '.join(node['signal_ids']) for node in signals],
                mode='markers', name='Semáforos', uid='traffic-signals',
                marker={'color': '#304b54', 'size': 4.5, 'opacity': .7, 'line': {'color': 'white', 'width': .7}},
                hovertemplate='%{text}<br>SUMO %{customdata}<extra>Semáforo</extra>'))
    available = ranking
    if available:
        coord = 'receiver_coordinates' if metric == 'laeq_dba' else 'coordinates'
        color = [state[metric] for _, state in available]
        text = [f'{loc["name"]}<br>{formatted(state["passages"])} passagens · '
                f'LAeq {formatted(state["laeq_dba"], 1)} dB(A)<br>Pico de Lp,A {formatted(state["lp_peak_dba"], 1)} dB(A)'
                for loc, state in available]
        fig.add_trace(go.Scattergl(x=[loc[coord][0] for loc, _ in available], y=[loc[coord][1] for loc, _ in available],
                                   mode='markers', text=text, hovertemplate='%{text}<extra></extra>', name='Cruzamentos',
                                   marker={'color': color, 'size': 13, 'line': {'width': 1.5, 'color': 'white'},
                                           'colorscale': [[0, '#45aab5'], [.55, '#e5ac42'], [1, '#c04b2e']], 'showscale': True,
                                           'colorbar': {'title': {'text': MAP_METRICS[metric], 'side': 'right'},
                                                        'thickness': 9, 'len': .57, 'outlinewidth': 0, 'x': .97}}))
    if data.get('car_positions'):
        fig.add_trace(go.Scattergl(**positions[CAR_TRACE], mode='markers', name=CAR_TRACE, uid='simulated-cars',
                                   marker={'color': '#207a70', 'size': 4, 'opacity': .68},
                                   hovertemplate='%{text}<extra>Carro simulado</extra>'))
    fig.add_trace(go.Scattergl(**positions[BUS_TRACE], mode='markers', name=BUS_TRACE, uid='simulated-buses',
                               marker={'color': BLUE, 'symbol': 'square', 'size': 7, 'line': {'color': 'white', 'width': .7}},
                               hovertemplate='%{text}<extra>Ônibus simulado</extra>'))
    fig.add_trace(go.Scattergl(**positions[GPS_TRACE], mode='markers', name=GPS_TRACE, uid='urbs-gps', visible='legendonly',
                               marker={'color': '#714b96', 'symbol': 'circle-open', 'size': 8},
                               hovertemplate='Linha %{text}<extra>GPS URBS</extra>'))
    return fig


def scenario_indicators(values):
    rows = []
    for label, key, unit in (('Atraso médio', 'delay_s', 's'), ('Tempo médio de viagem', 'travel_s', 's'),
                             ('Maior fila', 'peak_queue_m', 'm'), ('CO₂ direto', 'co2', 'kg')):
        value = values.get(key)
        rows.append(html.Div([
            html.Dt(label),
            html.Dd([html.Strong(formatted(value, 1)), html.Small(unit) if value is not None else None]),
        ]))
    return rows


def create_app(preferred_runs=()):
    app = Dash(__name__, assets_folder=str(ROOT/'assets'), title='Quadrilátero Central | Curitiba')
    app.layout = layout
    store = RunResults()
    config = read_json(ROOT/'config/curitiba.json')

    @app.server.get('/api/v1/runs')
    def runs():
        return jsonify(envelope('runs.catalog', runs=store.listing()))

    @app.server.get('/api/v1/runs/<run>/<resource>')
    def resource(run, resource):
        try:
            if resource == 'frames':
                cursor = request.args.get('after', 0, type=int)
                if cursor < 0:
                    abort(400)
                return Response((json.dumps(f, ensure_ascii=False)+'\n' for f in store.frames(run)[cursor:]),
                                content_type='application/x-ndjson; charset=utf-8')
            if resource == 'window':
                frames = store.frames(run)
                start = request.args.get('start_s', 0, type=int)
                end = request.args.get('end_s', frames[-1]['end_s'] if frames else 0, type=int)
                if not 0 <= start <= end:
                    abort(400)
                return jsonify(summary_payload(run, frames, start, end))
            if resource == 'comparison':
                comparison = store.signal_comparison(run)
                if comparison:
                    return jsonify(comparison)
            if resource in {'metadata', 'map', 'summary', 'status', 'gps', 'bus-journeys', 'traffic-targets'}:
                value = store.data(run, resource+'.json')
                if value is not None:
                    return jsonify(value)
        except KeyError:
            pass
        abort(404)

    @app.server.get('/api/v1/tomtom/latest')
    def latest_flow():
        return jsonify(current_capture())

    @app.server.get('/api/v1/urbs/coverage')
    def coverage():
        paths = sorted((CACHE/'urbs').glob('coverage-*.json'))
        if not paths:
            abort(404)
        return jsonify(read_json(paths[-1]))

    @app.server.get('/docs/arquitetura.md')
    def architecture():
        return send_from_directory(ROOT/'docs', 'arquitetura.md', mimetype='text/plain')

    @lru_cache(maxsize=2)
    def best_comparison(candidates, complete_runs):
        eligible = []
        for run in candidates:
            control = store.data(run, 'summary.json', {}).get('signal_control', {})
            if len(control.get('kennedy_signals', {})) != 8:
                continue
            comparison = store.signal_comparison(run)
            if comparison:
                before = comparison['baseline']['delay_s']
                after = comparison['adaptive']['delay_s']
                if before and after is not None:
                    recorded = all((store.path(key) / 'signal-events.jsonl').is_file()
                                   for key in (run, comparison['baseline_run']))
                    eligible.append((1 - after / before, recorded, run, comparison))
        return max(eligible, default=(0, False, None, None))[3]

    @app.callback(Output('run', 'data'), Input('run-peak', 'value'), Input('tick', 'n_intervals'), State('run', 'data'))
    def select_pair(peak, _tick, previous):
        plan = config['default_signal_plan'].rsplit('/', 1)[-1]
        entries = [entry for entry in store.listing() if entry['metadata'] and
                   entry['metadata'].get('signal_plan') == plan and entry['metadata'].get('preset') == peak
                   and entry['state'] not in ('failed', 'preparing')]
        candidates = tuple(sorted(entry['id'] for entry in entries if entry['state'] == 'complete'
                                  and entry['metadata'].get('signal_control', {}).get('strategy') == 'mqtt-adaptive'))
        complete_runs = tuple(sorted(entry['id'] for entry in entries if entry['state'] == 'complete'))
        comparison = best_comparison(candidates, complete_runs)
        if comparison:
            pair = {'baseline': comparison['baseline_run'], 'adaptive': comparison['run_id'],
                    'comparison': comparison}
        else:
            fixed = [entry['id'] for entry in entries if
                     entry['metadata'].get('signal_control', {}).get('strategy', 'fixed') == 'fixed'
                     and not entry['metadata'].get('eco_approach')]
            baseline = next((run for run in preferred_runs if run in fixed), fixed[0] if fixed else None)
            pair = {'baseline': baseline, 'adaptive': None, 'comparison': None}
        return no_update if pair == previous else pair

    @app.callback(Output('kpis-baseline', 'children'), Output('kpis-adaptive', 'children'),
                  Output('comparison-status', 'children'),
                  Input('run', 'data'))
    def show_indicators(pair):
        pair = pair or {}
        comparison = pair.get('comparison')
        if comparison:
            meta = store.data(pair['adaptive'], 'metadata.json')
            clock = period(meta, [0, meta['duration_s']])
            return (*(scenario_indicators(comparison[side]) for side in ('baseline', 'adaptive')),
                    f'{clock} · indicadores do pico completo')
        baseline = pair.get('baseline')
        summary = store.data(baseline, 'summary.json') if baseline else None
        before = signal_kpis(summary, ()) if summary else {}
        return scenario_indicators(before), scenario_indicators({}), 'Aguardando um par concluído da Onda Verde e do MQTT.'

    @app.callback(Output('map-note', 'children'), Input('map-metric', 'value'))
    def map_note(metric):
        if metric == HEAT_METRIC:
            return 'A escala é a mesma nos dois mapas e soma a presença de carros e ônibus desde o início do pico.'
        return 'As cores dos cruzamentos resumem o indicador do pico. A reprodução mostra o mesmo horário nos dois mapas.'

    app.clientside_callback(
        ClientsideFunction(namespace='mapPlayback', function_name='capturePairViewport'),
        Output('map-viewport', 'data'), Input('map-baseline', 'relayoutData'), Input('map-adaptive', 'relayoutData'),
        State('map-render-baseline', 'data'), State('map-render-adaptive', 'data'), State('map-viewport', 'data'),
        prevent_initial_call=True,
    )
    for side in ('baseline', 'adaptive'):
        app.clientside_callback(
            ClientsideFunction(namespace='mapPlayback', function_name='renderMap'),
            Output(f'map-{side}', 'figure'), Input(f'map-render-{side}', 'data'),
            Input('map-gesture', 'data'), Input('map-viewport', 'data'),
        )
    app.clientside_callback(
        'function(disabled, gesturing) { return disabled || gesturing; }',
        Output('map-tick', 'disabled'), Input('map-tick-disabled', 'data'), Input('map-gesture', 'data'),
    )

    def render_run_map(run, data, frames, metric, revision, cursor, running, speed, previous):
        changed = [run, metric] != previous.get('view')
        count_changed = len(frames) != previous.get('count')
        state = {'view': [run, metric], 'count': len(frames)}
        if not data:
            redraw = changed or previous.get('had_map')
            return (empty_figure('Aguardando dados da simulação') if redraw else no_update), state, ''

        approaches = data.get('signal_approaches', [])
        recording = store.frames(run, 'signal-events.jsonl') if approaches else ()
        rebuild = (changed or not previous.get('had_map') or bool(recording) != previous.get('signals_recorded', False)
                   or (metric != HEAT_METRIC and count_changed))

        completed = bisect_right(frames, cursor, key=lambda frame: frame['end_s'])
        frame = frames[completed-1] if completed else None
        end_s = frame['end_s'] if frame else None
        frame_changed = end_s != previous.get('end_s')
        cursor_changed = cursor != previous.get('cursor_s')
        traces = previous.get('traces', {})
        heat_s = previous.get('heat_s')
        grid = data.get('traffic_grid')
        heat_step = 2 * speed * PLAYBACK_TICK_MS * PLAYBACK_RATE / 1000
        heat_changed = metric == HEAT_METRIC and grid and (
            rebuild or (not running and heat_s != cursor)
            or (cursor_changed and (heat_s is None or cursor - heat_s >= heat_step or frame_changed)))
        heat = accumulated_traffic(grid, frames, completed, cursor) if heat_changed else None
        dense = bool(frames and data.get('position_interval_s'))
        position_changed = rebuild or frame_changed or (dense and cursor_changed)
        if position_changed:
            snapshot = playback_positions(store, run, frames, completed, cursor) if dense else None
            gps = store.data(run, 'gps.json', {}).get('samples', [])
            positions = map_positions(frame, gps, 0, snapshot, data.get('bus_lines', {}))

        signal_second = min(int(cursor), recording[-1]['time_s']) if recording else None
        signal_changed = bool(recording and (rebuild or signal_second != previous.get('signal_second')))
        mqtt_summary = previous.get('mqtt_summary', '')
        if signal_changed:
            lamps, recent = signal_activity(recording, cursor)
            colors, states = signal_colors(approaches, lamps)
            mqtt = mqtt_markers(data['intersections'], recent)
            mqtt_summary = ''
            if recent:
                packet = recent[-1]
                reply = ('sem resposta' if packet['decisions'] is None
                         else f'propostas ({len(packet["decisions"])})')
                mqtt_summary = (f'MQTT · t={packet["time_s"]} s · envio → broker ({len(packet["observed"])})'
                                f' · {reply} · ajustes aplicados ({len(packet["applied"])})')
        figure = no_update
        if rebuild:
            junctions = [] if metric == HEAT_METRIC else junction_metrics(window_summary(frames), data, metric)
            figure = map_figure(data, junctions, positions, metric, revision, heat=heat)
            if recording:
                figure.add_trace(go.Scattergl(
                    x=[lane['point'][0] for lane in approaches], y=[lane['point'][1] for lane in approaches],
                    text=[lane['street'] for lane in approaches], customdata=states, mode='markers',
                    name=SIGNAL_TRACE, uid='traffic-light-lanes', marker={'color': colors, 'size': 6,
                    'line': {'color': '#f9fffd', 'width': .6}},
                    hovertemplate='%{text}<br>Movimentos SUMO: %{customdata}<extra>Semáforo por faixa</extra>'))
                figure.add_trace(go.Scattergl(**mqtt, name=MQTT_TRACE, uid='mqtt-messages', mode='markers',
                                             hovertemplate='%{text}<extra>MQTT</extra>'))
            traces = {trace.name: i for i, trace in enumerate(figure.data)
                      if trace.name in (CAR_TRACE, BUS_TRACE, GPS_TRACE, HEAT_TRACE, SIGNAL_TRACE, MQTT_TRACE)}
        elif position_changed or heat_changed or signal_changed:
            figure = Patch()
            if position_changed:
                for trace, fields in positions.items():
                    if trace in traces and (trace != GPS_TRACE or frame_changed):
                        for field, value in fields.items():
                            figure['data'][traces[trace]][field] = value
            if heat_changed:
                for field, value in heat.items():
                    figure['data'][traces[HEAT_TRACE]][field] = value
            if signal_changed:
                figure['data'][traces[SIGNAL_TRACE]]['marker']['color'] = colors
                figure['data'][traces[SIGNAL_TRACE]]['customdata'] = states
                for field, value in mqtt.items():
                    figure['data'][traces[MQTT_TRACE]][field] = value
        state.update(had_map=True, end_s=end_s, cursor_s=cursor, heat_s=cursor if heat_changed else heat_s, traces=traces,
                     signal_second=signal_second, signals_recorded=bool(recording), mqtt_summary=mqtt_summary)
        return figure, state, mqtt_summary

    @app.callback(Output('map-render-baseline', 'data'), Output('map-render-adaptive', 'data'),
                  Output('map-playback', 'data'), Output('map-tick-disabled', 'data'),
                  Output('map-play', 'children'), Output('map-play', 'disabled'), Output('map-restart', 'disabled'),
                  Output('map-time', 'children'), Output('map-progress', 'value'), Output('map-progress', 'max'),
                  Output('map-progress', 'disabled'), Output('mqtt-activity', 'children'),
                  Input('run', 'data'), Input('map-metric', 'value'),
                  Input('tick', 'n_intervals'), Input('map-tick', 'n_intervals'), Input('map-play', 'n_clicks'),
                  Input('map-restart', 'n_clicks'), Input('map-progress', 'value'), Input('map-scrub', 'data'),
                  State('map-speed', 'value'), State('map-playback', 'data'))
    def play_maps(pair, metric, _refresh, _frame_tick, _play, _restart, seek, _scrub, speed, previous):
        pair, previous = pair or {}, previous or {}
        run_ids = [pair.get('baseline'), pair.get('adaptive')]
        map_data = [store.data(run, 'map.json') if run else None for run in run_ids]
        frames = [store.frames(run) if data else () for run, data in zip(run_ids, map_data)]
        meta = store.data(run_ids[0], 'metadata.json') if run_ids[0] else None
        required = frames if run_ids[1] else frames[:1]
        last_s = min(batch[-1]['end_s'] if batch else 0 for batch in required)
        active = bool(run_ids[0] and not run_ids[1] and meta and last_s < meta['duration_s']
                      and store.data(run_ids[0], 'status.json', {}).get('state') == 'running')
        playable = last_s > 0
        changed = run_ids != previous.get('runs')
        cursor = 0 if changed else previous.get('cursor_s', 0)
        running = playable and metric == HEAT_METRIC if changed else previous.get('running', False)
        speed = speed if speed in PLAYBACK_SPEEDS else 1
        triggered = ctx.triggered_prop_ids
        if not changed:
            if 'map-progress.value' in triggered and seek is not None:
                cursor, running = seek, False
            elif 'map-scrub.data' in triggered:
                running = False
            elif 'map-restart.n_clicks' in triggered:
                cursor, running = 0, False
            elif 'map-play.n_clicks' in triggered and playable:
                running = not running
                if running and cursor >= last_s and not active:
                    cursor = 0
            elif 'map-tick.n_intervals' in triggered and running:
                cursor = min(cursor + speed * PLAYBACK_TICK_MS * PLAYBACK_RATE / 1000, last_s)
                running = cursor < last_s or active
        cursor = max(0, min(cursor, last_s))
        revision = run_ids[1] or run_ids[0]
        graphs = [render_run_map(run, data, batch, metric, revision, cursor, running, speed,
                                 {} if changed else old)
                  for run, data, batch, old in zip(run_ids, map_data, frames, previous.get('maps', [{}, {}]))]
        figures, rendered, mqtt = zip(*graphs)
        state = {'runs': run_ids, 'cursor_s': cursor, 'running': running, 'maps': list(rendered)}
        seek_limit = last_s // WINDOW_STEP_S * WINDOW_STEP_S
        seek_value = int(cursor // WINDOW_STEP_S) * WINDOW_STEP_S
        clock = period(meta, [0, cursor]).split('–')[1] if meta and playable else '—'
        if state == previous and all(figure is no_update for figure in figures):
            return (no_update,) * 12
        mqtt_label = mqtt[1] or ('MQTT · sem envio neste instante' if rendered[1].get('signal_second') is not None
                                else 'MQTT · mensagens indisponíveis neste replay')
        return (*figures, state, not running, 'Pausar' if running else 'Reproduzir',
                not playable, not playable, clock, seek_value if seek != seek_value else no_update,
                max(WINDOW_STEP_S, seek_limit), not seek_limit, mqtt_label)

    @app.callback(Output('live-status', 'children'), Input('run', 'data'), Input('tick', 'n_intervals'))
    def show_run_status(pair, _tick):
        run = (pair or {}).get('baseline')
        state = store.data(run, 'status.json', {}).get('state') if run else None
        return html.Span(STATE_LABELS.get(state, 'Sem simulação'), className='badge ' + (state or 'empty'))

    return app

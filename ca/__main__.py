import argparse
import logging
import re
import sys
from argparse import Namespace
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from math import isfinite
from pathlib import Path
from threading import Thread

from .io import CACHE, LOCAL, PRESETS, ROOT, envelope, read_json, reference_dir, utc, window, write_json
from .signal_control import CONTROL_OPTIONS, CYCLE_STRATEGIES, FEEDBACK_STRATEGIES, strategy_for_peak


def scenario(network_path, reference, config, args, load_traffic=None, od=None):
    from .demand import build_routes, equip_eco_approach
    from .experiments import fingerprint, finish_run
    from .learning import model_path
    from .metrics import CountValidation, timed_rows
    from .network import RoadNetwork
    from .queues import QUEUE_GAP_M, QUEUE_STOP_SPEED_MPS
    from .signals import mqtt_endpoint
    from .simulate import run_sumo, setup_sumo
    from .traffic import REFERENCE_STATS, demand_observations, hourly_shape
    from .transit import match_buses

    begin, end = window(args.date, args.peak, args.start, args.end)
    preset = 'personalizada' if args.start else args.peak
    strategy = strategy_for_peak(args.control, config, preset)
    model = model_path(config, preset, strategy, args.model)
    if args.mqtt_control and strategy in ('fixed', *CYCLE_STRATEGIES, *FEEDBACK_STRATEGIES):
        raise ValueError('A estratégia da janela precisa admitir extensão via MQTT.')
    signals = args.signals or ROOT / config['default_signal_plan']
    duration = int((end-begin).total_seconds())
    if duration < 30 or not isfinite(args.car_scale) or args.car_scale < 0:
        raise ValueError('Use uma janela de pelo menos 30 s e uma escala de carros maior ou igual a zero.')
    if args.live_flow and (args.traffic_stats or args.stats_timeset is not None):
        raise ValueError('Use --live-flow ou selecione um relatório histórico com --traffic-stats.')
    gps_day = args.urbs_date or begin.date()
    if gps_day > begin.date():
        raise ValueError('A data de referência do GPS deve ser igual ou anterior à do cenário.')
    gps_begin, gps_end = begin - (begin.date()-gps_day), end - (begin.date()-gps_day)
    run_id = args.name or f'{args.date}-{preset}-{begin:%H%M}-{end:%H%M}'
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,69}', run_id):
        raise ValueError('Use um nome de simulação curto com letras minúsculas, números, hífen e sublinhado.')
    folder = ROOT / 'runs' / run_id
    try:
        folder.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise ValueError(f'Execução existente: {run_id}. Escolha outro --name.') from None
    status = lambda state, **details: write_json(folder / 'status.json', envelope('simulation.status', state=state, **details))
    status('preparing')
    publisher = None
    try:
        print(f'Preparando {run_id} em {folder}', flush=True)
        network = RoadNetwork(network_path, config)
        profile_path = None
        profile = {}
        if load_traffic is not None:
            traffic = load_traffic(network, preset)
        else:
            stats = None if args.live_flow else args.traffic_stats or reference / REFERENCE_STATS
            traffic = demand_observations(network, stats, args.stats_timeset, begin, end)
            if args.live_flow and not traffic['live_edges']:
                raise ValueError('Nenhuma velocidade TomTom da janela pôde ser associada à rede. Capture no horário escolhido.')
            if not args.live_flow:
                profile_path = reference / 'data/tomtom/2026-06-20T17_05_59.764Z.geojson'
                profile = hourly_shape(profile_path, begin, end)
        write_json(folder / 'traffic-targets.json', traffic)
        buses, telemetry, gps = match_buses(network, gps_begin, gps_end, config['bbox'])
        telemetry['gps_date'] = gps_day.isoformat()
        journeys = telemetry.pop('journeys')
        if not buses and not args.allow_no_urbs:
            raise ValueError('A janela não produziu rotas URBS. Verifique os arquivos e a cobertura de GPS.')
        write_json(folder / 'bus-journeys.json', envelope('urbs.journeys', journeys=journeys))
        write_json(folder / 'gps.json', envelope('urbs.map_samples', samples=gps))
        print(f'URBS: {len(buses)} rotas de GPS e {telemetry["matched_points"]} pontos associados', flush=True)
        validation = CountValidation(timed_rows(args.counts, 'counts', begin, end), network.edges)
        noise = timed_rows(args.noise, 'measurements', begin, end)
        for row in noise:
            if not (row.get('intersection_id') and row.get('source') and row.get('measurement_kind') in ('residual', 'total')
                    and isinstance(row.get('laeq_dba'), (int, float)) and isfinite(row['laeq_dba'])):
                raise ValueError('Medição acústica inválida. Consulte docs/arquitetura.md.')
        demand = build_routes(folder / 'demand.rou.xml', network, config, traffic['edges'], profile,
                              begin, duration, preset, args.car_scale, buses, od)
        if args.eco_approach:
            equip_eco_approach(folder / 'demand.rou.xml', config['eco_approach'])
        cfg = setup_sumo(folder, network_path, duration, config['seed'], signals)
        metadata = envelope('scenario.metadata', run_id=run_id, name=config['name'], preset=preset,
                            start=utc(begin), end=utc(end), timezone=str(LOCAL), duration_s=duration,
                            aggregation_seconds=config['aggregation_seconds'], seed=config['seed'],
                            demand=demand, urbs=telemetry, tomtom={k: v for k, v in traffic.items() if k != 'edges'},
                            hourly_profile={'file': profile_path.name if profile else None, 'factors': profile},
                            fleet=config['fleet'], car_scale=args.car_scale, acoustics=config['acoustics'],
                            pedestrian_demand=config['pedestrian_demand'],
                            ippuc={'source': network.ippuc.get('source'), 'features': len(network.ippuc.get('features', []))},
                            field_count_intervals=len(validation.rows), noise_measurements=noise,
                            queue_measurement={'method': 'connected_lanes', 'max_gap_m': QUEUE_GAP_M,
                                               'stop_speed_mps': QUEUE_STOP_SPEED_MPS},
                            signal_control={'strategy': strategy, 'requested': args.control,
                                            'mqtt_control': args.mqtt_control,
                                            'model_sha256': fingerprint(model) if model else None},
                            signals=signals.name, signal_plan=signals.name)
        if args.eco_approach:
            metadata['eco_approach'] = {**config['eco_approach'], 'demand_sha256': fingerprint(folder / 'demand.rou.xml')}
        write_json(folder / 'metadata.json', metadata)
        publisher = mqtt_endpoint(args.mqtt, run_id, strategy, args.mqtt_control)
        status('running')
        print(f'Executando SUMO: {demand["cars"]} carros, {demand["buses"]} ônibus, '
              f'{demand["pedestrians"]} pedestres e {demand["bicycles"]} bicicletas', flush=True)
        result = run_sumo(folder, cfg, network, config, begin, duration, validation, demand['pedestrian_sites'], publisher,
                          strategy=strategy, bus_lines={j['id']: j['line_id'] for j in journeys},
                          targets=traffic['edges'], model=model)
        totals = finish_run(folder, result)['totals']
        status('complete')
        print(f'Concluído: {run_id} | {totals["mass_kg"]["co2"]:.2f} kg CO2 | GEH: {result["geh"]["status"]}', flush=True)
    except (Exception, KeyboardInterrupt) as exc:
        status('failed', error=str(exc) or type(exc).__name__)
        raise
    finally:
        if publisher:
            publisher.close()


def run_monthly(network_path, reference, config, args):
    from .monthly import monthly_report, previous_month, urbs_reference
    from .origin_destination import monthly_matrices
    from .traffic import monthly_observations

    first, last = previous_month(datetime.now(LOCAL).date())
    if args.month:
        if not re.fullmatch(r'[0-9]{4}-(0[1-9]|1[0-2])', args.month):
            raise ValueError('Informe um mês válido no formato AAAA-MM.')
        selected = date.fromisoformat(args.month + '-01')
        if selected > first:
            raise ValueError('Escolha um mês civil que já terminou.')
        first = selected
        last = first.replace(day=monthrange(first.year, first.month)[1])
    print(f'Mês de referência: {first:%d/%m/%Y} a {last:%d/%m/%Y}', flush=True)
    report, date_id, time_ids = monthly_report(config, first, last, args.traffic_stats)
    od = None if args.sem_od else monthly_matrices(config['bbox'], first, last)
    day = urbs_reference(first, last, config['bbox'], args.urbs_date)

    def load_traffic(network, peak):
        return monthly_observations(network, report, date_id, time_ids[peak], first, last)

    run_peaks(network_path, reference, config, args, day, f'mensal-{first:%Y-%m}', load_traffic, od)


def run_offline(network_path, reference, config, args):
    from .sources import cached_urbs_reference
    from .traffic import REFERENCE_STATS, historical_stats, offline_observations

    report = reference / REFERENCE_STATS
    segments, metadata = historical_stats(report, speed_field='averageSpeed')
    periods = [(date.fromisoformat(row['from']), date.fromisoformat(row['to']))
               for row in metadata.get('dateRanges', [])]
    if not periods:
        raise ValueError('O relatório offline da TomTom precisa informar o período das observações.')
    for first, last in periods:
        print(f'TomTom offline: {first:%d/%m/%Y} a {last:%d/%m/%Y}', flush=True)
    day = cached_urbs_reference(config['bbox'], periods, args.urbs_date)

    def load_traffic(network, _peak):
        return offline_observations(network, report, segments, metadata)

    run_peaks(network_path, reference, config, args, day, f'offline-{day}', load_traffic)


def run_peaks(network_path, reference, config, args, day, prefix, load_traffic, od=None):
    from .network import build_network

    print(f'URBS: dia útil de referência {day:%d/%m/%Y}', flush=True)
    if not network_path.is_file():
        network_path = build_network(reference/'data/map/curitiba.osm', config['bbox'])
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
    run_ids = {peak: f'{prefix}-{peak}-{stamp}' for peak in PRESETS}
    server = None
    if not args.no_dashboard:
        from werkzeug.serving import make_server

        from .dashboard import create_app

        app = create_app(preferred_runs=tuple(run_ids.values()))
        server = make_server(args.host, args.port, app.server, threaded=True)
        dashboard_thread = Thread(target=server.serve_forever, daemon=True)
        dashboard_thread.start()
        print(f'Dash: http://{args.host}:{args.port}', flush=True)
    try:
        for peak, run_id in run_ids.items():
            scenario_args = Namespace(date=day.isoformat(), peak=peak, start=None, end=None, name=run_id,
                                      live_flow=False, traffic_stats=None, stats_timeset=None, urbs_date=day,
                                      counts=args.counts, noise=args.noise, signals=args.signals,
                                      car_scale=args.car_scale, allow_no_urbs=False, mqtt=args.mqtt, control=args.control,
                                      mqtt_control=args.mqtt_control, model=args.model, eco_approach=args.eco_approach)
            peak_od = {'analysis_id': od[0], 'pairs': od[1][peak]} if od else None
            scenario(network_path, reference, config, scenario_args, load_traffic, peak_od)
        if server is not None:
            dashboard_thread.join()
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()


def dashboard_options(parser):
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8050)


def scenario_options(parser):
    parser.add_argument('--counts', type=Path)
    parser.add_argument('--noise', type=Path)
    parser.add_argument('--signals', type=Path)
    parser.add_argument('--car-scale', type=float, default=1.)
    eco_approach_option(parser)
    mqtt_options(parser)
    parser.add_argument('--control', choices=CONTROL_OPTIONS, default='fixed', help='Estratégia semafórica')
    parser.add_argument('--model', type=Path, help='Modelo JSON para --control ml ou ml-online')


def eco_approach_option(parser):
    parser.add_argument('--eco-approach', action='store_true',
                        help='Ajusta a velocidade dos carros na aproximação dos semáforos (GLOSA)')


def mqtt_options(parser):
    parser.add_argument('--mqtt', metavar='HOST[:PORTA]')
    parser.add_argument('--mqtt-control', action='store_true',
                        help='Recebe solicitações de extensão de verde do broker local')


def main():
    parser = argparse.ArgumentParser(prog='python -m ca')
    parser.add_argument('--reference', type=Path, help='Pasta Sumo-CAmbiente-main')
    sub = parser.add_subparsers(dest='command')
    run = sub.add_parser('run', help='Executa os dois picos e abre o Dash')
    sources = run.add_mutually_exclusive_group()
    sources.add_argument('--traffic-stats', type=Path, help='Importa o GeoJSON do mês de referência')
    sources.add_argument('--offline', action='store_true', help='Usa o relatório TomTom da pasta de referência e o cache URBS')
    run.add_argument('--month', metavar='AAAA-MM', help='Seleciona outro mês civil completo para o Traffic Stats')
    run.add_argument('--sem-od', action='store_true', help='Usa a demanda estimada pela malha sem consultar a matriz O/D')
    run.add_argument('--urbs-date', type=date.fromisoformat, help='Sobrescreve o dia útil de referência da URBS')
    run.add_argument('--no-dashboard', action='store_true', help='Gera os resultados sem iniciar o servidor Dash')
    dashboard_options(run)
    scenario_options(run)
    sub.add_parser('network', help='Gera a rede SUMO a partir da malha OSM da referência')
    sub.add_parser('ippuc', help='Importa ciclovias e ciclofaixas oficiais do GeoCuritiba')
    urbs = sub.add_parser('urbs', help='Baixa os sete arquivos diários URBS e o GPS complementar')
    urbs.add_argument('--through', default=(datetime.now(LOCAL).date()-timedelta(days=1)).isoformat())
    urbs.add_argument('--audit', action='store_true', help='Conta os registros pelas datas efetivas no campo DTHR')
    flow = sub.add_parser('tomtom', help='Faz captura de velocidade e tempo de viagem nas vias do recorte')
    flow.add_argument('--points', type=int, default=16, choices=range(1, 65), metavar='1..64')
    sim = sub.add_parser('simulate', help='Executa o cenário e publica os resultados em JSONL')
    sim.add_argument('--date', required=True)
    sim.add_argument('--peak', choices=('manha', 'tarde'), default='tarde')
    sim.add_argument('--start')
    sim.add_argument('--end')
    sim.add_argument('--name')
    sim.add_argument('--traffic-stats', type=Path)
    sim.add_argument('--stats-timeset', type=int)
    sim.add_argument('--live-flow', action='store_true', help='Usa somente velocidades TomTom capturadas dentro da janela')
    sim.add_argument('--urbs-date', type=date.fromisoformat, help='Data de referência do GPS, alinhada pelo horário local')
    scenario_options(sim)
    sim.add_argument('--allow-no-urbs', action='store_true')
    replay = sub.add_parser('replay', help='Repete a demanda de uma execução fixa com outro controle semafórico')
    replay.add_argument('reference_run', help='Identificador da execução fixa em runs/')
    replay.add_argument('--name', required=True, help='Identificador da nova execução')
    replay.add_argument('--sumo-seed', type=int, help='Varia a aleatoriedade do SUMO com a mesma demanda gravada')
    replay.add_argument('--control', choices=CONTROL_OPTIONS, required=True)
    replay.add_argument('--signals', type=Path, help='Aplica um plano semafórico SUMO adicional à repetição')
    replay.add_argument('--model', type=Path, help='Modelo JSON para --control ml ou ml-online')
    replay.add_argument('--train', action='store_true', help='Treina o modelo durante a repetição e salva signal-model.json')
    eco_approach_option(replay)
    mqtt_options(replay)
    replay.add_argument('--summary-only', action='store_true', help='Grava os blocos de KPIs sem trajetórias de 2 s')
    serve = sub.add_parser('serve', help='Abre o servidor do painel Plotly Dash')
    dashboard_options(serve)
    args = parser.parse_args()
    if args.command is None:
        reference_override = args.reference
        args = parser.parse_args(['run'])
        args.reference = reference_override
    if args.command == 'run' and args.offline and args.month:
        run.error('Use --month no fluxo mensal do Traffic Stats.')
    if getattr(args, 'mqtt_control', False) and (not args.mqtt or args.control == 'fixed'):
        parser.error('--mqtt-control exige --mqtt e uma estratégia dinâmica.')
    if getattr(args, 'control', None) == 'mqtt-adaptive' and (not args.mqtt or args.mqtt_control):
        parser.error('mqtt-adaptive exige --mqtt e já inclui o controlador.')
    config = read_json(ROOT/'config/curitiba.json')
    reference = reference_dir(args.reference)
    network_path = CACHE/'network/curitiba.net.xml'
    try:
        if args.command == 'run':
            execute = run_offline if args.offline else run_monthly
            execute(network_path, reference, config, args)
        elif args.command == 'replay':
            from .experiments import replay as replay_scenario

            if not all(re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,69}', key) for key in (args.reference_run, args.name)):
                raise ValueError('Use identificadores de execução com letras minúsculas, números, hífen e sublinhado.')
            replay_scenario(ROOT/'runs'/args.reference_run, ROOT/'runs'/args.name, config, args.control, args.mqtt,
                            args.mqtt_control, not args.summary_only, args.signals, args.model, args.train, args.sumo_seed,
                            eco_approach=args.eco_approach)
        elif args.command == 'serve':
            from .dashboard import create_app
            create_app().run(host=args.host, port=args.port, debug=False, load_dotenv=False)
        elif args.command == 'urbs':
            from .sources import audit_week, fetch_week
            through = date.fromisoformat(args.through)
            path, records = fetch_week(through)
            unavailable = [r for r in records if r['status'] == 'unavailable']
            print(f'{len(records)-len(unavailable)}/{len(records)} arquivos disponíveis. {path}')
            for row in unavailable:
                print(f'{row["file"]}: {row["error"]}')
            if args.audit:
                print(audit_week(through, config['bbox']))
            return 1 if unavailable else 0
        elif args.command == 'ippuc':
            from .sources import fetch_ippuc
            path, count = fetch_ippuc(config['bbox'])
            print(f'{count} feições cicloviárias. {path}')
        else:
            from .network import RoadNetwork, build_network
            if args.command == 'network' or not network_path.exists():
                network_path = build_network(reference/'data/map/curitiba.osm', config['bbox'])
            if args.command == 'network':
                print(network_path)
            elif args.command == 'tomtom':
                from .sources import fetch_flow
                points = RoadNetwork(network_path, config).flow_points(args.points)
                if not points:
                    raise ValueError('Não há pontos de amostragem nos corredores configurados.')
                path, count, errors = fetch_flow(points)
                print(f'{count} observações, {errors} falhas. {path}')
                return 1 if errors else 0
            else:
                scenario(network_path, reference, config, args)
    except (OSError, ValueError) as exc:
        print(f'Erro: {exc}', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())

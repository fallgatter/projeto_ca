import hashlib
import json
from datetime import datetime
from shutil import copyfile
from xml.etree.ElementTree import SubElement, parse

from .demand import equip_eco_approach
from .io import envelope, read_json, write_json
from .learning import model_path
from .metrics import CountValidation, pedestrian_trip_info, window_summary
from .network import RoadNetwork
from .signal_control import CYCLE_STRATEGIES, FEEDBACK_STRATEGIES, strategy_for_peak
from .signals import mqtt_endpoint
from .simulate import run_sumo


def fingerprint(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def finish_run(folder, result):
    with (folder / 'frames.jsonl').open(encoding='utf-8') as stream:
        totals = window_summary(json.loads(line) for line in stream)
    summary = envelope('simulation.summary', **result, totals=totals,
                       pedestrians=pedestrian_trip_info(folder / 'trips.xml'))
    write_json(folder / 'summary.json', summary)
    return summary


def replay(source, folder, config, requested, mqtt=None, mqtt_control=False, record_positions=True, signals=None,
           model=None, train=False, sumo_seed=None, *, eco_approach=False):
    if read_json(source / 'status.json')['state'] != 'complete':
        raise ValueError('Selecione uma execução de referência concluída.')
    meta = read_json(source / 'metadata.json')
    if meta.get('signal_control', {}).get('strategy', 'fixed') != 'fixed':
        raise ValueError('Selecione uma execução de referência com tempos fixos.')
    already_equipped = meta.get('eco_approach')
    if already_equipped:
        already_equipped.pop('baseline_run', None)
    strategy = strategy_for_peak(requested, config, meta['preset'])
    model = model_path(config, meta['preset'], strategy, model, train)
    if mqtt_control and strategy in ('fixed', *CYCLE_STRATEGIES, *FEEDBACK_STRATEGIES):
        raise ValueError('A estratégia da janela precisa admitir extensão via MQTT.')
    start = datetime.fromisoformat(meta['start'])
    duration = meta['duration_s']
    config = {**config, 'bbox': read_json(source / 'map.json')['bbox'], 'seed': meta['seed'],
              'aggregation_seconds': meta['aggregation_seconds'],
              'acoustics': meta['acoustics']}
    cfg = parse(source / 'baseline.sumocfg')
    if sumo_seed is not None:
        if not 0 <= sumo_seed <= 2147483647:
            raise ValueError('Use uma semente SUMO de 0 a 2147483647.')
        cfg.getroot().find('random_number/seed').set('value', str(sumo_seed))
        config['seed'] = sumo_seed
    inputs = cfg.getroot().find('input')
    net_ref = inputs.find('net-file')
    network_path = (source / net_ref.get('value')).resolve()
    net_ref.set('value', str(network_path))
    routes = inputs.find('route-files')
    demand_path = (source / routes.get('value')).resolve()
    routes.set('value', 'demand.rou.xml')
    additional_ref = inputs.find('additional-files')
    extra = [(source / p.strip()).resolve() for p in additional_ref.get('value').split(',')] if additional_ref is not None else []
    if signals is not None:
        signals = signals.resolve()
        if additional_ref is None:
            additional_ref = SubElement(inputs, 'additional-files')
        meta['signal_plan'] = signals.name
    if additional_ref is not None:
        files = [str(path) for path in extra]
        if signals is not None:
            files.append('signal-plan.add.xml')
        additional_ref.set('value', ','.join(files))
    cfg.getroot().find('output/tripinfo-output').set('value', 'trips.xml')
    targets_path = source / 'traffic-targets.json'
    inputs_hash = {'network': fingerprint(network_path), 'demand': fingerprint(demand_path),
                   'traffic_targets': fingerprint(targets_path),
                   'signals': [fingerprint(p) for p in [*extra, signals] if p is not None],
                   'sumocfg': fingerprint(source / 'baseline.sumocfg')}
    if sumo_seed is not None and sumo_seed != meta['seed']:
        inputs_hash['sumo_seed_override'] = sumo_seed
    meta.update(run_id=folder.name, reference_run=source.name, inputs_sha256=inputs_hash, seed=config['seed'],
                signal_control={'strategy': strategy, 'requested': requested, 'mqtt_control': mqtt_control,
                                'training': train, 'model_sha256': fingerprint(model) if model else None})
    folder.mkdir(parents=True, exist_ok=False)

    def status(state, **details):
        write_json(folder / 'status.json', envelope('simulation.status', state=state, **details))

    status('preparing')
    publisher = None
    try:
        cfg_path = folder / 'baseline.sumocfg'
        cfg.write(cfg_path, encoding='utf-8', xml_declaration=True)
        if signals is not None:
            frozen_plan = folder / 'signal-plan.add.xml'
            copyfile(signals, frozen_plan)
            if fingerprint(frozen_plan) != inputs_hash['signals'][-1]:
                raise ValueError('O plano semafórico mudou durante a cópia.')
        copyfile(demand_path, folder / 'demand.rou.xml')
        if eco_approach:
            settings = config['eco_approach']
            equip_eco_approach(folder / 'demand.rou.xml', settings)
            meta['eco_approach'] = {**settings, 'demand_sha256': fingerprint(folder / 'demand.rou.xml')}
            if not already_equipped and strategy == 'fixed' and signals is None and 'sumo_seed_override' not in inputs_hash:
                meta['eco_approach']['baseline_run'] = source.name
        for name in ('gps.json', 'bus-journeys.json', 'traffic-targets.json'):
            copyfile(source / name, folder / name)
        write_json(folder / 'metadata.json', meta)
        journeys = read_json(folder / 'bus-journeys.json')['journeys']
        rows = read_json(source / 'summary.json')['geh']['rows']
        network = RoadNetwork(network_path, config)
        validation = CountValidation(rows, network.edges)
        publisher = mqtt_endpoint(mqtt, folder.name, strategy, mqtt_control)
        status('running')
        print(f'{folder.name}: {strategy} | {duration} s | referência {source.name}', flush=True)
        result = run_sumo(folder, cfg_path, network, config, start, duration, validation,
                          meta['demand']['pedestrian_sites'], publisher, strategy=strategy,
                          bus_lines={row['id']: row['line_id'] for row in journeys},
                          targets=read_json(folder / 'traffic-targets.json')['edges'], record_positions=record_positions,
                          model=model, train=train)
        summary = finish_run(folder, result)
        status('complete')
        print(f'{folder.name}: concluída | {summary["totals"]["mass_kg"]["co2"]:.2f} kg de CO2', flush=True)
        return summary
    except (Exception, KeyboardInterrupt) as exc:
        status('failed', error=str(exc) or type(exc).__name__)
        raise
    finally:
        if publisher:
            publisher.close()

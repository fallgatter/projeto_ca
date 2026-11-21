import gzip
import json
from collections import Counter, defaultdict
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from random import Random
from shutil import copyfile
from time import perf_counter
from xml.etree import ElementTree as ET
from xml.etree.ElementTree import Element, ElementTree, SubElement, indent

from .io import CACHE, LOCAL, ROOT, read_json, sumo_binary, sumo_modules, write_json
from .queues import QUEUE_STOP_SPEED_MPS, QueueMonitor

from .demand import stagger_cars
from .network import Network


PROJECT = Path(__file__).resolve().parent
OUTPUT = PROJECT / 'results_mpc'
PROFILES = {'original': OUTPUT, 'escalonado': PROJECT/'results_fluxo'}
CHUNK = 60
FRAME = 2
BIN = 900
MODES = ('carros', 'onibus')
WARMUP = 300


def source_for(peak):
    return ROOT / 'runs' / f'mensal-2026-07-{peak}-20261119-235229-202742'


def setup_sumo(folder, net_path, duration, seed, signals):
    root = Element('configuration')
    entry = SubElement(root, 'input')
    SubElement(entry, 'net-file', value=str(net_path))
    SubElement(entry, 'route-files', value='demand.rou.xml')
    if signals:
        SubElement(entry, 'additional-files', value=str(signals.resolve()))
    time = SubElement(root, 'time')
    SubElement(time, 'begin', value='0')
    SubElement(time, 'end', value=str(duration))
    SubElement(time, 'step-length', value='1')
    SubElement(SubElement(root, 'random_number'), 'seed', value=str(seed))
    SubElement(SubElement(root, 'processing'), 'pedestrian.model', value='striping')
    routing = SubElement(root, 'routing')
    SubElement(routing, 'device.rerouting.period', value='120')
    SubElement(routing, 'device.rerouting.adaptation-interval', value='15')
    SubElement(routing, 'device.rerouting.adaptation-weight', value='0.6')
    SubElement(routing, 'device.rerouting.threshold.factor', value='1.1')
    SubElement(SubElement(root, 'output'), 'tripinfo-output', value='trips.xml')
    indent(root)
    target = folder / 'baseline.sumocfg'
    ElementTree(root).write(target, encoding='UTF-8', xml_declaration=True)
    return target


def digest(path):
    with path.open('rb') as stream:
        return sha256(stream.read()).hexdigest()


def write_chunk(folder, index, frames):
    with gzip.open(folder / f'{index}.json.gz', 'wt', encoding='utf-8', compresslevel=2) as stream:
        json.dump(frames, stream, separators=(',', ':'))


def demand(source, destination, duration, training, seed, profile='original'):
    if not training and profile == 'original':
        copyfile(source, destination)
        return
    root = ET.parse(source).getroot()
    if profile == 'escalonado':
        stagger_cars(root, duration, seed, BIN)
    else:
        rng = Random(seed)
        for child in root.findall('vehicle'):
            if child.get('id').startswith('car-'):
                time = float(child.get('depart')) + rng.randint(-120, 120)
                child.set('depart', str(round(max(0, min(duration-1, time)))))
    root[:] = sorted(root, key=lambda item: float(item.get('depart', '-1')))
    ET.ElementTree(root).write(destination, encoding='utf-8', xml_declaration=True)


def check_trips(path, scheduled):
    result = dict(scheduled=scheduled, departed=0, completed=0, delay_s=0., travel_s=0., co2_kg=0.)
    completed = {}
    teleported = set()
    for _, trip in ET.iterparse(path, events=('end',)):
        if trip.tag != 'tripinfo' or not trip.get('id', '').startswith(('car-', 'bus-')):
            continue
        actor = trip.get('id')
        result['departed'] += 1
        emissions = trip.find('emissions')
        if emissions is not None:
            result['co2_kg'] += float(emissions.get('CO2_abs', 0))/1e6
        if 'teleport' in trip.get('vaporized', '').lower():
            teleported.add(actor)
        if float(trip.get('arrival', -1)) >= 0 and actor not in teleported:
            completed[actor] = [float(trip.get('timeLoss')), float(trip.get('duration'))]
    return result, completed


def simulate(peak, scenario, seed, *, source=None, net_path=None, extra_plan=None, broker=None, duration=None,
             monitor=None, profile='original'):
    started = perf_counter()
    training = scenario in ('treino', 'validacao')
    optimized = scenario in ('otimizado', 'coordenado', 'revisado')
    source = source or source_for(peak)
    net_path = net_path or CACHE/'network/curitiba.net.xml'
    config = read_json(ROOT/'config/curitiba.json')
    meta = read_json(source/'metadata.json')
    begin = datetime.fromisoformat(meta['start']).astimezone(LOCAL)
    start_of_day = begin.hour*3600 + begin.minute*60
    if duration is None:
        duration = int(meta['duration_s'])
    output = PROFILES[profile]
    folder = monitor.folder if monitor else output / peak / str(seed) / scenario
    folder.mkdir(parents=True, exist_ok=True)
    (folder/'summary.json').unlink(missing_ok=True)
    road = Network(net_path, config['bbox'])
    plan = folder/'reference.add.xml'
    phases, origins = road.reference_plan(net_path, peak, plan, extra_plan)
    route_path = folder/'demand.rou.xml'
    demand(source/'demand.rou.xml', route_path, duration, training, seed, profile)
    cfg = setup_sumo(folder, net_path.resolve(), duration, seed, plan)
    caps = {edge: max(1., row['target_speed_kmh'])/3.6
            for edge, row in read_json(source/'traffic-targets.json')['edges'].items()
            if row['source'] == 'stats_monthly_median'}
    vehicles = {item.get('id'): (0 if item.get('id').startswith('car-') else 1)
                for item in ET.parse(route_path).getroot().findall('vehicle')
                if item.get('id').startswith(('car-', 'bus-')) and float(item.get('depart')) < duration}
    watched = set(road.signals)
    watch_edges = {edge for signal in watched for edge in road.signals[signal][0]}
    tracked_edges = defaultdict(list)
    for key, edges in road.corridor_edges.items():
        for edge in edges:
            tracked_edges[edge].append(key)
    corridor_mask = {eid: sum(1 << list(road.corridor_edges).index(key) for key in keys)
                     for eid, keys in tracked_edges.items()}
    counts = defaultdict(Counter)
    _, traci = sumo_modules()
    backend = 'TraCI'
    try:
        import libsumo
    except ImportError:
        pass
    else:
        backend = 'libsumo'
    tc = traci.constants
    command = [sumo_binary('sumo'), '-c', str(cfg), '--no-step-log', 'true', '--duration-log.disable', 'true',
               '--error-log', str(folder/'sumo-errors.log'), '--no-warnings', 'true',
               '--tripinfo-output.write-unfinished', 'true', '--device.emissions.probability', '1']
    if backend == 'libsumo':
        libsumo.start(command)
        conn = libsumo
    else:
        traci.start(command, label='quadrilatero', numRetries=8)
        conn = traci.getConnection('quadrilatero')
    controller = None
    recorder = monitor if optimized else None
    try:
        if optimized:
            from .control import Controller
            from .live import ForecastRecorder

            if recorder is None:
                recorder = ForecastRecorder(peak, seed, folder)
            controller = Controller(conn, road, phases, watched, start_of_day, output/'fourier.json', broker,
                                    coordinated=scenario != 'otimizado', monitor=True,
                                    review=scenario == 'revisado')
        summary = collect(conn, tc, road, watched, watch_edges, tracked_edges, vehicles, caps, counts, folder,
                          training, controller, duration, start_of_day, corridor_mask, recorder,
                          record_replay=not training and monitor is None)
        if controller:
            summary['control'] = controller.summary()
    finally:
        if controller:
            controller.close()
        conn.close()
    if training:
        summary = {'bins': {str(key): dict(value) for key, value in sorted(counts.items())}}
    else:
        net_metrics, trips = check_trips(folder/'trips.xml', len(vehicles))
        for actor in summary.pop('teleport_ids'):
            trips.pop(actor, None)
        net_metrics.update(completed=len(trips), delay_s=sum(row[0] for row in trips.values()),
                           travel_s=sum(row[1] for row in trips.values()))
        summary['network'].update(net_metrics)
        write_json(folder/'completed.json', trips)
        map_file = output/'map.json'
        if monitor is None and not map_file.exists():
            write_json(map_file, road.map_data())
    if profile == 'escalonado' and not training and not optimized:
        summary['bins'] = {str(key): dict(value) for key, value in sorted(counts.items())}
    summary.update(peak=peak, scenario=scenario, seed=seed, source=source.name, start=begin.isoformat(), profile=profile,
                   duration=duration, programs=origins, backend=backend, run_time_s=round(perf_counter()-started, 1),
                   inputs=dict(net=digest(net_path), routes=digest(route_path), reference=digest(plan),
                               targets=digest(source/'traffic-targets.json')),
                   supply=dict(carros=sum(value == 0 for value in vehicles.values()),
                               onibus=sum(value == 1 for value in vehicles.values())))
    if recorder:
        recorder.write(folder)
    write_json(folder/'summary.json', summary)
    print(f'{peak}/{seed}/{scenario}: {summary["run_time_s"]} s de processamento', flush=True)


def collect(conn, tc, road, watched, watch_edges, tracked_edges, vehicles, caps, counts, folder,
            training, controller, duration, start_of_day, corridor_mask, recorder, *, record_replay):
    tls = conn.trafficlight
    vehicle = conn.vehicle
    simulation = conn.simulation
    signal_domains = set(road.signals) if not training else set()
    if controller:
        signal_domains.update(controller.active)
    light_var = tc.TL_RED_YELLOW_GREEN_STATE
    phase_var = tc.TL_CURRENT_PHASE
    for signal in sorted(signal_domains):
        tls.subscribe(signal, (light_var, phase_var, tc.TL_NEXT_SWITCH) if controller and signal in controller.active else (light_var,))
    variables = (tc.VAR_ROAD_ID, tc.VAR_SPEED)
    if record_replay:
        variables += (tc.VAR_POSITION, tc.VAR_ANGLE)
    if controller:
        variables += (tc.VAR_LANEPOSITION, tc.VAR_STOPSTATE)
    queue_peaks = {'rede': 0., **dict.fromkeys(road.corridor_edges, 0.)}
    if not training:
        variables = tuple(dict.fromkeys((*variables, tc.VAR_LANE_ID, tc.VAR_LANEPOSITION, tc.VAR_STOPSTATE, tc.VAR_LENGTH)))
        approach_edges = {lane: edge for signal in watched for lane, (edge, _, _) in road.signals[signal][1].items()}
        queue_monitor = QueueMonitor(road.net, {lane: (lane, 0) for lane in approach_edges})
    speed_command, prior_road, speed_before, ids = {}, {}, {}, {}
    stock_speed = {}
    metrics = {key: [Counter(), Counter()] for key in road.corridor_edges}
    teleports = set()
    frames = []
    last_lights = {}
    elapsed = 0
    arrivals, departures, mqtt_events = Counter(), Counter(), []
    arrivals_by_mode = (Counter(), Counter())
    for now in range(1, duration+1):
        conn.simulationStep()
        for actor in simulation.getDepartedIDList():
            if actor in vehicles:
                vehicle.subscribe(actor, variables)
                if vehicles[actor] == 0:
                    stock_speed[actor] = vehicle.getMaxSpeed(actor)
        teleports.update(actor for actor in simulation.getStartingTeleportIDList() if actor in vehicles)
        for actor in simulation.getArrivedIDList():
            stock_speed.pop(actor, None)
            speed_command.pop(actor, None)
            prior_road.pop(actor, None)
            speed_before.pop(actor, None)
        approaches = defaultdict(list)
        stopped_stock = Counter()
        playback = record_replay and now % FRAME == 0
        positions = []
        stopped = defaultdict(list)
        gauged = now > WARMUP
        for actor, values in (vehicle.getAllSubscriptionResults() or {}).items():
            if tc.VAR_ROAD_ID not in values:
                continue
            eid, speed = values[tc.VAR_ROAD_ID], values[tc.VAR_SPEED]
            if not eid:
                continue
            kind = vehicles[actor]
            if not training and speed < QUEUE_STOP_SPEED_MPS and not values[tc.VAR_STOPSTATE] & 1:
                lane = values[tc.VAR_LANE_ID]
                if lane in queue_monitor.lengths:
                    front = max(0., queue_monitor.lengths[lane]-values[tc.VAR_LANEPOSITION])
                    stopped[lane].append((front, front+values[tc.VAR_LENGTH]))
            old = prior_road.get(actor)
            if not eid.startswith(':'):
                if eid != old:
                    if eid in watch_edges and actor not in teleports:
                        arrivals[eid] += 1
                        if controller:
                            arrivals_by_mode[kind][eid] += 1
                        if gauged:
                            counts[(start_of_day+now-1)//BIN*BIN][eid] += 1
                    if controller and eid in controller.routes and old is not None and actor not in teleports:
                        departures[old, eid] += 1
                    prior_road[actor] = eid
                if kind == 0 and eid in road.edges:
                    cap = caps.get(eid)
                    original = stock_speed[actor]
                    command = min(original, max(cap, speed-2.5)) if cap is not None else original
                    if abs(command - speed_command.get(actor, original)) > .02:
                        vehicle.setMaxSpeed(actor, command)
                        speed_command[actor] = command
                scheduled_stop = controller and kind == 1 and values[tc.VAR_STOPSTATE] & 1
                if controller and controller.coordinated and speed < 1. and now % 5 == 0:
                    stopped_stock[eid] += 1
                if controller and eid in watch_edges and not scheduled_stop:
                    distance = road.edges[eid].getLength() - values[tc.VAR_LANEPOSITION]
                    if distance <= 160:
                        eta = 0 if speed < 1. else min(45, round(max(0., distance)/max(speed, 2.)))
                        approaches[eid].append(eta)
                if gauged and eid in tracked_edges:
                    for corridor in tracked_edges[eid]:
                        row = metrics[corridor][kind]
                        row['distance_m'] += speed
                        row['vehicle_s'] += 1
                        row['stopped_s'] += speed < 1.
                        row['stops'] += speed < 1. <= speed_before.get(actor, 0)
                        row['entries'] += eid != old
            speed_before[actor] = speed
            if playback:
                x, y = values[tc.VAR_POSITION]
                if actor not in ids:
                    ids[actor] = len(ids)
                # IDs are unique within each replay, allowing interpolation between samples.
                positions.append([ids[actor], round(x, 1), round(y, 1), round(values[tc.VAR_ANGLE]),
                                  kind, int(speed < 1.), corridor_mask.get(prior_road.get(actor), 0)])
        if controller or playback:
            lights = tls.getAllSubscriptionResults() or {}
        if not training:
            for lane, length in queue_monitor.measure(stopped).items():
                queue_peaks['rede'] = max(queue_peaks['rede'], length)
                for corridor in tracked_edges[approach_edges[lane]]:
                    queue_peaks[corridor] = max(queue_peaks[corridor], length)
        if controller:
            events = controller.step(now, lights, phase_var, approaches, arrivals, departures, stopped_stock,
                                     arrivals_by_mode)
            if record_replay:
                mqtt_events.extend(events)
            if recorder:
                recorder.sample(now, controller)
        if playback:
            states = {key: value[light_var] for key, value in lights.items() if light_var in value}
            delta = states if not frames else {key: state for key, state in states.items()
                                                if last_lights.get(key) != state}
            frames.append([now, positions, delta, mqtt_events])
            last_lights = states
            mqtt_events = []
        if record_replay and (now % CHUNK == 0 or now == duration):
            write_chunk(folder, elapsed, frames)
            frames = []
            elapsed += 1
        if now % 900 == 0:
            print(f'{folder.parent.parent.name}/{folder.parent.name}/{folder.name} {now}/{duration}', flush=True)
    if not training:
        write_json(folder/'queues.json', queue_peaks)
    return dict(corridors={key: {mode: dict(row) for mode, row in zip(MODES, rows)}
                           for key, rows in metrics.items()},
                network={'teleports': len(teleports)}, teleport_ids=sorted(teleports))

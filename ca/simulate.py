import json
from collections import Counter, defaultdict
from datetime import timedelta
from math import ceil, hypot
from xml.etree.ElementTree import Element, ElementTree, SubElement, indent

from .io import envelope, sumo_binary, sumo_modules, utc, write_json
from .metrics import MODES, POLLUTANTS, Receivers, mode
from .queues import QUEUE_STOP_SPEED_MPS, QueueMonitor
from .signal_control import CYCLE_STRATEGIES, FEEDBACK_STRATEGIES, AdaptiveSignals
from .signals import FixedProgram, apply_extensions

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


def monitored(network, bbox):
    from .sources import contains

    nodes = {key: node for key, node in network.signal_junctions().items() if contains(bbox, network.lonlat(node.getCoord()))}
    lanes = {}
    approaches = {}
    for node_id, node in nodes.items():
        for edge in node.getIncoming():
            if edge.isSpecial():
                continue
            approaches[edge.getID()] = node_id
            for lane in edge.getLanes():
                if lane.allows('passenger') or lane.allows('bus'):
                    lanes[lane.getID()] = node_id, lane.getLength()
    indexed = defaultdict(set)
    for tls in network.net.getTrafficLights():
        for src, _, _ in tls.getConnections():
            node_id = src.getEdge().getToNode().getID()
            if node_id in nodes:
                indexed[node_id].add(tls.getID())
    return nodes, lanes, approaches, indexed


def signal_approaches(network, monitored_lanes, tls, signals):
    approaches = []
    for signal in sorted(signals):
        movements = defaultdict(list)
        for index, links in enumerate(tls.getControlledLinks(signal)):
            for lane, _, _ in links:
                if lane in monitored_lanes:
                    movements[lane].append(index)
        for lane, indexes in movements.items():
            road = network.net.getLane(lane)
            approaches.append({'signal': signal, 'links': sorted(set(indexes)),
                               'point': network.lonlat(road.getShape()[-1]),
                               'street': road.getEdge().getName() or lane})
    return approaches


def write_signal_frame(stream, subscriptions, variable, previous, now, full, mqtt=None):
    states = {key: values[variable] for key, values in subscriptions.items() if variable in values}
    lights = states if full else {key: state for key, state in states.items() if previous.get(key) != state}
    payload = {'time_s': now, 'full': full, 'lights': lights}
    if mqtt:
        payload['mqtt'] = mqtt
    stream.write(json.dumps(payload, separators=(',', ':'), allow_nan=False) + '\n')
    return states


def intersects_bounds(network, bbox):
    west, south, east, north = bbox
    ring = [network.xy(p) for p in ((west, south), (east, south), (east, north), (west, north))]
    segments = list(zip(ring, ring[1:]+ring[:1]))

    def inside(position):
        x, y = position
        return all((b[0]-a[0])*(y-a[1]) - (b[1]-a[1])*(x-a[0]) >= 0 for a, b in segments)

    return inside


class TrafficGrid:
    def __init__(self, network, bbox):
        west, south, east, north = bbox
        self.origin = network.xy((west, south))
        x0, y0 = self.origin
        x1, y1 = network.xy((east, south))
        x2, y2 = network.xy((west, north))
        self.east = x1-x0, y1-y0
        self.north = x2-x0, y2-y0
        self.det = self.east[0]*self.north[1] - self.east[1]*self.north[0]
        self.columns = max(1, ceil(hypot(*self.east)/100))
        self.rows = max(1, ceil(hypot(*self.north)/100))

    def cell(self, position):
        dx, dy = position[0]-self.origin[0], position[1]-self.origin[1]
        col = int(self.columns * (dx*self.north[1] - dy*self.north[0]) / self.det)
        row = int(self.rows * (self.east[0]*dy - self.east[1]*dx) / self.det)
        return min(self.rows-1, max(0, row))*self.columns + min(self.columns-1, max(0, col))


def empty_junction():
    return {'passages': 0, 'peak_queue_m': 0., 'energy_seconds': 0., 'peak_energy': 0.,
            'queue_now_m': 0., 'co2_now_g_s': 0., 'sensors': []}


def empty_frame(start, end, begin):
    return envelope('simulation.frame',
                    timestamp=utc(begin + timedelta(seconds=end)), start_s=start, end_s=end,
                    trips={name: {'completed': 0, 'travel_s': 0., 'delay_s': 0.} for name in MODES},
                    mass_kg={name: dict.fromkeys(POLLUTANTS, 0.) for name in ('cars', 'buses')},
                    intersections=defaultdict(empty_junction), pedestrian_passages=Counter(),
                    active=dict.fromkeys((*MODES, 'pedestrians'), 0), cars=[], buses=[], teleports=0,
                    traffic_cells=Counter())


def run_sumo(folder, cfg_path, network, config, begin, duration, validation, sites, publisher=None,
             controller=None, extension_budget=None, bus_lines=None, targets=None, *, strategy='fixed',
             record_positions=True, model=None, train=False):
    if controller is not None and strategy != 'fixed':
        raise ValueError('Selecione uma estratégia integrada ou um controlador personalizado.')
    publish_frames = publisher is not None and strategy != 'mqtt-adaptive'
    with_signals = controller is not None or publish_frames
    custom = controller or FixedProgram()
    bus_lines = bus_lines or {}
    brt_lines = frozenset(config.get('brt_lines', ()))
    feedback = strategy in FEEDBACK_STRATEGIES
    if strategy == 'mqtt-adaptive':
        from .mqtt_feedback import MqttAdaptiveSignals
        if publisher is None:
            raise ValueError('O controle mqtt-adaptive requer um broker.')
        adaptive = MqttAdaptiveSignals(strategy, brt_lines, publisher)
    elif feedback:
        from .feedback import FeedbackSignals
        adaptive = FeedbackSignals(strategy, brt_lines)
    elif strategy in CYCLE_STRATEGIES:
        from .learning import CycleSignals
        adaptive = CycleSignals(strategy, brt_lines, config, model, train)
    else:
        adaptive = AdaptiveSignals(strategy, brt_lines) if strategy != 'fixed' else None
    targets = targets or {}
    median_caps = {key: max(1., row['target_speed_kmh'])/3.6 for key, row in targets.items()
                   if row['source'] == 'stats_monthly_median'}
    original_max = {}
    applied_caps = {}
    grid = TrafficGrid(network, config['bbox'])
    nodes, lanes, approaches, signal_ids = monitored(network, config['bbox'])
    queue_monitor = QueueMonitor(network.net, lanes)
    receptors = Receivers(network, nodes, config['acoustics'])
    lane_ids = defaultdict(list)
    for lane, (node_id, _) in lanes.items():
        lane_ids[node_id].append(lane)
    info = {node_id: {'name': network.intersection_name(node), 'coordinates': network.lonlat(node.getCoord()),
                      'receiver_coordinates': receptors.coordinates[node_id], 'signal_ids': sorted(signal_ids[node_id]),
                      'sensors': [f'approach_{lane}' for lane in sorted(lane_ids[node_id])]}
            for node_id, node in nodes.items()}
    position_interval = config.get('position_interval_seconds', 2)
    if type(position_interval) is not int or position_interval < 1:
        raise ValueError('position_interval_seconds deve ser um número inteiro positivo.')
    map_data = envelope('scenario.map', roads=network.map_data(), intersections=info,
                                            crossings=sites, bbox=config['bbox'], car_positions=True,
                                            position_interval_s=position_interval if record_positions else None, bus_lines=bus_lines,
                                            traffic_grid={'columns': grid.columns, 'rows': grid.rows})
    crossing_site = {crossing: site['junction_id'] for site in sites for crossing in site['crossings']}
    completed, departed, starts, last_delay, last_road, last_crossing = Counter(), Counter(), {}, {}, {}, {}
    speeds = defaultdict(lambda: [0., 0])
    teleports = set()
    motor_speed_sum = 0.
    motor_seconds = 0
    queue_sum = 0.
    brt_trips = Counter()
    inside = intersects_bounds(network, config['bbox'])
    _, traci = sumo_modules()
    tc = traci.constants
    emissions = (tc.VAR_CO2EMISSION, tc.VAR_COEMISSION, tc.VAR_NOXEMISSION, tc.VAR_HCEMISSION, tc.VAR_PMXEMISSION)
    vehicle_vars = (tc.VAR_POSITION, tc.VAR_SPEED, tc.VAR_ROAD_ID, tc.VAR_LANE_ID, tc.VAR_LANEPOSITION, tc.VAR_LENGTH,
                    tc.VAR_TIMELOSS, tc.VAR_STOPSTATE, tc.VAR_NOISEEMISSION, *emissions)
    interval = config['aggregation_seconds']
    slice_end = min(interval, duration)
    frame = empty_frame(0, slice_end, begin)
    positions = []
    command = [sumo_binary('sumo'), '-c', str(cfg_path), '--no-step-log', 'true', '--log', str(folder/'sumo.log'),
               '--error-log', str(folder/'sumo-errors.log')]
    try:
        traci.start(command, label=folder.name, numRetries=10)
    except traci.exceptions.FatalTraCIError as exc:
        raise ValueError(f'Falha ao iniciar o SUMO via TraCI. Consulte {folder / "sumo-errors.log"}. ({exc})') from None
    conn = traci.getConnection(folder.name)
    try:
        observed_signals = set().union(*signal_ids.values())
        tls = conn.trafficlight
        lamp_variable = tc.TL_RED_YELLOW_GREEN_STATE
        map_data['signal_approaches'] = signal_approaches(network, lanes, tls, observed_signals)
        write_json(folder / 'map.json', map_data)
        for signal in sorted(observed_signals):
            tls.subscribe(signal, (lamp_variable,))
        if adaptive is not None:
            adaptive.start(conn, network, observed_signals)
        with ((folder / 'frames.jsonl').open('w', encoding='utf-8') as output,
              (folder / 'signal-events.jsonl').open('w', encoding='utf-8', buffering=1) as signal_output):
            lights = write_signal_frame(signal_output, tls.getAllSubscriptionResults(), lamp_variable, {}, 0, True)
            for second in range(duration):
                conn.simulationStep()
                for actor in conn.simulation.getDepartedIDList():
                    actor_mode = mode(actor)
                    if actor_mode:
                        departed[actor_mode] += 1
                        starts[actor] = second
                        conn.vehicle.subscribe(actor, vehicle_vars)
                for actor in conn.simulation.getStartingTeleportIDList():
                    teleports.add(actor)
                    last_road.pop(actor, None)
                    frame['teleports'] += 1
                for actor in conn.simulation.getArrivedIDList():
                    if actor in starts and actor not in teleports:
                        actor_mode = mode(actor)
                        trip = frame['trips'][actor_mode]
                        trip['completed'] += 1
                        trip['travel_s'] += second - starts[actor]
                        trip['delay_s'] += last_delay.get(actor, 0.)
                        completed[actor_mode] += 1
                        if bus_lines.get(actor) in brt_lines:
                            brt_trips.update(completed=1, travel_s=second-starts[actor],
                                             delay_s=last_delay.get(actor, 0.))
                    starts.pop(actor, None)
                    original_max.pop(actor, None)
                    applied_caps.pop(actor, None)
                    last_road.pop(actor, None)
                    last_delay.pop(actor, None)
                    if adaptive is not None:
                        adaptive.bus_approaches.pop(actor, None)
                snapshot = second + 1 == slice_end
                position_sample = ({'time_s': second + 1, 'cars': {}, 'buses': {}}
                                   if snapshot or record_positions and (second + 1) % position_interval == 0 else None)
                energy, node_co2 = defaultdict(float), defaultdict(float)
                stopped = defaultdict(list)
                sensors = defaultdict(dict)
                active = Counter()
                approaching, queued, downstream, platoons = Counter(), Counter(), Counter(), Counter()
                filled = Counter() if feedback else None
                brt_approaches = defaultdict(set)
                for actor, values in conn.vehicle.getAllSubscriptionResults().items():
                    if not values or actor not in starts:
                        continue
                    actor_mode = mode(actor)
                    road, lane, speed = values[tc.VAR_ROAD_ID], values[tc.VAR_LANE_ID], values[tc.VAR_SPEED]
                    position = values[tc.VAR_POSITION]
                    last_delay[actor] = values[tc.VAR_TIMELOSS]
                    previous = last_road.get(actor)
                    if median_caps and actor_mode == 'cars' and road in network.edges:
                        cap = median_caps.get(road)
                        if cap is not None:
                            if actor not in original_max:
                                original_max[actor] = conn.vehicle.getMaxSpeed(actor)
                            # Limit the deceleration imposed by a speed cap at a segment transition.
                            gradual_cap = min(original_max[actor], max(cap, speed-2.5))
                            if gradual_cap != applied_caps.get(actor):
                                conn.vehicle.setMaxSpeed(actor, gradual_cap)
                                applied_caps[actor] = gradual_cap
                        elif actor in original_max:
                            conn.vehicle.setMaxSpeed(actor, original_max.pop(actor))
                            applied_caps.pop(actor)
                    if previous and previous in network.edges and previous != road and road:
                        validation.passage(previous, actor_mode, second)
                        if previous in approaches and actor_mode != 'bicycles':
                            frame['intersections'][approaches[previous]]['passages'] += 1
                    last_road[actor] = road
                    if not inside(position):
                        continue
                    if road in targets and (actor_mode == 'cars' or (actor_mode == 'buses' and not median_caps)):
                        speeds[road][0] += speed*3.6
                        speeds[road][1] += 1
                    active[actor_mode] += 1
                    if position_sample is not None and actor_mode != 'bicycles':
                        position_sample[actor_mode][actor] = network.lonlat(position)
                    if actor_mode == 'bicycles':
                        continue
                    motor_speed_sum += speed
                    motor_seconds += 1
                    if filled is not None and lane in adaptive.storage:
                        filled[lane] += values[tc.VAR_LENGTH] + 2.5
                    if adaptive is not None and not (values[tc.VAR_STOPSTATE] & 1):
                        lane_length = adaptive.incoming.get(lane)
                        if lane_length is not None:
                            distance = lane_length - values[tc.VAR_LANEPOSITION]
                            if distance <= 70:
                                approaching[lane] += 1
                                if speed < 2:
                                    queued[lane] += 1
                                if bus_lines.get(actor) in brt_lines and distance <= 50:
                                    next_tls = adaptive.observe_bus(conn, actor, lane)
                                    if next_tls is not None:
                                        signal, link = next_tls
                                        brt_approaches[signal].add(link)
                            elif strategy == 'pressure-coordinated' and speed >= 4 and distance <= min(160, speed * 15):
                                platoons[lane] += 1
                        if lane in adaptive.downstream and (speed < 2 or values[tc.VAR_LANEPOSITION] < 18):
                            downstream[lane] += 1
                    frame['traffic_cells'][grid.cell(position)] += 1
                    for p, variable in zip(POLLUTANTS, emissions):
                        frame['mass_kg'][actor_mode][p] += max(0, values[variable]) / 1_000_000
                    receptors.radiate(energy, position, values[tc.VAR_NOISEEMISSION])
                    if speed < QUEUE_STOP_SPEED_MPS and not (values[tc.VAR_STOPSTATE] & 1) and lane in queue_monitor.lengths:
                        front = max(0, queue_monitor.lengths[lane] - values[tc.VAR_LANEPOSITION])
                        stopped[lane].append((front, front + values[tc.VAR_LENGTH]))
                    if snapshot and lane in lanes:
                        node_id, length = lanes[lane]
                        to_line = max(0, length - values[tc.VAR_LANEPOSITION])
                        if to_line <= 100:
                            node_co2[node_id] += max(0, values[tc.VAR_CO2EMISSION])/1000
                            if to_line <= 15 and (lane not in sensors[node_id] or sensors[node_id][lane][0] > to_line):
                                sensors[node_id][lane] = to_line, speed*3.6, actor_mode
                queue = queue_monitor.measure(stopped)
                queue_sum += sum(queue.values())
                applied = None
                if adaptive is not None:
                    observations = {'filled': filled} if feedback else {}
                    applied = adaptive.update(conn, second+1, approaching, queued, downstream, brt_approaches, platoons, **observations)
                    if getattr(publisher, 'accept_commands', False):
                        for request in publisher.drain():
                            if (0 <= second+1-request['observed_s'] <= interval
                                    and request.get('timestamp') == utc(begin + timedelta(seconds=request['observed_s']))):
                                adaptive.extend(conn, second+1, request)
                exchange = getattr(publisher, 'last_exchange', None)
                mqtt_event = ({**exchange, 'applied': applied or {}}
                              if exchange and exchange['time_s'] == second+1 else None)
                lights = write_signal_frame(signal_output, tls.getAllSubscriptionResults(), lamp_variable, lights,
                                            second+1, (second+1) % interval == 0, mqtt_event)
                for node_id in energy.keys() | queue.keys():
                    item = frame['intersections'][node_id]
                    item['peak_queue_m'] = max(item['peak_queue_m'], queue[node_id])
                    item['energy_seconds'] += energy[node_id]
                    item['peak_energy'] = max(item['peak_energy'], energy[node_id])
                for person in conn.simulation.getDepartedPersonIDList():
                    conn.person.subscribe(person, (tc.VAR_ROAD_ID,))
                for person in conn.simulation.getArrivedPersonIDList():
                    last_crossing.pop(person, None)
                walking = conn.person.getAllSubscriptionResults()
                for person, values in walking.items():
                    if not values:
                        continue
                    edge = values[tc.VAR_ROAD_ID]
                    if edge in crossing_site and edge != last_crossing.get(person):
                        frame['pedestrian_passages'][crossing_site[edge]] += 1
                    last_crossing[person] = edge
                if record_positions and position_sample is not None:
                    positions.append(position_sample)
                if not snapshot:
                    continue
                frame['cars'] = [{'id': actor, 'coordinates': point} for actor, point in position_sample['cars'].items()]
                frame['buses'] = [{'id': actor, 'line_id': bus_lines.get(actor), 'coordinates': point}
                                  for actor, point in position_sample['buses'].items()]
                if record_positions:
                    write_json(folder / 'positions' / f'{slice_end}.json', positions)
                positions.clear()
                for node_id in frame['intersections'].keys() | sensors.keys() | node_co2.keys():
                    item = frame['intersections'][node_id]
                    item['queue_now_m'] = round(queue[node_id], 2)
                    item['co2_now_g_s'] = round(node_co2[node_id], 4)
                    item['sensors'] = [{'sensor_id': f'approach_{lane_id}', 'state': 'occupied',
                                        'vehicle_speed_kmh': round(speed, 2), 'mode': actor_mode}
                                       for lane_id, (_, speed, actor_mode) in sensors[node_id].items()]
                frame['active'].update(active, pedestrians=len(walking))
                if strategy == 'ml-online':
                    frame['online_control'] = adaptive.online_status()
                if with_signals:
                    frame['signals'] = {key: {'phase_index': conn.trafficlight.getPhase(key),
                                             'lamp_state': conn.trafficlight.getRedYellowGreenState(key),
                                             'next_switch_s': conn.trafficlight.getNextSwitch(key)}
                                        for key in observed_signals}
                output.write(json.dumps(frame, ensure_ascii=False, allow_nan=False) + '\n')
                output.flush()
                if publish_frames:
                    publisher.publish(frame, folder.name, info)
                commands = custom.decide(frame)
                if commands:
                    apply_extensions(conn, commands, extension_budget if extension_budget is not None else {})
                slice_end = min(duration, second+1+interval)
                frame = empty_frame(second+1, slice_end, begin)
    finally:
        conn.close()
    comparison = [{'edge_id': key, **targets[key], 'simulated_speed_kmh': round(total/n, 2), 'vehicle_seconds': n}
                  for key, (total, n) in speeds.items() if n >= 30]
    brt_completed = brt_trips['completed']
    if train:
        adaptive.save(folder / 'signal-model.json')
    if strategy == 'ml-online':
        adaptive.save_online(folder / 'signal-online-evidence.json', duration)
    return {'completed': dict(completed), 'departed': dict(departed), 'teleported_vehicles': len(teleports),
            'teleported_ids': sorted(teleports),
            'teleported_by_mode': dict(Counter(mode(actor) or 'other' for actor in teleports)), 'active_unfinished': len(starts),
            'speed_comparison': comparison, 'geh': validation.result(),
            'signal_control': adaptive.result() if adaptive else {'strategy': 'fixed'},
            'network_speed_kmh': 3.6*motor_speed_sum/motor_seconds if motor_seconds else None,
            'mean_queue_m': queue_sum/(duration*len(nodes)) if nodes else None,
            'brt': {'completed': brt_completed,
                    'mean_travel_s': brt_trips['travel_s']/brt_completed if brt_completed else None,
                    'mean_delay_s': brt_trips['delay_s']/brt_completed if brt_completed else None}}

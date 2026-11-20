from collections import defaultdict
from datetime import datetime
from math import log10, sqrt
from xml.etree.ElementTree import iterparse

from .io import read_json

MODES = ('cars', 'buses', 'bicycles')
POLLUTANTS = ('co2', 'co', 'nox', 'hc', 'pmx')


def mode(vehicle):
    prefix = vehicle.split('-', 1)[0]
    return {'car': 'cars', 'bus': 'buses', 'bike': 'bicycles'}.get(prefix)


def db(energy):
    return 10*log10(energy) if energy > 0 else None


def geh(simulated, observed):
    return sqrt(2*(simulated-observed)**2/(simulated+observed)) if simulated+observed else 0.0


def timed_rows(path, key, begin, end):
    rows = []
    if path is None:
        return rows
    for row in read_json(path)[key]:
        start, finish = (datetime.fromisoformat(row[k]) for k in ('start', 'end'))
        if start.utcoffset() is None or finish.utcoffset() is None or finish <= start:
            raise ValueError(f'Intervalo inválido em {path.name}. Use ISO 8601 com fuso e duração positiva.')
        if begin <= start and finish <= end:
            rows.append({**row, 'start_s': round((start-begin).total_seconds()),
                         'end_s': round((finish-begin).total_seconds())})
    return rows


class CountValidation:
    def __init__(self, rows, edges):
        self.rows = rows
        self.counts = [0] * len(rows)
        self.index = defaultdict(list)
        seen = set()
        for i, row in enumerate(rows):
            key = row['edge_id'], row['mode'], row['start_s'], row['end_s']
            if (row['edge_id'] not in edges or row['mode'] not in ('motor', *MODES)
                    or type(row['vehicles']) is not int or row['vehicles'] < 0 or not row.get('source') or key in seen):
                raise ValueError(f'Contagem de campo inválida ou duplicada: {key}.')
            self.index[row['edge_id']].append(i)
            seen.add(key)

    def passage(self, edge, vehicle_mode, t):
        for i in self.index.get(edge, ()):
            row = self.rows[i]
            when = row['start_s'] <= t < row['end_s']
            if when and (row['mode'] == vehicle_mode or row['mode'] == 'motor' and vehicle_mode != 'bicycles'):
                self.counts[i] += 1

    def result(self):
        rows = []
        for row, simulated in zip(self.rows, self.counts):
            factor = 3600/(row['end_s']-row['start_s'])
            rows.append({**row, 'simulated': simulated, 'geh': geh(simulated*factor, row['vehicles']*factor)})
        score = sum(r['geh'] < 5 for r in rows)/len(rows) if rows else None
        return {'status': 'sem_contagens' if score is None else 'aprovado' if score >= .85 else 'reprovado',
                'share_under_5': score, 'threshold': .85, 'rows': rows}


class Receivers:
    def __init__(self, network, nodes, config):
        self.network = network
        self.grid = defaultdict(list)
        self.coordinates = {}
        self.radius = config['radius_m']
        self.height2 = (config['receiver_height_m'] - config['source_height_m'])**2
        self.reference_distance2 = config['source_reference_distance_m']**2
        for node_id, node in nodes.items():
            x, y = node.getCoord()
            y += config['receiver_offset_m']
            self.coordinates[node_id] = network.lonlat((x, y))
            for cell in network.cells(x-self.radius, y-self.radius, x+self.radius, y+self.radius):
                self.grid[cell].append((node_id, x, y))

    def radiate(self, receivers, position, source_db):
        if source_db <= 0:
            return
        x, y = position
        reference_energy = 10**(source_db/10) * self.reference_distance2
        for receiver_id, rx, ry in self.grid.get(next(self.network.cells(x, y, x, y)), ()):
            distance_squared = (x-rx)**2+(y-ry)**2
            if distance_squared <= self.radius**2:
                receivers[receiver_id] += reference_energy / max(1.0, distance_squared+self.height2)


def window_summary(frames):
    trips = {name: dict(completed=0, travel_s=0., delay_s=0.) for name in MODES}
    pollutants = {name: dict.fromkeys(POLLUTANTS, 0.) for name in ('cars', 'buses')}
    junctions = defaultdict(lambda: {'passages': 0, 'peak_queue_m': 0., 'energy_seconds': 0., 'peak_energy': 0.})
    active = defaultdict(int)
    duration = 0
    for frame in frames:
        duration += frame['end_s'] - frame['start_s']
        for name, values in frame['trips'].items():
            for key, value in values.items():
                trips[name][key] += value
        for name, values in frame['mass_kg'].items():
            for key, value in values.items():
                pollutants[name][key] += value
        for key, value in frame['pedestrian_passages'].items():
            active[key] += value
        for key, state in frame['intersections'].items():
            total = junctions[key]
            total['passages'] += state['passages']
            total['peak_queue_m'] = max(total['peak_queue_m'], state['peak_queue_m'])
            total['energy_seconds'] += state['energy_seconds']
            total['peak_energy'] = max(total['peak_energy'], state['peak_energy'])
    for values in trips.values():
        count = values['completed']
        values['mean_travel_s'] = values['travel_s']/count if count else None
        values['mean_delay_s'] = values['delay_s']/count if count else None
    for state in junctions.values():
        state['laeq_dba'] = db(state['energy_seconds']/duration) if duration else None
        state['lp_peak_dba'] = db(state['peak_energy'])
    totals = {key: sum(p[key] for p in pollutants.values()) for key in POLLUTANTS}
    return {'duration_s': duration, 'trips': trips, 'mass_by_mode_kg': pollutants, 'mass_kg': totals,
            'intersections': dict(junctions), 'pedestrian_passages': dict(active),
            'peak_queue_m': max((j['peak_queue_m'] for j in junctions.values()), default=0.)}


def pedestrian_trip_info(path):
    completed = 0
    waiting = 0.
    for _, entry in iterparse(path):
        if entry.tag == 'personinfo' and entry.get('id', '').startswith('ped-'):
            completed += 1
            waiting += float(entry.get('waitingTime', 0))
        entry.clear()
    return {'completed': completed, 'mean_waiting_s': waiting/completed if completed else None}


def signal_kpis(summary, receivers, pedestrian_trips=None):
    totals = summary['totals']
    trips = totals['trips']
    motor = [trips[name] for name in ('cars', 'buses')]
    completed = sum(item['completed'] for item in motor)
    energy = sum(totals['intersections'].get(node, {}).get('energy_seconds', 0.) for node in receivers)
    brt = summary.get('brt', {})
    pedestrians = summary.get('pedestrians') or pedestrian_trips or {}
    return {
        'delay_s': sum(item['delay_s'] for item in motor)/completed if completed else None,
        'travel_s': sum(item['travel_s'] for item in motor)/completed if completed else None,
        'speed_kmh': summary.get('network_speed_kmh'),
        'mean_queue_m': summary.get('mean_queue_m'),
        'peak_queue_m': totals['peak_queue_m'],
        'completed': completed,
        'bus_delay_s': trips['buses']['mean_delay_s'],
        'brt_delay_s': brt.get('mean_delay_s'),
        'brt_completed': brt.get('completed'),
        'ped_crossings': sum(totals['pedestrian_passages'].values()),
        'ped_completed': pedestrians.get('completed'),
        'ped_wait_s': pedestrians.get('mean_waiting_s'),
        'bike_completed': trips['bicycles']['completed'],
        'teleports': summary['teleported_vehicles'],
        'laeq_dba': db(energy/(len(receivers)*totals['duration_s'])) if receivers and totals['duration_s'] else None,
        **totals['mass_kg'],
    }

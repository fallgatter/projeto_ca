import random
from collections import defaultdict
from datetime import timedelta
from itertools import pairwise
from math import hypot
from statistics import mean
from xml.etree.ElementTree import Element, ElementTree, SubElement, indent, parse

from .network import cycling_lanes, normalized, segment_projection
from .origin_destination import ZONES_PER_SIDE, zone_boxes
from .sources import contains


def equip_eco_approach(path, settings):
    routes = parse(path)
    parameters = {
        'has.glosa.device': 'true',
        'device.glosa.range': str(settings['range_m']),
        'device.glosa.min-speed': str(settings['min_speed_mps']),
        'device.glosa.add-switchtime': str(settings['green_buffer_s']),
        # SUMO only advises speeding up if this exceeds the driver's speed factor.
        'device.glosa.max-speedfactor': '0',
    }
    for vehicle_type in routes.getroot().findall('vType'):
        if vehicle_type.get('vClass') != 'passenger':
            continue
        existing = {param.get('key'): param for param in vehicle_type.findall('param')}
        for key, value in parameters.items():
            if key in existing:
                existing[key].set('value', value)
            else:
                SubElement(vehicle_type, 'param', key=key, value=value)
    indent(routes)
    routes.write(path, encoding='UTF-8', xml_declaration=True)


def boundary_position(network, bbox, edge, entering):
    shape = edge.getShape()
    previous = 0.
    for a, b in pairwise(shape):
        length = hypot(b[0]-a[0], b[1]-a[1])
        if contains(bbox, network.lonlat(a)) != entering and contains(bbox, network.lonlat(b)) == entering:
            low, high = 0., 1.
            for _ in range(16):
                mid = (low+high)/2
                point = network.lonlat((a[0]+mid*(b[0]-a[0]), a[1]+mid*(b[1]-a[1])))
                if contains(bbox, point) == entering:
                    high = mid
                else:
                    low = mid
            fraction = high if entering else low
            point = network.lonlat((a[0]+fraction*(b[0]-a[0]), a[1]+fraction*(b[1]-a[1])))
            total = sum(hypot(y[0]-x[0], y[1]-x[1]) for x, y in pairwise(shape))
            position = (previous+fraction*length) / total * edge.getLength()
            return point, min(round(position, 2), edge.getLength())
        previous += length
    return None


def observed_routes(network, bbox, pairs, rng):
    zones = zone_boxes(bbox)
    inside = defaultdict(list)
    entering = defaultdict(list)
    leaving = defaultdict(list)

    for edge in sorted(network.edges.values(), key=lambda edge: edge.getID()):
        if not edge.allows('passenger'):
            continue
        points = [network.lonlat(node.getCoord()) for node in (edge.getFromNode(), edge.getToNode())]
        start, end = (contains(bbox, point) for point in points)
        if start and end and edge.getLength() > 28:
            point = network.lonlat(edge.getShape()[len(edge.getShape())//2])
            groups, position = inside, -1.
        elif start != end:
            crossing = boundary_position(network, bbox, edge, entering=end)
            if crossing is None:
                continue
            point, position = crossing
            groups = leaving if start else entering
        else:
            continue
        index = next((i for i, zone in enumerate(zones) if contains(zone, point)), None)
        if index is not None:
            groups[index].append((edge, position))

    pool, weights = [], []
    for (origin, dest, external), share in sorted(pairs.items()):
        origins = (entering if external & 1 else inside)[origin]
        destinations = (leaving if external & 2 else inside)[dest]
        if not origins or not destinations:
            continue
        paths = set()
        for _ in range(24):
            a, depart_pos = rng.choice(origins)
            b, arrival_pos = rng.choice(destinations)
            if a == b:
                continue
            path, _ = network.net.getFastestPath(a, b, vClass='passenger', maxCost=800, withInternal=False)
            if path and sum(edge.getLength() for edge in path) >= 150:
                paths.add((' '.join(edge.getID() for edge in path), depart_pos, arrival_pos))
                if len(paths) >= 6:
                    break
        if paths:
            pool.append(sorted(paths))
            weights.append(share)
    if not pool:
        raise ValueError('TomTom O/D: nenhum par da matriz produziu uma rota conectada no SUMO.')
    represented = 100 * sum(weights) / sum(pairs.values())
    return pool, weights, {'zones': ZONES_PER_SIDE**2, 'pairs': len(pairs), 'mapped_pairs': len(pool),
                           'represented_share_pct': round(represented, 2)}


def estimated_routes(network, bbox, targets, count, rng):
    edges = [e for e in network.edges.values() if e.allows('passenger') and e.getLength() > 28
             and contains(bbox, network.lonlat(e.getShape()[len(e.getShape())//2]))]
    origin_weights, destination_weights = [], []
    for edge in edges:
        lanes = sum(lane.allows('passenger') for lane in edge.getLanes())
        target = targets.get(edge.getID(), {})
        congestion = 1 + .8*(1 - target.get('speed_ratio', 1.))
        corridor = 1.55 if network.is_corridor(edge) else 1
        weight = edge.getLength()**.45 * lanes * (edge.getSpeed()/10)**1.5 * congestion * corridor
        origin_weights.append(weight * target.get('departure_weight', 1.))
        destination_weights.append(weight)
    pool = []
    # Reuse a route pool so total demand does not control routing cost.
    pool_size = min(750, max(80, count))
    origins = rng.choices(edges, origin_weights, k=pool_size*4)
    destinations = rng.choices(edges, destination_weights, k=pool_size*4)
    for origin, dest in zip(origins, destinations):
        if hypot(*(a-b for a, b in zip(origin.getFromNode().getCoord(), dest.getToNode().getCoord()))) < 330:
            continue
        path, _ = network.net.getFastestPath(origin, dest, vClass='passenger', maxCost=800, withInternal=False)
        if path:
            pool.append(' '.join(edge.getID() for edge in path))
        if len(pool) == pool_size:
            break
    if not pool:
        raise ValueError('Nenhuma rota de automóvel conectada no recorte.')
    return pool


def generate_cars(network, config, targets, profile, begin, duration, preset, rng, scale, od):
    count = round(config['car_departures_per_hour'][preset] * scale * duration/3600)
    if count == 0:
        return [], None
    stats = None
    if od:
        pool, weights, stats = observed_routes(network, config['bbox'], od['pairs'], rng)
        stats['analysis_id'] = od['analysis_id']
        print(f'TomTom O/D: {stats["mapped_pairs"]}/{stats["pairs"]} pares com rota · '
              f'{stats["represented_share_pct"]:.1f}% do peso da matriz', flush=True)
        choices = [rng.choice(paths) for paths in rng.choices(pool, weights, k=count)]
    else:
        pool = estimated_routes(network, config['bbox'], targets, count, rng)
    fleet = config['fleet']
    trips = []
    hours = [profile.get((begin + timedelta(seconds=sec)).hour, 1) for sec in range(duration)]
    for i, sec in enumerate(sorted(rng.choices(range(duration), weights=hours, k=count))):
        car_type = rng.choices(fleet, [entry['weight'] for entry in fleet])[0]['id']
        car = Element('vehicle', id=f'car-{i}', type=car_type, depart=str(sec), departLane='best')
        if od:
            route, depart_pos, arrival_pos = choices[i]
            if depart_pos >= 0:
                car.set('departPos', str(depart_pos))
            if arrival_pos >= 0:
                car.set('arrivalPos', str(arrival_pos))
        else:
            route = rng.choice(pool)
        SubElement(car, 'route', edges=route)
        trips.append((sec, car))
    return trips, stats


def generate_active(network, config, begin, duration, rng):
    nodes = defaultdict(set)
    for edge in network.edges.values():
        if 'xv de novembro' in normalized(edge.getName()) and edge.allows('pedestrian'):
            nodes[edge.getFromNode()].add(edge)
            nodes[edge.getToNode()].add(edge)
    crossings = defaultdict(list)
    for edge in network.net.getEdges(withInternal=True):
        if edge.getFunction() == 'crossing':
            crossings[edge.getID().rsplit('_', 1)[0][1:]].append(edge.getID())
    active, sites = [], []
    reference = config['pedestrian_demand']
    day = 'weekend' if begin.weekday() >= 5 else 'weekday'
    hourly = {kind: mean(reference[f'{day}_{kind}'])*60/reference['sample_minutes']*reference['crossing_fraction']
              for kind in ('commercial', 'closed')}
    weights = [hourly['commercial' if 9 <= (begin+timedelta(seconds=sec)).hour < 19 else 'closed']
               for sec in range(duration)]
    pedestrian_count = round(sum(weights)/3600)
    for node, sidewalks in nodes.items():
        nearby = crossings[node.getID()]
        if not nearby or len(sidewalks) < 2:
            continue
        paths = sorted(sidewalks, key=lambda edge: edge.getID())[:2]
        sites.append({'junction_id': node.getID(), 'name': network.intersection_name(node),
                      'coordinates': network.lonlat(node.getCoord()), 'crossings': nearby})
        seconds = rng.choices(range(duration), weights=weights, k=pedestrian_count)
        for i, second in enumerate(sorted(seconds)):
            origin, target = paths if i % 2 == 0 else paths[::-1]
            departure = min(origin.getLength()*.8, origin.getLength()-1) if origin.getToNode() == node else min(12, origin.getLength()/2)
            arrival = max(1, target.getLength()-12) if target.getToNode() == node else min(12, target.getLength()/2)
            person = Element('person', id=f'ped-{node.getID()}-{i}', type='pedestre', depart=str(second),
                             departPos=f'{max(.1, departure):.2f}')
            SubElement(person, 'walk', edges=f'{origin.getID()} {target.getID()}', arrivalPos=f'{arrival:.2f}')
            active.append((second, person))
    dedicated = {lane for edge in network.edges.values() for lane in cycling_lanes(edge)}
    official = defaultdict(list)
    for path in network.cycleways:
        points = [network.xy(p) for p in path]
        for a, b in zip(points, points[1:]):
            for key in network.cells(min(a[0], b[0])-24, min(a[1], b[1])-24, max(a[0], b[0])+24, max(a[1], b[1])+24):
                official[key].append((a, b))
    corroborated = set()
    for lane in dedicated:
        shape = lane.getShape()
        a, b = shape[len(shape)//2-1:len(shape)//2+1]
        midpoint = ((a[0]+b[0])/2, (a[1]+b[1])/2)
        if any(segment_projection(midpoint, a, b)[0] <= 24 for a, b in official[next(network.cells(*midpoint, *midpoint))]):
            corroborated.add(lane)
    bike_paths = []
    for lane in sorted(dedicated, key=lambda lane: lane.getID()):
        path = [lane]
        visited = {lane.getEdge()}
        for _ in range(9):
            options = [conn.getToLane() for conn in path[-1].getOutgoing()
                       if conn.getToLane() in dedicated and conn.getToLane().getEdge() not in visited]
            if not options:
                break
            path.append(max(options, key=lambda lane: lane.getLength()))
            visited.add(path[-1].getEdge())
        if sum(lane.getLength() for lane in path) >= 150:
            bike_paths.append((' '.join(lane.getEdge().getID() for lane in path),
                               str(path[0].getIndex()), 1 + 3*sum(lane in corroborated for lane in path)/len(path)))
    bike_count = round(config['bicycles_per_hour']*duration/3600) if bike_paths else 0
    bike_weights = [row[2] for row in bike_paths]
    for i in range(bike_count):
        second = rng.randrange(duration)
        route, lane_index, _ = rng.choices(bike_paths, weights=bike_weights)[0]
        bike = Element('vehicle', id=f'bike-{i}', type='bicicleta', depart=str(second), departLane=lane_index)
        SubElement(bike, 'route', edges=route)
        active.append((second, bike))
    return active, sites, bike_count


def build_routes(target, network, config, targets, profile, begin, duration, preset, scale, buses, od=None):
    rng = random.Random(config['seed'])
    routes = Element('routes')
    for row in config['fleet']:
        car = SubElement(routes, 'vType', id=row['id'], vClass='passenger', emissionClass=row['emissionClass'])
        SubElement(car, 'param', key='has.rerouting.device', value='true')
    SubElement(routes, 'vType', id='onibus_urbs', vClass='bus', emissionClass='HBEFA3/Bus', length='12',
               width='2.55', accel='1.2', decel='3.5', maxSpeed='16.67', color='0,120,180')
    SubElement(routes, 'vType', id='bicicleta', vClass='bicycle', emissionClass='Zero/default')
    SubElement(routes, 'vType', id='pedestre', vClass='pedestrian', maxSpeed=str(config['pedestrian_speed_mps']),
               speedFactor='normc(1,0.12,0.6,1.3)')
    cars, od_stats = generate_cars(network, config, targets, profile, begin, duration, preset, rng, scale, od)
    active, sites, bikes = generate_active(network, config, begin, duration, rng)
    for _, agent in sorted([*cars, *buses, *active], key=lambda trip: (trip[0], trip[1].get('id'))):
        routes.append(agent)
    indent(routes)
    ElementTree(routes).write(target, encoding='UTF-8', xml_declaration=True)
    return {'cars': len(cars), 'buses': len(buses), 'bicycles': bikes, 'pedestrians': len(active) - bikes,
            'pedestrian_sites': sites, 'origin_destination': od_stats}

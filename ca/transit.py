from collections import defaultdict
from functools import lru_cache
from math import hypot
from statistics import median
from xml.etree.ElementTree import Element, SubElement

from .sources import bus_catalog, gps_window


def episodes(points):
    group = []
    for second, point in points:
        if group and second - group[-1][0] > 100:
            yield group
            group = []
        group.append((second, point))
    if group:
        yield group


def shape_cells(network, shapes):
    result = defaultdict(set)
    for (line, _), points in shapes.items():
        for point in points:
            if point is not None:
                x, y = network.xy(point)
                result[line].update(network.cells(x-30, y-30, x+30, y+30))
    return result


def match_buses(network, begin, end, bbox):
    positions, files = gps_window(begin, end, bbox)
    lines, stops, shapes, schedules = bus_catalog(begin.date(), bbox)
    itineraries = shape_cells(network, shapes)
    stop_points = {line: [(stop, network.xy(stop['coordinates'])) for stop in values.values()]
                   for line, values in stops.items()}
    agents, samples, journeys = [], [], []
    counts = {'episodes': 0, 'rejected': 0, 'gps_points': sum(map(len, positions.values())), 'matched_points': 0,
              'scheduled_stops': 0, 'matched_stops': 0}

    @lru_cache(maxsize=40000)
    def connect(origin, target):
        return network.net.getShortestPath(origin, target, vClass='bus', maxCost=1550, withInternal=False)[0]

    for (vehicle, line), points in sorted(positions.items()):
        for episode in episodes(points):
            counts['episodes'] += 1
            if len(episode) < 3 or episode[-1][0] - episode[0][0] < 14:
                counts['rejected'] += 1
                continue
            projected = [(second, network.xy(point)) for second, point in episode]
            trace, route = [], []
            for i, (second, point) in enumerate(projected):
                prev = projected[max(0, i-2)][1]
                nxt = projected[min(len(projected)-1, i+2)][1]
                movement = hypot(nxt[0]-prev[0], nxt[1]-prev[1])
                direction = ((nxt[0]-prev[0])/movement, (nxt[1]-prev[1])/movement) if movement > 15 else None
                candidates = []
                for edge, (distance, pos, heading) in network.nearby(point, 34, 'bus').items():
                    dot = sum(a*b for a, b in zip(direction, heading)) if direction else 1.0
                    if dot < -.25:
                        continue
                    mid = edge.getShape()[len(edge.getShape())//2]
                    corridor = next(network.cells(*mid, *mid)) in itineraries[line]
                    cost = distance + 16*(1-dot) + (5 if itineraries[line] and not corridor else 0)
                    if route and edge != route[-1]:
                        cost += 4
                    candidates.append((cost, edge.getID(), edge, pos, distance))
                for _, _, edge, pos, distance in sorted(candidates)[:5]:
                    if route and edge != route[-1]:
                        gap = second - trace[-1][0]
                        transition = connect(route[-1], edge)
                        if not transition or sum(e.getLength() for e in transition[1:-1]) > 25*gap+30:
                            continue
                        route.extend(transition[1:])
                    elif not route:
                        route.append(edge)
                    elif pos < trace[-1][2] - 30:
                        continue
                    trace.append((second, edge, pos, point, distance, len(route)-1))
                    break
            if len(trace) < max(3, len(episode)*.55) or (len(route) == 1 and trace[-1][2] - trace[0][2] < 25):
                counts['rejected'] += 1
                continue
            first, last = trace[0], trace[-1]
            depart_pos = min(first[2], max(0, route[0].getLength() - 2))
            arrival_pos = min(last[2], route[-1].getLength() - .1)
            if arrival_pos < 1 or (route[0] == route[-1] and len(route) > 1):
                arrival_pos = max(.1, route[-1].getLength() - .1)
            agent_id = f'bus-{len(agents)}'
            bus = Element('vehicle', id=agent_id, type='onibus_urbs', line=line,
                          depart=str(first[0]), departPos=f'{depart_pos:.2f}', arrivalPos=f'{arrival_pos:.2f}',
                          departLane='best', departSpeed='0')
            SubElement(bus, 'route', edges=' '.join(e.getID() for e in route))
            SubElement(bus, 'param', key='urbs.vehicle_id', value=vehicle)
            dwellings = attach_stops(bus, trace, stop_points.get(line, []), depart_pos, arrival_pos)
            counts['matched_stops'] += dwellings
            counts['scheduled_stops'] += len(stops[line])
            counts['matched_points'] += len(trace)
            agents.append((first[0], bus))
            journeys.append({'id': agent_id, 'vehicle_id': vehicle, 'line_id': line, 'line_name': lines.get(line),
                             'observed_start_s': first[0], 'observed_end_s': last[0],
                             'gps_points': len(episode), 'mapped_points': len(trace),
                             'median_error_m': round(median(p[4] for p in trace), 2),
                             'timetable_records': schedules[line], 'stops': dwellings})
            for j, (second, point) in enumerate(episode):
                if j % 4 == 0 or j == len(episode)-1:
                    samples.append([second, *point, vehicle, line])
    return agents, {'files': files, **counts, 'routes': len(agents), 'line_catalog': len(lines),
                    'shape_catalog': len(shapes), 'journeys': journeys}, sorted(samples)


def attach_stops(bus, trace, stations, departure, arrival):
    stops = []
    seen = set()
    start = 0
    while start + 1 < len(trace):
        first = trace[start]
        end = start + 1
        while end < len(trace) and trace[end][5] == first[5] and hypot(
                trace[end][3][0]-first[3][0], trace[end][3][1]-first[3][1]) <= 10:
            end += 1
        duration = trace[end-1][0] - first[0]
        pos = first[2]
        if duration >= 10 and (first[5] or pos > departure + 5) and (first[5] != trace[-1][5] or pos < arrival - 5):
            nearest = [(hypot(x-first[3][0], y-first[3][1]), station['id']) for station, (x, y) in stations]
            if nearest:
                distance, station = min(nearest)
                key = first[5], station
                if distance <= 30 and key not in seen and (not stops or first[5] > stops[-1][0] or pos > stops[-1][1]+10):
                    lane = next(lane for lane in first[1].getLanes() if lane.allows('bus'))
                    pos = min(lane.getLength() - .2, max(3.2, pos))
                    if pos > 3:
                        SubElement(bus, 'stop', lane=lane.getID(), startPos=f'{pos-3:.2f}',
                                   endPos=f'{pos:.2f}', duration=str(min(60, duration)))
                        seen.add(key)
                        stops.append((first[5], pos))
        start = end
    return len(stops)

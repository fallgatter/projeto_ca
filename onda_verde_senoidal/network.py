from collections import defaultdict
from heapq import heappop, heappush
import unicodedata
from xml.etree import ElementTree as ET

from .io import ROOT, sumo_modules


CORRIDORS = {
    'kennedy': 'Avenida Presidente Kennedy',
    'sete': 'Avenida Sete de Setembro',
    'floriano': 'Avenida Marechal Floriano Peixoto',
}
ROAD_RANK = {'highway.primary': 0, 'highway.secondary': 1, 'highway.tertiary': 2}


def normalized(name):
    return ''.join(c for c in unicodedata.normalize('NFKD', name.casefold()) if not unicodedata.combining(c))


def motor(edge):
    return not edge.isSpecial() and (edge.allows('passenger') or edge.allows('bus'))


def green(state, indexes):
    return any(state[index] in 'gG' for index in indexes)


class Network:
    def __init__(self, path, bbox):
        sumolib, _ = sumo_modules()
        self.net = sumolib.net.readNet(str(path), withInternal=True)
        west, south, east, north = bbox
        self.bbox = bbox
        self.edges = {
            edge.getID(): edge for edge in self.net.getEdges()
            if motor(edge)
        }
        self.signals = {}
        self.incoming = defaultdict(dict)
        self.outgoing = defaultdict(dict)
        self.points = {}
        for light in self.net.getTrafficLights():
            signal = light.getID()
            groups = defaultdict(set)
            lanes = {}
            for source, target, index in light.getConnections():
                edge = source.getEdge()
                if not motor(edge) or not (source.allows('passenger') or source.allows('bus')):
                    continue
                self.incoming[edge.getID()].setdefault(signal, set()).add(index)
                groups[edge.getID()].add(index)
                lane = lanes.setdefault(source.getID(), [edge.getID(), set(), source.getShape()[-1]])
                lane[1].add(index)
                if motor(target.getEdge()):
                    self.outgoing[signal].setdefault(target.getEdge().getID(), set()).add(index)
            if not lanes:
                continue
            x = sum(lane[2][0] for lane in lanes.values()) / len(lanes)
            y = sum(lane[2][1] for lane in lanes.values()) / len(lanes)
            lon, lat = self.net.convertXY2LonLat(x, y)
            if west <= lon <= east and south <= lat <= north:
                self.signals[signal] = (dict(groups), lanes)
                self.points[signal] = [round(x, 1), round(y, 1)]
        self.corridor_edges = {
            key: {eid for eid, edge in self.edges.items() if normalized(name) == normalized(edge.getName())}
            for key, name in CORRIDORS.items()
        }
        self.corridor_lights = {
            key: sorted(signal for signal, (groups, _) in self.signals.items() if edges.intersection(groups))
            for key, edges in self.corridor_edges.items()
        }

    def downstream(self, source, first_edge, street=None, limit=700):
        """Return the first lights reachable along outgoing, legal motor connections."""
        queue = [(0., 0., first_edge)]
        visited = set()
        while queue:
            distance, seconds, eid = heappop(queue)
            if eid in visited or distance > limit:
                continue
            visited.add(eid)
            edge = self.edges[eid]
            distance += edge.getLength()
            if distance > limit:
                continue
            seconds += edge.getLength() / max(3., edge.getSpeed())
            stops = self.incoming.get(eid, {})
            if stops:
                for target in sorted(stops):
                    if target != source and target in self.signals:
                        yield target, eid, distance, max(1, round(seconds))
                continue
            for following in edge.getOutgoing():
                if following.getID() in self.edges and (street is None or normalized(following.getName()) == street):
                    heappush(queue, (distance, seconds, following.getID()))

    def neighbors(self, active):
        routes = {}
        for signal in sorted(active):
            for eid in sorted(self.outgoing[signal]):
                for target, approach, _, seconds in self.downstream(signal, eid, limit=400):
                    if target in active:
                        routes.setdefault(eid, []).append((signal, target, approach, seconds))
        return routes

    def map_data(self):
        roads = []
        coordinates = {}
        for edge_id, edge in self.edges.items():
            shape = edge.getShape()
            coords = [[round(x, 1), round(y, 1)] for x, y in shape]
            rank = ROAD_RANK.get(edge.getType(), 3)
            roads.append([rank, coords])
            coordinates[edge_id] = coords
        corridors = {}
        for key, name in CORRIDORS.items():
            edges = [self.edges[eid] for eid in sorted(self.corridor_edges[key])]
            shapes = [[[round(x, 1), round(y, 1)] for x, y in edge.getShape()] for edge in edges]
            points = [point for shape in shapes for point in shape]
            xmin, ymin = map(min, zip(*points))
            xmax, ymax = map(max, zip(*points))
            corridors[key] = dict(name=name, bounds=[xmin-130, ymin-130, xmax+130, ymax+130],
                                  signals=self.corridor_lights[key], shapes=shapes)
        lights = {}
        approach_shapes = {}
        for signal, (_, lanes) in self.signals.items():
            approaches = []
            for edge, indexes, pos in lanes.values():
                if edge not in approach_shapes:
                    approach_shapes[edge] = self.approach_shape(edge, coordinates)
                name = self.edges[edge].getName()
                approaches.append([round(pos[0], 1), round(pos[1], 1), sorted(indexes),
                                   name, [key for key, ids in self.corridor_edges.items() if edge in ids], edge])
            lights[signal] = dict(point=self.points[signal], approaches=approaches,
                                  name=' × '.join(sorted({row[3] for row in approaches if row[3]})) or signal)
        west, south, east, north = self.bbox
        xy = [self.net.convertLonLat2XY(lon, lat) for lon in (west, east) for lat in (south, north)]
        return dict(roads=roads, corridors=corridors, lights=lights, approach_shapes=approach_shapes,
                    bounds=[min(x for x, _ in xy), min(y for _, y in xy),
                            max(x for x, _ in xy), max(y for _, y in xy)])

    def approach_shape(self, edge_id, coordinates):
        edge = self.edges[edge_id]
        street = normalized(edge.getName())
        path = [edge_id]
        length = edge.getLength()
        # The lane at the stop line can be a split only a fraction of a meter long.
        while street and length < 80:
            upstream = [previous for previous in edge.getIncoming()
                        if previous.getID() in self.edges and previous.getID() not in path
                        and previous.getFromNode() != edge.getToNode()
                        and normalized(previous.getName()) == street]
            if not upstream:
                break
            edge = max(upstream, key=lambda previous: (previous.getLength(), previous.getID()))
            path.append(edge.getID())
            length += edge.getLength()
        return [point for key in reversed(path) for point in coordinates[key]]

    def reference_plan(self, net_path, peak, destination, extra=None):
        """Keep fixed signal stages and derive arterial offsets from network travel times."""
        raw = {el.attrib['id']: el for _, el in ET.iterparse(net_path, events=('end',))
               if el.tag == 'tlLogic' and el.get('type') == 'static'}
        special = {}
        files = ['onda-verde-kennedy.add.xml']
        if peak == 'manha':
            files.append('setran-reboucas-2015.add.xml')
        for filename in files:
            special.update({el.get('id'): el for el in ET.parse(ROOT/'config/signals'/filename).findall('tlLogic')})
        if extra:
            special.update({el.get('id'): el for el in ET.parse(extra).findall('tlLogic')})
        programs = raw | special
        phases = {}
        for signal, entry in programs.items():
            if entry.get('type') != 'static':
                raise ValueError(f'Programa de {signal} precisa ser estático.')
            phases[signal] = [(int(float(p.get('duration'))), p.get('state')) for p in entry.findall('phase')]

        links = []
        for source, outgoing in self.outgoing.items():
            if source not in self.signals or source not in phases:
                continue
            approaches, _ = self.signals[source]
            by_name = defaultdict(set)
            for eid, indexes in approaches.items():
                by_name[normalized(self.edges[eid].getName())].update(indexes)
            for eid, indexes in outgoing.items():
                road = self.edges[eid]
                street = normalized(road.getName())
                rank = ROAD_RANK.get(road.getType(), 3)
                if not street or street not in by_name or rank == 3:
                    continue
                source_indexes = indexes.intersection(by_name[street])
                start = self.green_start(phases[source], source_indexes)
                if start is None:
                    continue
                for target, approach, distance, seconds in self.downstream(source, eid, street):
                    if target not in phases or sum(d for d, _ in phases[source]) != sum(d for d, _ in phases[target]):
                        continue
                    end = self.green_start(phases[target], self.incoming[approach][target])
                    if end is not None:
                        priority = 0 if street in (normalized(name) for name in CORRIDORS.values()) else 1
                        links.append((priority, rank, distance, source, target, start + seconds - end))

        # A maximum-priority forest avoids imposing incompatible offsets at shared intersections.
        potentials = {signal: (signal, 0) for signal in self.signals}
        anchored = {signal: int(float(special[signal].get('offset', '0')))
                    for signal in self.signals if signal in special}

        def root(signal):
            parent, delta = potentials[signal]
            if parent == signal:
                return signal, 0
            leader, total = root(parent)
            potentials[signal] = (leader, delta + total)
            return potentials[signal]

        touched = set()
        for _, _, _, source, target, offset in sorted(links):
            first, first_delta = root(source)
            second, second_delta = root(target)
            if first == second or (first in anchored and second in anchored):
                continue
            difference = offset + first_delta - second_delta
            if second in anchored:
                potentials[first] = second, -difference
            else:
                potentials[second] = first, difference
            touched.update((source, target))

        result = ET.Element('additional')
        origins = {}
        for signal in sorted(touched | special.keys()):
            if signal in special:
                result.append(special[signal])
                origins[signal] = special[signal].get('programID')
                continue
            leader, seconds = root(signal)
            cycle = sum(d for d, _ in phases[signal])
            program = programs[signal]
            program.set('programID', 'onda-reconstruida')
            program.set('offset', str((anchored.get(leader, 0) + seconds) % cycle))
            result.append(program)
            origins[signal] = 'onda-reconstruida'
        ET.indent(result)
        ET.ElementTree(result).write(destination, encoding='utf-8', xml_declaration=True)
        return phases, origins

    @staticmethod
    def green_start(phases, indexes):
        position = 0
        longest = None
        for duration, state in phases:
            if not any(letter in 'yYuU' for letter in state) and green(state, indexes):
                if longest is None or duration > longest[0]:
                    longest = duration, position
            position += duration
        return longest[1] if longest else None

import subprocess
import unicodedata
from collections import defaultdict
from math import ceil, hypot

from .io import CACHE, read_json, sumo_binary, sumo_modules


def normalized(name):
    return ''.join(c for c in unicodedata.normalize('NFKD', name.casefold()) if not unicodedata.combining(c))


def cycling_lanes(edge):
    return [lane for lane in edge.getLanes()
            if lane.allows('bicycle') and not lane.allows('passenger') and not lane.allows('bus')]


def build_network(osm, bbox):
    folder = CACHE / 'network'
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / 'curitiba.net.xml'
    pending = folder / 'curitiba.part.net.xml'
    log = folder / 'netconvert.log'
    cmd = [sumo_binary('netconvert'), '--osm-files', str(osm),
           '--keep-edges.in-geo-boundary=' + ','.join(map(str, bbox)), '--osm.sidewalks', 'true',
           '--osm.crossings', 'true', '--sidewalks.guess', 'true', '--crossings.guess', 'true',
           '--tls.guess-signals', 'true', '--output.street-names', 'true', '-o', str(pending)]
    with log.open('w', encoding='utf-8') as output:
        subprocess.run(cmd, stdout=output, stderr=subprocess.STDOUT, check=True)
    pending.replace(target)
    return target


def segment_projection(point, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = hypot(dx, dy)
    if length == 0:
        return hypot(point[0] - a[0], point[1] - a[1]), 0, (0, 0)
    ux, uy = dx / length, dy / length
    position = min(length, max(0.0, (point[0] - a[0]) * ux + (point[1] - a[1]) * uy))
    return hypot(point[0] - a[0] - position * ux, point[1] - a[1] - position * uy), position, (ux, uy)


class RoadNetwork:
    def __init__(self, path, config):
        sumolib, _ = sumo_modules()
        self.net = sumolib.net.readNet(str(path), withInternal=True, withPedestrianConnections=True)
        self.edges = {e.getID(): e for e in self.net.getEdges() if not e.isSpecial()}
        self.corridors = tuple(normalized(s) for s in config['corridors'])
        ip_path = CACHE/'ippuc/cycleways.json'
        layer = read_json(ip_path) if ip_path.is_file() else {}
        self.ippuc = layer if layer.get('bbox') == config['bbox'] else {}
        self.cycleways = []
        for feature in self.ippuc.get('features', []):
            geometry = feature.get('geometry') or {}
            coordinates = geometry.get('coordinates', [])
            if geometry.get('type') == 'LineString':
                self.cycleways.append(coordinates)
            elif geometry.get('type') == 'MultiLineString':
                self.cycleways.extend(coordinates)
        self.grid = defaultdict(list)
        self.cell_size = 75
        for edge in self.edges.values():
            shape = edge.getShape()
            if not (edge.allows('bus') or edge.allows('passenger')):
                continue
            position = 0.0
            for a, b in zip(shape, shape[1:]):
                for key in self.cells(min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])):
                    self.grid[key].append((edge, a, b, position))
                position += hypot(b[0] - a[0], b[1] - a[1])

    def cells(self, x0, y0, x1, y1):
        for x in range(int(x0 // self.cell_size), int(x1 // self.cell_size) + 1):
            for y in range(int(y0 // self.cell_size), int(y1 // self.cell_size) + 1):
                yield x, y

    def xy(self, point):
        return self.net.convertLonLat2XY(*point)

    def lonlat(self, point):
        return [round(x, 7) for x in self.net.convertXY2LonLat(*point)]

    def nearby(self, point, radius, vclass):
        x, y = point
        candidates = {}
        for key in self.cells(x-radius, y-radius, x+radius, y+radius):
            for edge, a, b, start in self.grid.get(key, ()):
                if not edge.allows(vclass):
                    continue
                distance, pos, heading = segment_projection(point, a, b)
                if distance <= radius and (edge not in candidates or candidates[edge][0] > distance):
                    candidates[edge] = distance, min(start + pos, edge.getLength()), heading
        return candidates

    def is_corridor(self, edge):
        name = normalized(edge.getName())
        return any(s in name for s in self.corridors)

    def signal_junctions(self):
        nodes = {}
        for tls in self.net.getTrafficLights():
            for incoming, _, _ in tls.getConnections():
                edge = incoming.getEdge()
                if edge.isSpecial() or not (edge.allows('bus') or edge.allows('passenger')):
                    continue
                node = edge.getToNode()
                nodes[node.getID()] = node
        return nodes

    def map_data(self):
        def draw(kind, shape):
            x, y = roads[kind]
            for lon, lat in map(self.lonlat, shape):
                x.append(lon)
                y.append(lat)
            x.append(None)
            y.append(None)

        roads = defaultdict(lambda: [[], []])
        for edge in self.edges.values():
            if self.is_corridor(edge):
                draw('corridors', edge.getShape())
            elif edge.allows('passenger') or edge.allows('bus'):
                draw('roads', edge.getShape())
            for lane in cycling_lanes(edge):
                draw('cycleways', lane.getShape())
        if self.cycleways:
            x, y = roads['ippuc_cycleways']
            for path in self.cycleways:
                for lon, lat in path:
                    x.append(lon)
                    y.append(lat)
                x.append(None)
                y.append(None)
        return dict(roads)

    def intersection_name(self, node):
        names = sorted({e.getName() for e in node.getIncoming() + node.getOutgoing() if e.getName()})
        return ' × '.join(names) if names else node.getID()

    def flow_points(self, count):
        groups = defaultdict(list)
        for edge in self.edges.values():
            if not edge.allows('passenger') or edge.getLength() < 35:
                continue
            name = normalized(edge.getName())
            key = next((s for s in self.corridors if s in name), None)
            if key:
                groups[key].append(edge)
        for edges in groups.values():
            edges.sort(key=lambda e: e.getLength(), reverse=True)
        result = []
        for index in range(max(map(len, groups.values()), default=0)):
            for edges in groups.values():
                if index >= len(edges):
                    continue
                shape = edges[index].getShape()
                a, b = shape[len(shape)//2 - 1:len(shape)//2 + 1]
                point = self.lonlat(((a[0]+b[0])/2, (a[1]+b[1])/2))
                if all(hypot(point[0] - p[0], point[1] - p[1]) > 0.0003 for p in result):
                    result.append(point)
                if len(result) == count:
                    return result
        return result


def edge_observations(network, records, directional):
    matches = defaultdict(list)
    for row in records:
        points = [network.xy(p) for p in row['coordinates']]
        matched = set()
        for a, b in zip(points, points[1:]):
            length = hypot(b[0] - a[0], b[1] - a[1])
            if length < 1:
                continue
            direction = ((b[0] - a[0]) / length, (b[1] - a[1]) / length)
            count = ceil(length / 32)
            for n in range(count):
                t = (n + .5) / count
                midpoint = (a[0] + (b[0]-a[0])*t, a[1] + (b[1]-a[1])*t)
                choices = []
                for edge, (distance, _, heading) in network.nearby(midpoint, 22, 'passenger').items():
                    dot = sum(h * d for h, d in zip(heading, direction))
                    if not directional:
                        dot = abs(dot)
                    if dot >= .58:
                        choices.append((distance + 12 * (1 - dot), edge.getID()))
                if choices:
                    matched.add(min(choices)[1])
        for edge_id in matched:
            matches[edge_id].append(row)
    return dict(matches)

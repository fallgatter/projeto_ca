import json
import lzma
import os
import shutil
import tempfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import ijson

from .io import CACHE, LOCAL, PRESETS, ROOT, envelope, read_json, utc, window, write_json

URBS = 'https://dadosabertos.c3sl.ufpr.br/curitibaurbs/'
FLOW = 'https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/18/json'
FLOW_REFRESH_SECONDS = 900
FLOW_POINTS = 16
IPPUC_CYCLEWAYS = ('https://geocuritiba.ippuc.org.br/server/rest/services/GeoCuritiba/'
                  'CICLOVIA_dashboard/FeatureServer/0/query')
KINDS = ('veiculos', 'linhas', 'shapeLinha', 'pontosLinha', 'tabelaLinha')


def tomtom_key(variable='TOMTOM_API_KEY'):
    if os.getenv(variable, '').strip():
        return os.environ[variable].strip()
    path = ROOT / '.env'
    if path.exists():
        for row in path.read_text(encoding='utf-8-sig').splitlines():
            name, _, value = row.partition('=')
            if name.strip() == variable and value.strip().strip('\"\''):
                return value.strip().strip('\"\'')
    raise ValueError(f'Preencha {variable} no .env local.')


def request(url, params=None, timeout=25, payload=None, show_messages=False, method=None):
    address = url + ('?' + urlencode(params) if params else '')
    headers = {'User-Agent': 'projeto-ca-utfpr/1.0'}
    if payload is not None:
        headers['Content-Type'] = 'application/json'
    body = json.dumps(payload).encode('utf-8') if payload is not None else None
    try:
        return urlopen(Request(address, headers=headers, data=body, method=method), timeout=timeout)
    except HTTPError as exc:
        message = f'HTTP {exc.code}'
        if show_messages:
            try:
                data = json.loads(exc.read(4096))
                details = (data.get('messages') or [data.get('message')]) if isinstance(data, dict) else []
            except (ValueError, OSError):
                details = []
            if isinstance(details, list):
                detail = ' '.join(item for item in details if isinstance(item, str))
                key = (params or {}).get('key')
                if key:
                    detail = detail.replace(key, '[chave omitida]')
                if detail:
                    message += f' ({detail[:1000]})'
        raise ValueError(message) from None
    except (URLError, TimeoutError) as exc:
        reason = getattr(exc, 'reason', exc)
        raise ValueError(f'Conexão indisponível ({type(reason).__name__}).') from None


def fetch_flow(points):
    key = tomtom_key()

    def sample(point):
        lon, lat = point
        observed = datetime.now(timezone.utc)
        try:
            with request(FLOW, {'key': key, 'point': f'{lat:.6f},{lon:.6f}', 'unit': 'kmph', 'openLr': 'true'}) as response:
                flow = json.load(response)['flowSegmentData']
            return {
                'observed_at': utc(observed), 'query': point, 'openlr': flow.get('openlr'),
                'coordinates': [[p['longitude'], p['latitude']] for p in flow['coordinates']['coordinate']],
                'speed_kmh': flow['currentSpeed'], 'free_speed_kmh': flow['freeFlowSpeed'],
                'travel_time_s': flow['currentTravelTime'], 'free_travel_time_s': flow['freeFlowTravelTime'],
                'confidence': flow['confidence'], 'closed': flow['roadClosure'],
            }
        except (ValueError, KeyError, TypeError) as exc:
            error = str(exc) if isinstance(exc, ValueError) else 'Resposta sem campos de tráfego.'
            return {'query': point, 'error': error}

    first = sample(points[0])
    if 'error' in first:
        raise ValueError(f'TomTom Traffic Flow: {first["error"]}')
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = [first, *pool.map(sample, points[1:])]
    observations = [record for record in results if 'error' not in record]
    errors = [record for record in results if 'error' in record]
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    path = CACHE / 'tomtom' / f'flow-{stamp}.json'
    write_json(path, envelope('tomtom.flow', source=FLOW, observations=observations, errors=errors))
    return path, len(observations), len(errors)


class FlowRefresh:
    def __init__(self, config):
        self.config = config
        self.points = None
        self.lock = Lock()
        self.last_attempt = None
        self.error = None

    def update(self, manual):
        from .network import RoadNetwork
        from .results import current_capture

        if not self.lock.acquire(blocking=False):
            return current_capture(), 'Coleta em andamento.'
        try:
            capture = current_capture()
            observations = capture['observations']
            ttl = 60 if manual else FLOW_REFRESH_SECONDS
            fresh = observations and (datetime.now(timezone.utc) - datetime.fromisoformat(
                observations[0]['observed_at'])).total_seconds() < ttl
            attempted_recently = self.last_attempt is not None and monotonic() - self.last_attempt < ttl
            if fresh or attempted_recently:
                return capture, self.error if attempted_recently else None
            self.last_attempt = monotonic()
            try:
                if self.points is None:
                    net = CACHE/'network/curitiba.net.xml'
                    if not net.is_file():
                        raise ValueError('Gere a rede SUMO para selecionar os pontos de coleta.')
                    self.points = RoadNetwork(net, self.config).flow_points(FLOW_POINTS)
                    if not self.points:
                        raise ValueError('Nenhum ponto de coleta nos corredores configurados.')
                fetch_flow(self.points)
                self.error = None
                return current_capture(), None
            except (OSError, ValueError) as exc:
                self.error = str(exc)
                return capture, self.error
        finally:
            self.lock.release()


def urbs_file(day, kind):
    return CACHE / 'urbs' / f'{day:%Y_%m_%d}_{kind}.json.xz'


def fetch_urbs(jobs):
    def download(job):
        target = urbs_file(*job)
        url = URBS + target.name
        if target.is_file():
            return {'file': target.name, 'url': url, 'bytes': target.stat().st_size, 'status': 'cached'}
        target.parent.mkdir(parents=True, exist_ok=True)
        pending = None
        try:
            with request(url, timeout=90) as response, tempfile.NamedTemporaryFile(
                    dir=target.parent, suffix='.xz.part', delete=False) as output:
                pending = Path(output.name)
                shutil.copyfileobj(response, output)
            with lzma.open(pending, 'rb') as source:
                source.read(64)
            pending.replace(target)
            return {'file': target.name, 'url': url, 'bytes': target.stat().st_size, 'status': 'downloaded'}
        except (OSError, ValueError, lzma.LZMAError, EOFError) as exc:
            return {'file': target.name, 'url': url, 'status': 'unavailable', 'error': str(exc)}
        finally:
            if pending is not None:
                pending.unlink(missing_ok=True)

    with ThreadPoolExecutor(max_workers=5) as pool:
        return list(pool.map(download, jobs))


def fetch_week(through):
    jobs = [(through - timedelta(days=i), kind) for i in range(7) for kind in KINDS]
    jobs.append((through + timedelta(days=1), 'veiculos'))
    results = fetch_urbs(jobs)
    path = CACHE / 'urbs' / f'week-{through}.json'
    write_json(path, envelope('urbs.week', through=through.isoformat(), files=results))
    return path, results


def records(path):
    if path.is_file():
        with lzma.open(path, 'rb') as stream:
            line = stream.readline()
            while line and not line.strip():
                line = stream.readline()
            if line.lstrip().startswith(b'['):
                stream.seek(0)
                yield from ijson.items(stream, 'item', use_float=True)
            else:
                if line:
                    yield json.loads(line)
                for raw in stream:
                    if raw.strip():
                        yield json.loads(raw)


def coordinates(row):
    return tuple(float(str(row[key]).replace(',', '.')) for key in ('LON', 'LAT'))


def contains(bbox, point):
    west, south, east, north = bbox
    lon, lat = point
    return west <= lon <= east and south <= lat <= north


def fetch_ippuc(bbox):
    params = {'f': 'geojson', 'where': 'operacional=1 AND ctba_tipo_ciclovia IN (1,2,3,4)',
              'geometry': ','.join(map(str, bbox)), 'geometryType': 'esriGeometryEnvelope',
              'spatialRel': 'esriSpatialRelIntersects', 'inSR': 4326, 'outSR': 4326,
              'outFields': 'objectid,nome,ctba_tipo_ciclovia', 'returnGeometry': 'true',
              'orderByFields': 'objectid', 'resultRecordCount': 1000}
    features = []
    for offset in range(0, 10000, 1000):
        with request(IPPUC_CYCLEWAYS, {**params, 'resultOffset': offset}) as response:
            data = json.load(response)
        if 'features' not in data:
            raise ValueError('GeoCuritiba retornou uma resposta sem feições cicloviárias.')
        features.extend(data['features'])
        if not data.get('exceededTransferLimit') and len(data['features']) < 1000:
            break
    target = CACHE/'ippuc/cycleways.json'
    write_json(target, envelope('ippuc.cycleways', source=IPPUC_CYCLEWAYS, retrieved_at=utc(datetime.now(timezone.utc)),
                                bbox=bbox, features=features))
    return target, len(features)


def gps_daily(published, bbox):
    path = urbs_file(published, 'veiculos')
    if not path.exists():
        return None
    target = path.with_name(f'{published.isoformat()}-positions.json')
    if target.exists():
        data = read_json(target)
        if data['bbox'] == bbox and data['source_bytes'] == path.stat().st_size:
            return data
    counts = Counter()
    positions = []
    invalid = 0
    for row in records(path):
        try:
            timestamp = row['DTHR']
            point = coordinates(row)
            vehicle, line = row['VEIC'].strip(), row['COD_LINHA'].strip()
            if not vehicle or not line or len(timestamp) != 19:
                raise ValueError
        except (KeyError, TypeError, ValueError):
            invalid += 1
            continue
        counts[timestamp[:10]] += 1
        if contains(bbox, point):
            try:
                when = datetime.fromisoformat(f'{timestamp[6:10]}-{timestamp[3:5]}-{timestamp[:2]}T{timestamp[11:]}')
            except ValueError:
                invalid += 1
                continue
            positions.append([when.isoformat(), vehicle, line, *point])
    data = envelope('urbs.positions', source=URBS + path.name, source_bytes=path.stat().st_size,
                    bbox=bbox, records_by_date=dict(counts), invalid=invalid, positions=positions)
    write_json(target, data)
    return data


def audit_week(through, bbox):
    archives = []
    for delta in range(-1, 7):
        day = through - timedelta(days=delta)
        data = gps_daily(day, bbox)
        archives.append({'archive': day.isoformat(), 'source': URBS + urbs_file(day, 'veiculos').name,
                         'records_by_date': data['records_by_date'] if data else {},
                         'positions_in_bbox': len(data['positions']) if data else None,
                         'invalid': data['invalid'] if data else None})
    target = CACHE/'urbs'/f'coverage-{through}.json'
    write_json(target, envelope('urbs.coverage', through=through.isoformat(), archives=archives))
    return target


def gps_window(begin, end, bbox):
    selected = defaultdict(dict)
    files = []
    for published in (begin.date(), begin.date() + timedelta(days=1)):
        data = gps_daily(published, bbox)
        if not data:
            continue
        files.append({'url': data['source'], 'records_by_date': data['records_by_date']})
        for timestamp, vehicle, line, lon, lat in data['positions']:
            when = datetime.fromisoformat(timestamp).replace(tzinfo=LOCAL)
            if begin <= when < end:
                selected[(vehicle, line)][int((when - begin).total_seconds())] = (lon, lat)
    return {key: sorted(positions.items()) for key, positions in selected.items()}, files


def cached_urbs_reference(bbox, periods, selected=None):
    if selected is not None:
        days = [selected]
    else:
        catalogs = (CACHE/'urbs').glob('[0-9][0-9][0-9][0-9]_[0-9][0-9]_[0-9][0-9]_linhas.json.xz')
        days = [date.fromisoformat(path.name[:10].replace('_', '-')) for path in catalogs]
        days.sort(key=lambda day: (any(first <= day <= last for first, last in periods), day), reverse=True)
    for day in days:
        if day.weekday() < 5 and all(urbs_file(day, kind).is_file() for kind in KINDS if kind != 'veiculos'):
            if all(gps_window(*window(day.isoformat(), peak), bbox)[0] for peak in PRESETS):
                return day
    detail = f' em {selected:%d/%m/%Y}' if selected is not None else ''
    raise ValueError(f'URBS: sem arquivos locais de um dia útil com dados nos dois picos{detail}. '
                     'Use o comando urbs para preparar o cache e execute novamente.')


def bus_catalog(day, bbox):
    lines = {r['COD']: r['NOME'] for r in records(urbs_file(day, 'linhas'))}
    stops = defaultdict(dict)
    for row in records(urbs_file(day, 'pontosLinha')):
        point = coordinates(row)
        if contains(bbox, point):
            stops[row['COD']][row['NUM']] = {'coordinates': point, 'name': row['NOME'], 'id': row['NUM']}
    shapes = defaultdict(list)
    for row in records(urbs_file(day, 'shapeLinha')):
        shapes[(row['COD'], row['SHP'])].append(coordinates(row))
    relevant = {key: [p if contains(bbox, p) else None for p in points] for key, points in shapes.items()
                if any(contains(bbox, p) for p in points)}
    schedules = Counter(row['COD'] for row in records(urbs_file(day, 'tabelaLinha')) if row['COD'] in stops)
    return lines, stops, relevant, schedules

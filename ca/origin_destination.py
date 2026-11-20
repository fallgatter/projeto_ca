import json
from collections import defaultdict
from hashlib import sha256
from math import isfinite
from time import monotonic, sleep

from .io import CACHE, LOCAL, PRESETS, read_json, write_json
from .monthly import WEEKDAYS, boundary
from .sources import request, tomtom_key

OD_API = 'https://api.tomtom.com/origindestination/1/analysis'
ZONES_PER_SIDE = 3
OD_STATES = ('ACCEPTED', 'ENDED', 'RUNNING', 'WAITING')


def zone_boxes(bbox):
    west, south, east, north = bbox
    lon = [west + (east-west)*i/ZONES_PER_SIDE for i in range(ZONES_PER_SIDE)] + [east]
    lat = [south + (north-south)*i/ZONES_PER_SIDE for i in range(ZONES_PER_SIDE)] + [north]
    return [(lon[c], lat[r], lon[c+1], lat[r+1])
            for r in range(ZONES_PER_SIDE) for c in range(ZONES_PER_SIDE)]


def matrix_request(bbox, first, last):
    regions = [{'type': 'Feature', 'properties': {'name': f'Zona {i}'},
                'geometry': {'type': 'Polygon', 'coordinates': [boundary(zone)]}}
               for i, zone in enumerate(zone_boxes(bbox), 1)]
    payload = {
        'analysisVersion': 2, 'dataSources': 'ALL_PASSENGER', 'regions': regions,
        'time': {'zoneId': str(LOCAL), 'daysOfWeek': list(WEEKDAYS),
                 'dateRanges': [{'startDate': first.isoformat(), 'endDate': last.isoformat()}],
                 'timeRanges': [{'startTime': start, 'endTime': end} for start, end in PRESETS.values()]},
    }
    suffix = sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:10]
    return {'name': f'UTFPR Curitiba OD {first:%Y-%m} {suffix}', **payload}


def matrix_pairs(data, peak):
    pairs = defaultdict(float)
    for row in data.get('links', []):
        if not isinstance(row, list) or len(row) != 5:
            raise ValueError('TomTom O/D: resultado incompatível com a Flow Matrix v2.')
        origin, dest, via, external_ends, share = row
        if (any(type(index) is not int or not 0 <= index < ZONES_PER_SIDE**2 for index in (origin, dest, via))
                or type(external_ends) is not int or external_ends not in range(4)
                or type(share) not in (int, float) or not isfinite(share) or share < 0):
            raise ValueError('TomTom O/D: linha inválida na Flow Matrix v2.')
        if via == dest and share > 0:
            pairs[origin, dest, external_ends] += share
    if not pairs:
        raise ValueError(f'TomTom O/D: não há viagens na matriz do pico {peak}.')
    return dict(pairs)


def monthly_matrices(bbox, first, last):
    payload = matrix_request(bbox, first, last)
    cache = CACHE/'tomtom'/(payload['name'].lower().replace(' ', '-') + '.json')
    if cache.is_file():
        data = read_json(cache)
        return data['id'], {peak: matrix_pairs(data['results'][peak], peak) for peak in PRESETS}

    key = tomtom_key('TOMTOM_STATS_API_KEY')

    def call(path='', params=None, body=None, method=None):
        try:
            with request(OD_API + path, {'key': key, **(params or {})},
                         payload=body, method=method, show_messages=True) as response:
                return None if method == 'POST' else json.load(response)
        except ValueError as exc:
            raise ValueError(f'TomTom O/D Analysis: {exc}. Confira o acesso ao O/D Analysis v2 no MOVE.') from None

    listing = call(params={'name': payload['name'], 'types': 'FLOW_MATRIX', 'limit': 25})
    matches = [job for job in listing.get('analysisInfos', [])
               if job.get('name') == payload['name'] and job.get('analysisVersion') == 2
               and job.get('status') in OD_STATES]
    job = min(matches, key=lambda item: OD_STATES.index(item['status'])) if matches else call('/flowmatrix', body=payload)
    job_id = str(job.get('id', ''))
    if not job_id.isdigit() or job.get('analysisVersion') != 2:
        raise ValueError('TomTom O/D: a API não identificou a análise como Flow Matrix v2.')
    print(f'TomTom O/D: análise {job_id}', flush=True)
    path = f'/flowmatrix/{job_id}'
    deadline = monotonic() + 20 * 60
    while True:
        info = call(path)['analysisInfo']
        state = info['status']
        if state == 'ACCEPTED':
            break
        if state == 'ENDED':
            try:
                call(f'/{job_id}/accept', method='POST')
            except ValueError:
                if call(path)['analysisInfo']['status'] != 'ACCEPTED':
                    raise
            break
        if state not in ('WAITING', 'RUNNING'):
            raise ValueError(f'TomTom O/D: análise {job_id} no estado {state}. Confira os detalhes no MOVE.')
        if monotonic() >= deadline:
            raise ValueError(f'TomTom O/D: análise {job_id} ainda em processamento. Execute novamente para retomá-la.')
        sleep(15)
    data = {'id': job_id, 'name': payload['name'], 'results': {
        peak: call(path + '/result/trips', {'dateRange': 0, 'timeRange': index})
        for index, peak in enumerate(PRESETS)}}
    matrices = {peak: matrix_pairs(data['results'][peak], peak) for peak in PRESETS}
    write_json(cache, data)
    return job_id, matrices

import gzip
import json
from datetime import timedelta
from hashlib import sha256
from time import monotonic, sleep
from urllib.parse import unquote, urlsplit

from .io import CACHE, LOCAL, PRESETS, read_json, window, write_json
from .sources import KINDS, fetch_urbs, gps_window, request, tomtom_key

STATS = 'https://api.tomtom.com/traffic/trafficstats'
WEEKDAYS = ('MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY')
PENDING = {'NEW', 'SCHEDULED', 'MAPMATCHING', 'MAPMATCHED', 'READING_GEOBASE', 'CALCULATIONS'}


def previous_month(today):
    last = today.replace(day=1) - timedelta(days=1)
    return last.replace(day=1), last


def boundary(bbox):
    west, south, east, north = bbox
    return [[west, south], [east, south], [east, north], [west, north], [west, south]]


def report_timesets(data, first, last):
    features = data.get('features', []) if isinstance(data, dict) else []
    if not features:
        raise ValueError('Forneça um relatório TomTom Traffic Stats Área completa em GeoJSON.')
    meta = next((f.get('properties', {}) for f in features if f.get('geometry') is None), {})
    dates = [row for row in meta.get('dateRanges', []) if row.get('from') == first.isoformat()
             and row.get('to') == last.isoformat() and not row.get('exclusions')
             and not set(row.get('excludedDaysOfWeek', [])) & set(WEEKDAYS)]
    if len(dates) != 1:
        raise ValueError(f'O GeoJSON TomTom precisa cobrir integralmente {first:%d/%m/%Y} a {last:%d/%m/%Y}.')
    if meta.get('zoneId') != str(LOCAL) or meta.get('userPreference', {}).get('distanceUnit') != 'KILOMETERS':
        raise ValueError('O relatório TomTom precisa usar America/Sao_Paulo e quilômetros.')
    by_peak = {}
    for peak, hours in PRESETS.items():
        expected = {day: ['-'.join(hours)] for day in WEEKDAYS}
        candidates = [row for row in meta.get('timeSets', [])
                      if {day['dayOfWeek']: ['-'.join(t.strip().zfill(5) for t in interval.split('-'))
                                           for interval in day['timeRanges']]
                          for day in row.get('dayToTimeRanges', [])} == expected]
        if len(candidates) != 1:
            raise ValueError(f'O GeoJSON TomTom precisa de uma janela de segunda a sexta para {"–".join(hours)}.')
        by_peak[peak] = candidates[0]['@id']
    return dates[0]['@id'], by_peak


def report_request(config, first, last):
    suffix = sha256(json.dumps([config['bbox'], PRESETS], sort_keys=True).encode()).hexdigest()[:10]
    return {
        'jobName': f'UTFPR Curitiba {first:%Y-%m} {suffix}',
        'distanceUnit': 'KILOMETERS',
        'network': {'name': config['name'], 'timeZoneId': str(LOCAL), 'frcs': list(range(8)),
                    'geometry': {'type': 'MultiPolygon', 'coordinates': [[boundary(config['bbox'])]]},
                    'probeSource': 'ALL'},
        'dateRange': {'name': f'{first:%Y-%m}', 'from': first.isoformat(), 'to': last.isoformat()},
        'timeSets': [{'name': peak, 'timeGroups': [{'days': [day[:3] for day in WEEKDAYS],
                                                  'times': ['-'.join(hours)]}]}
                     for peak, hours in PRESETS.items()],
    }


def download_report(payload):
    try:
        key = tomtom_key('TOMTOM_STATS_API_KEY')
    except ValueError as exc:
        raise ValueError(f'{exc} Use uma chave do MOVE ou importe o GeoJSON com --traffic-stats.') from None

    def call(path, params=None, body=None):
        try:
            with request(STATS + path, {'key': key, **(params or {})}, payload=body, show_messages=True) as response:
                return json.load(response)
        except ValueError as exc:
            raise ValueError(f'TomTom Traffic Stats: {exc}. Confira o acesso e as datas disponíveis no MOVE.') from None

    jobs = call('/job/search/1', {'name': payload['jobName'], 'type': 'areaanalysis',
                                 'state': ','.join(sorted(PENDING | {'DONE', 'NEED_CONFIRMATION'}))})
    existing = jobs.get('content', [])
    if existing:
        job_id = existing[0]['id']
    else:
        job_id = call('/areaanalysis/1', body=payload).get('jobId')
    if not str(job_id).isdigit():
        raise ValueError('A TomTom não retornou um identificador válido para o relatório.')
    print(f'TomTom: aguardando relatório histórico {job_id}', flush=True)
    deadline = monotonic() + 20 * 60
    while True:
        status = call(f'/status/1/{job_id}')
        state = status.get('jobState')
        if state == 'DONE':
            url = next((link for link in status.get('urls', [])
                        if unquote(urlsplit(link).path).lower().endswith(('.geojson', '.geojson.gz'))), '')
            if urlsplit(url).scheme != 'https' or not urlsplit(url).hostname:
                raise ValueError('A TomTom não retornou um link HTTPS para o GeoJSON.')
            with request(url, timeout=90) as response:
                raw = response.read()
            return json.loads(gzip.decompress(raw) if raw.startswith(b'\x1f\x8b') else raw)
        if state not in PENDING:
            raise ValueError(f'TomTom: relatório {job_id} no estado {state}. Confira no MOVE ou use --traffic-stats.')
        if monotonic() >= deadline:
            raise ValueError(f'TomTom: relatório {job_id} ainda está em processamento. Execute novamente para retomá-lo.')
        sleep(15)


def monthly_report(config, first, last, imported):
    payload = report_request(config, first, last)
    cache = CACHE / 'tomtom' / (payload['jobName'].replace(' ', '-').lower() + '.geojson')
    path = imported or cache
    if path.is_file():
        date_id, time_ids = report_timesets(read_json(path), first, last)
    else:
        if imported:
            raise ValueError(f'Relatório TomTom não encontrado: {imported}')
        data = download_report(payload)
        date_id, time_ids = report_timesets(data, first, last)
        write_json(cache, data)
    return path, date_id, time_ids


def urbs_reference(first, last, bbox, selected=None):
    if selected and (not first <= selected <= last or selected.weekday() >= 5):
        raise ValueError('Escolha uma data URBS de segunda a sexta dentro do mês de referência.')
    days = [selected] if selected else [last - timedelta(days=i) for i in range((last-first).days + 1)]
    for day in days:
        if day.weekday() >= 5:
            continue
        catalog = [(day, kind) for kind in KINDS if kind != 'veiculos']
        gps = [(day, 'veiculos'), (day + timedelta(days=1), 'veiculos')]
        archives = fetch_urbs(catalog + gps)
        missing_catalog = [row for row in archives[:len(catalog)] if row['status'] == 'unavailable']
        gps_errors = [row for row in archives[len(catalog):] if row['status'] == 'unavailable']
        missing_gps = len(gps_errors) == len(gps)
        if missing_catalog or missing_gps:
            unavailable = missing_catalog + (gps_errors if missing_gps else [])
            error = next((row['error'] for row in unavailable if row['error'] != 'HTTP 404'), 'HTTP 404')
            if selected or error != 'HTTP 404':
                raise ValueError(f'URBS/C3SL: arquivos de {day:%d/%m/%Y} indisponíveis ({error}).')
            continue
        if all(gps_window(*window(day.isoformat(), peak), bbox)[0] for peak in PRESETS):
            return day
    raise ValueError(f'URBS/C3SL: sem GPS nos dois picos para o período {first:%d/%m/%Y} a {last:%d/%m/%Y}.')

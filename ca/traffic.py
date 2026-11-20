from collections import defaultdict
from datetime import datetime, timedelta
from math import isfinite
from statistics import mean, median

from .io import CACHE, envelope, read_json, utc
from .network import edge_observations

REFERENCE_STATS = 'data/tomtom/jobs_9420849_results_Curitiba.geojson'


def historical_stats(path, timeset=None, speed_field='harmonicAverageSpeed'):
    features = read_json(path)['features']
    metadata = next((f['properties'] for f in features if f['geometry'] is None), {})
    time_ids = {item['@id'] for item in metadata.get('timeSets', [])}
    if timeset is None and len(time_ids) > 1:
        raise ValueError('O relatório tem várias janelas. Escolha --stats-timeset pelo @id do relatório.')
    if timeset is not None and timeset not in time_ids:
        raise ValueError('O --stats-timeset informado não consta no relatório.')
    segments = []
    for feature in features:
        geom = feature['geometry']
        props = feature['properties']
        if not geom or geom['type'] != 'LineString':
            continue
        results = [r for r in props.get('segmentTimeResults', []) if timeset is None or r['timeSet'] == timeset]
        speeds = [r[speed_field] for r in results if r.get('sampleSize', 0) >= 5
                  and r.get(speed_field, 0) > 0]
        if not speeds or not props.get('speedLimit'):
            continue
        segments.append({'coordinates': geom['coordinates'], 'speed_kmh': mean(speeds),
                         'free_speed_kmh': props['speedLimit'], 'segment_id': props.get('segmentId')})
    return segments, metadata


def offline_observations(network, path, segments, metadata):
    edges = {}
    for edge_id, rows in edge_observations(network, segments, directional=True).items():
        weight = mean(min(10., max(1., r['free_speed_kmh']/r['speed_kmh'])) for r in rows)
        edges[edge_id] = {'target_speed_kmh': round(mean(r['speed_kmh'] for r in rows), 2),
                          'departure_weight': round(weight, 4), 'source': 'stats_offline_average'}
    if not edges:
        raise ValueError('TomTom: nenhum trecho do relatório offline foi associado à rede do quadrilátero.')
    return envelope('traffic.targets', mode='offline_report', edges=edges,
                    historic={'file': path.name, 'date_ranges': metadata['dateRanges'],
                              'time_sets': [row['name'] for row in metadata['timeSets']],
                              'mapped_edges': len(edges), 'segments': len(segments),
                              'statistic': 'averageSpeed'})


def demand_observations(network, stats, timeset, begin, end):
    history, metadata = historical_stats(stats, timeset) if stats else ([], {})
    matched = edge_observations(network, history, directional=True) if history else {}
    captures = []
    live = defaultdict(list)
    start_utc, end_utc = utc(begin), utc(end)
    for path in sorted((CACHE / 'tomtom').glob('flow-*.json')):
        data = read_json(path)
        records = data['observations']
        same_window = [r for r in records if start_utc <= r['observed_at'] < end_utc]
        captures.append({'file': path.name, 'observed_at': records[0]['observed_at'] if records else None,
                         'samples': len(records), 'samples_in_window': len(same_window)})
        confident = [r for r in same_window if r['confidence'] >= .7 and not r['closed'] and r['free_speed_kmh'] > 0]
        for edge_id, records in edge_observations(network, confident, directional=False).items():
            live[edge_id].extend(records)
    result = {}
    for edge_id in matched.keys() | live.keys():
        records = live.get(edge_id) or matched[edge_id]
        speed = mean(r['speed_kmh'] for r in records)
        free = mean(r['free_speed_kmh'] for r in records)
        result[edge_id] = {'target_speed_kmh': round(speed, 2), 'speed_ratio': min(1.0, speed/free),
                           'source': 'flow' if edge_id in live else 'stats'}
    return envelope('traffic.targets', edges=result, captures=captures, mode='mixed' if stats else 'live_only',
                    historic={'file': stats.name if stats else None, 'date_ranges': metadata.get('dateRanges'),
                              'time_sets': [t['name'] for t in metadata.get('timeSets', [])
                                            if timeset is None or t['@id'] == timeset],
                              'mapped_edges': len(matched), 'segments': len(history)},
                    live_edges=len(live))


def monthly_observations(network, path, date_id, time_id, first, last):
    segments = []
    for feature in read_json(path)['features']:
        geometry = feature.get('geometry')
        if not geometry or geometry['type'] != 'LineString':
            continue
        props = feature['properties']
        for row in props.get('segmentTimeResults', []):
            if (row.get('dateRange'), row.get('timeSet')) != (date_id, time_id):
                continue
            speed = row.get('medianSpeed')
            if (isinstance(speed, (int, float)) and isfinite(speed) and speed >= 0
                    and row.get('sampleSize', 5) >= 5 and row.get('normalizedSampleSize', 1) > 0):
                segments.append({'coordinates': geometry['coordinates'], 'speed_kmh': speed})
    edges = {}
    for edge_id, rows in edge_observations(network, segments, directional=True).items():
        speed = median(r['speed_kmh'] for r in rows)
        free = network.edges[edge_id].getSpeed() * 3.6
        if free > 0:
            edges[edge_id] = {'target_speed_kmh': round(speed, 2), 'speed_ratio': min(1., speed/free),
                              'source': 'stats_monthly_median', 'matched_segments': len(rows)}
    if not edges:
        raise ValueError('TomTom: nenhuma velocidade mediana da janela selecionada foi associada à rede do quadrilátero.')
    return envelope('traffic.targets', mode='monthly_median', edges=edges,
                    historic={'file': path.name, 'date_ranges': [{'from': first.isoformat(), 'to': last.isoformat()}],
                              'time_set_id': time_id, 'mapped_edges': len(edges), 'segments': len(segments),
                              'statistic': 'medianSpeed'})


def hourly_shape(path, begin, end):
    if not path.is_file():
        return {}
    props = read_json(path)['features'][0]['properties']
    values = defaultdict(list)
    for row in props['timedData']['hourly']:
        if row['v'] > 0:
            values[datetime.fromisoformat(row['time']).hour].append(max(row['c'], 0.0))
    result = {hour: 1 + mean(samples)/100 for hour, samples in values.items()}
    cursor = begin
    integral = 0.0
    while cursor < end:
        limit = min(end, cursor.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
        integral += result.get(cursor.hour, 1.0) * (limit - cursor).total_seconds()
        cursor = limit
    average = integral / (end - begin).total_seconds()
    return {hour: result.get(hour, 1.0)/average for hour in range(24)}

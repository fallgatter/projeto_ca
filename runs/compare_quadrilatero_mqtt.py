import json
import sys
from statistics import mean
from xml.etree.ElementTree import parse

from ca.results import RunResults


store = RunResults()
wave = {p.get('id') for p in parse('config/signals/onda-verde-kennedy.add.xml').findall('tlLogic')}
integrated = '--kennedy' in sys.argv
for seed in (42, 73):
    for peak, duration in [('manha', 9000), ('tarde', 7200)]:
        suffix = '-s73' if seed == 73 else ''
        run = f'quadrilatero-{peak}-mqtt{suffix}'
        if integrated:
            run = f'kennedy-integrada-{peak}-mqtt-s{seed}'
        if store.data(run, 'status.json')['state'] != 'complete':
            continue
        comparison = store.signal_comparison(run)
        assert comparison is not None
        fixed = comparison['baseline_run']
        ids = [fixed, run]
        metadata = [store.data(i, 'metadata.json') for i in ids]
        assert metadata[0]['inputs_sha256'] == metadata[1]['inputs_sha256']
        assert all(m['seed'] == seed and m['duration_s'] == duration for m in metadata)
        summaries = [store.data(i, 'summary.json') for i in ids]
        assert all(s['totals']['duration_s'] == duration for s in summaries)
        nodes = store.data(run, 'map.json')['intersections']
        corridor = {n for n, x in nodes.items() if wave.intersection(x['signal_ids'])}
        assert len(corridor) == 8
        matched = []
        for i, s in zip(ids, summaries):
            teleported = set(s['teleported_ids']) if 'teleported_ids' in s else set()
            if 'teleported_ids' not in s:
                import re
                log = (store.path(i) / 'sumo-errors.log').read_text(encoding='utf-8')
                teleported = set(re.findall(r"Teleporting vehicle '([^']+)'", log))
            trips = parse(store.path(i) / 'trips.xml').findall('tripinfo')
            matched.append({t.get('id'): float(t.get('timeLoss')) for t in trips
                            if t.get('id').startswith(('car-', 'bus-')) and t.get('id') not in teleported})
        shared = sorted(matched[0].keys() & matched[1].keys())
        result = {}
        for trip, s, label in zip(matched, summaries, ['baseline', 'adaptive']):
            result[label] = {**comparison[label], 'matched_motor_n': len(shared),
                             'matched_motor_delay': mean(trip[i] for i in shared),
                             'kennedy_peak_m': max(s['totals']['intersections'].get(n, {}).get('peak_queue_m', 0)
                                                   for n in corridor)}
        stats = summaries[1]['signal_control']
        assert (stats['mqtt_batches'] > stats.get('mqtt_missed_batches', 0)
                and stats['green_adjustments'] == stats['mqtt_extensions'] + stats['mqtt_shortenings'])
        if integrated:
            assert set(stats['kennedy_signals']) == wave
            assert all(item['observations'] and item['max_abs_offset_s'] <= 4
                       for item in stats['kennedy_signals'].values())
            assert any(item['shortenings'] + item['extensions'] for item in stats['kennedy_signals'].values())
            archived = f'quadrilatero-{peak}-mqtt{suffix}'
            old_comparison = store.signal_comparison(archived)
            assert old_comparison['baseline_run'] == fixed
            result['kennedy_fixed_mqtt'] = old_comparison['adaptive']
            old = store.data(archived, 'summary.json')
            result['kennedy_fixed_mqtt']['kennedy_peak_m'] = max(
                old['totals']['intersections'].get(n, {}).get('peak_queue_m', 0) for n in corridor)
        result['control'] = stats
        print(peak, seed, fixed, run, json.dumps(result))

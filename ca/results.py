import json
import re
from datetime import datetime, timedelta
from functools import lru_cache
from statistics import mean
from threading import Lock
from xml.etree.ElementTree import iterparse

from .io import CACHE, LOCAL, ROOT, envelope, read_json
from .metrics import pedestrian_trip_info, signal_kpis, window_summary


def optional_json(path, default=None):
    return read_json(path) if path.exists() else default


@lru_cache(maxsize=24)
def static_json(path, version):
    return read_json(path)


@lru_cache(maxsize=24)
def saved_pedestrian_trips(path, version):
    return pedestrian_trip_info(path)


@lru_cache(maxsize=24)
def brt_trip_losses(path, version, bus_ids):
    losses = {}
    for _, item in iterparse(path):
        actor = item.get('id')
        if item.tag == 'tripinfo' and actor in bus_ids and not item.get('vaporized'):
            losses[actor] = float(item.get('timeLoss'))
        item.clear()
    return losses


@lru_cache(maxsize=24)
def car_trip_metrics(path, version):
    trips = {}
    for _, item in iterparse(path):
        actor = item.get('id', '')
        if item.tag == 'tripinfo' and actor.startswith('car-') and not item.get('vaporized'):
            if float(item.get('arrival')) >= 0:
                trips[actor] = (float(item.get('waitingTime')), int(item.get('waitingCount')),
                                float(item.get('duration')))
        item.clear()
    return trips


class RunResults:
    def __init__(self, folder=ROOT / 'runs'):
        self.folder = folder
        self.lock = Lock()
        self.streams = {}

    def path(self, run):
        if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,69}', run or ''):
            raise KeyError(run)
        path = self.folder / run
        if not (path/'status.json').is_file():
            raise KeyError(run)
        return path

    def listing(self):
        result = []
        for path in sorted(self.folder.glob('*/status.json'), key=lambda p: p.stat().st_mtime, reverse=True):
            meta = optional_json(path.parent/'metadata.json')
            state = optional_json(path, {}).get('state')
            result.append({'id': path.parent.name, 'state': state, 'metadata': meta})
        return result

    def data(self, run, name, default=None):
        path = self.path(run) / name
        return static_json(path, path.stat().st_mtime_ns) if path.is_file() else default

    def frames(self, run, name='frames.jsonl'):
        path = self.path(run) / name
        if not path.is_file():
            return ()
        with self.lock, path.open('rb') as stream:
            stat = path.stat()
            identity = stat.st_dev, stat.st_ino
            if path not in self.streams or self.streams[path][0] != identity or stat.st_size < self.streams[path][1]:
                self.streams[path] = (identity, 0, [])
            _, offset, frames = self.streams[path]
            stream.seek(offset)
            for line in stream:
                if not line.endswith(b'\n'):
                    break
                frames.append(json.loads(line))
                offset += len(line)
            self.streams[path] = (identity, offset, frames)
            return tuple(frames)

    def signal_comparison(self, run):
        metadata = self.data(run, 'metadata.json')
        hashes = metadata.get('inputs_sha256') if metadata else None
        source = metadata.get('reference_run') if metadata else None
        if not hashes or not source:
            return None
        strategy = metadata['signal_control']['strategy']
        eco = metadata.get('eco_approach', {})
        if strategy == 'fixed' and not eco.get('baseline_run'):
            return None
        selected = self.data(run, 'summary.json')
        if not selected or self.data(run, 'status.json')['state'] != 'complete':
            return None
        baseline_id = None
        for entry in self.listing():
            if entry['state'] != 'complete':
                continue
            meta = entry['metadata'] or {}
            same_fixed_inputs = (meta.get('reference_run') == source and meta.get('inputs_sha256') == hashes
                                 and meta.get('signal_control', {}).get('strategy') == 'fixed'
                                 and meta.get('eco_approach', {}).get('demand_sha256') == eco.get('demand_sha256'))
            if entry['id'] == eco.get('baseline_run') or (strategy != 'fixed' and same_fixed_inputs):
                baseline_id = entry['id']
                break
        if baseline_id is None:
            return None
        baseline = self.data(baseline_id, 'summary.json')
        receivers = self.data(run, 'map.json')['intersections'].keys() & self.data(baseline_id, 'map.json')['intersections'].keys()

        def kpis(summary, run_id):
            path = self.path(run_id) / 'trips.xml'
            pedestrians = (saved_pedestrian_trips(path, path.stat().st_mtime_ns)
                           if 'pedestrians' not in summary and path.is_file() else None)
            return signal_kpis(summary, receivers, pedestrians)

        before, after = kpis(baseline, baseline_id), kpis(selected, run)
        lines = selected.get('signal_control', {}).get('brt_lines', ())
        journeys = self.data(run, 'bus-journeys.json', {}).get('journeys', ())
        brt_ids = {item['id'] for item in journeys if item['line_id'] in lines}
        base_trips = self.brt_delays(baseline_id, baseline, brt_ids)
        test_trips = self.brt_delays(run, selected, brt_ids)
        shared = base_trips.keys() & test_trips.keys()
        for metrics, trips in ((before, base_trips), (after, test_trips)):
            metrics['brt_matched'] = len(shared)
            metrics['brt_matched_delay_s'] = mean(trips[actor] for actor in shared) if shared else None
        if eco:
            def car_trips(run_id, summary):
                folder = self.path(run_id)
                path = folder / 'trips.xml'
                teleported = self.teleported_ids(folder, summary)
                if teleported is None or not path.is_file():
                    return set(), {}
                trips = car_trip_metrics(path, path.stat().st_mtime_ns)
                return trips.keys() - teleported, trips

            base_ids, base_car_trips = car_trips(baseline_id, baseline)
            test_ids, test_car_trips = car_trips(run, selected)
            shared_cars = base_ids & test_ids
            for metrics, trips in ((before, base_car_trips), (after, test_car_trips)):
                metrics['car_matched'] = len(shared_cars)
                metrics['car_matched_stopped_s'] = mean(trips[actor][0] for actor in shared_cars) if shared_cars else None
                metrics['car_matched_stop_count'] = mean(trips[actor][1] for actor in shared_cars) if shared_cars else None
                metrics['car_matched_travel_s'] = mean(trips[actor][2] for actor in shared_cars) if shared_cars else None
        return envelope('signal.comparison', run_id=run, baseline_run=baseline_id,
                        strategy=strategy, eco_approach=bool(eco), receivers=len(receivers),
                        baseline=before, adaptive=after)

    def brt_delays(self, run, summary, brt_ids):
        folder = self.path(run)
        trips = folder / 'trips.xml'
        if not brt_ids or not trips.is_file():
            return {}
        teleported = self.teleported_ids(folder, summary)
        if teleported is None:
            return {}
        return brt_trip_losses(trips, trips.stat().st_mtime_ns, frozenset(brt_ids.difference(teleported)))

    @staticmethod
    def teleported_ids(folder, summary):
        teleported = summary.get('teleported_ids')
        if teleported is not None:
            return teleported
        log = folder / 'sumo-errors.log'
        if log.is_file():
            return re.findall(r"Teleporting vehicle '([^']+)'", log.read_text(encoding='utf-8', errors='replace'))
        return None


def local_start(metadata):
    return datetime.fromisoformat(metadata['start']).astimezone(LOCAL)


def period(metadata, bounds):
    start = local_start(metadata)
    stamps = (start+timedelta(seconds=s) for s in bounds)
    return '–'.join(t.strftime('%H:%M:%S' if t.second else '%H:%M') for t in stamps)


def slice_frames(frames, start, end):
    return [f for f in frames if f['start_s'] >= start and f['end_s'] <= end]


def current_capture():
    paths = sorted((CACHE/'tomtom').glob('flow-*.json'))
    if paths:
        path = paths[-1]
        return static_json(path, path.stat().st_mtime_ns)
    return envelope('tomtom.flow', observations=[], errors=[])


def summary_payload(run, frames, start, end):
    return envelope('window.summary', run_id=run, start_s=start, end_s=end,
                    **window_summary(slice_frames(frames, start, end)))

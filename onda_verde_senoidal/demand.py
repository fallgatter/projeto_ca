from collections import Counter, defaultdict
from itertools import pairwise
from math import ceil
from random import Random
from statistics import quantiles
from xml.etree import ElementTree as ET


def stagger_cars(root, duration, seed, interval):
    """Reschedule cars within each origin and preserve its demand in every block."""
    groups = defaultdict(list)
    for car in root.findall('vehicle'):
        departure = float(car.get('depart'))
        if not car.get('id').startswith('car-') or not 0 <= departure < duration:
            continue
        origin = car.find('route').get('edges').split()[0]
        groups[origin, int(departure)//interval].append(car)
        if car.get('departPos') is not None:
            # These routes enter at the observed boundary. SUMO can lower speed
            # at insertion to maintain safe gaps or respect an intersection.
            car.set('departSpeed', 'max')
    rng = Random(seed)
    schedules = defaultdict(list)
    by_origin = defaultdict(list)
    for (origin, block), cars in sorted(groups.items()):
        start = block*interval
        spacing = (min(duration, start+interval)-start)/len(cars)
        phase = rng.random()
        times = sorted(start+int(spacing*((index+phase+rng.uniform(-.25,.25)) % len(cars)))
                       for index in range(len(cars)))
        for car, departure in zip(cars, times):
            item = Departure(car, origin, departure)
            schedules[block].append(item)
            by_origin[origin].append(item)
    for block, items in sorted(schedules.items()):
        balance_slots(items, by_origin, block*interval, min(duration, (block+1)*interval))
        for item in items:
            item.car.set('depart', str(item.second))


class Departure:
    def __init__(self, car, origin, second):
        self.car = car
        self.origin = origin
        self.second = second


def balance_slots(items, by_origin, start, end):
    """Move departures by at most 8 s to reduce extreme 5 s counts."""
    step = 5
    slots = [[] for _ in range(ceil((end-start)/step))]
    for item in items:
        slots[(item.second-start)//step].append(item)
    limit = ceil(2*len(items)/len(slots))
    moved = set()
    for index, target in sorted(enumerate(slots), key=lambda pair: (len(pair[1]), pair[0])):
        if len(target) >= limit:
            continue
        lo, hi = start+index*step, min(end, start+(index+1)*step)-1
        neighbors = range(max(0,index-2), min(len(slots),index+3))
        for neighbor in sorted(neighbors, key=lambda j: (-len(slots[j]), abs(index-j), j)):
            donor = slots[neighbor]
            if not (len(donor) > limit or (not target and len(donor) >= 3)):
                continue
            for item in sorted(donor, key=lambda d: abs(d.second-max(lo,min(hi,d.second)))):
                proposed = max(lo,min(hi,item.second))
                if item in moved or abs(proposed-item.second) > 8 or any(
                        other is not item and abs(proposed-other.second) < 3 for other in by_origin[item.origin]):
                    continue
                donor.remove(item)
                target.append(item)
                item.second = proposed
                moved.add(item)
                break
            else:
                continue
            break


def departure_audit(original, refined, duration):
    """Compare scheduled and actual departures at the same ten busiest origins."""
    def read(folder):
        cars = {car.get('id'): (float(car.get('depart')), car.find('route').get('edges').split()[0])
                for car in ET.parse(folder/'demand.rou.xml').getroot().findall('vehicle')
                if car.get('id').startswith('car-') and 0 <= float(car.get('depart')) < duration}
        actual = {}
        for _, trip in ET.iterparse(folder/'trips.xml', events=('end',)):
            if trip.tag == 'tripinfo':
                actor = trip.get('id')
                if actor in cars and 0 <= float(trip.get('depart')) < duration:
                    actual[actor] = float(trip.get('depart'))
                trip.clear()
        return cars, actual

    runs = [read(folder) for folder in (original, refined)]
    leaders = {edge for edge, _ in Counter(edge for _, edge in runs[0][0].values()).most_common(10)}
    results = []
    for cars, actual in runs:
        def describe(times):
            origins = defaultdict(list)
            for car, timestamp in times.items():
                origin = cars[car][1]
                if origin in leaders:
                    origins[origin].append(timestamp)
            headways = [b-a for origin_times in origins.values() for a,b in pairwise(sorted(origin_times))]
            p90 = quantiles(headways, n=10, method='inclusive')[-1] if len(headways) > 1 else next(iter(headways), None)
            return dict(gaps=len(headways), short=sum(t < 5 for t in headways),
                        long=sum(t > 120 for t in headways), p90=p90)
        buckets = Counter(int(t)//5 for t in actual.values())
        results.append(dict(scheduled=describe({car:t for car,(t,_) in cars.items()}), actual=describe(actual),
                            empty_5s=(duration+4)//5-len(buckets), max_5s=max(buckets.values(), default=0),
                            inserted=len(actual), total=len(cars),
                            delayed_2s=sum(t-cars[car][0] > 2 for car,t in actual.items())))
    return results

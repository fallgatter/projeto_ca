import json
from collections import Counter, defaultdict, deque
from hashlib import sha256
from math import hypot
from threading import Condition, Event
from typing import NamedTuple
from uuid import uuid4

from paho.mqtt.client import CallbackAPIVersion, Client, MQTTv5

from .io import read_json

from .flow import WINDOW_MINUTES, persistent_error
from .fourier import predict
from .network import green
from .simulate import WARMUP


EXCHANGE = 15
UPDATE = 60
MIN_GREEN = 10
HORIZON = 45
DECISION = 5
DETECTOR_METERS = 160

class PredictiveSettings(NamedTuple):
    corridor_weight: float
    queue_weight: float
    protected_radius: int
    split_range: int
    future_green: int
    discharge_headway: float = 2.
    startup_loss: float = 0.
    preserve_corridors: bool = False
    bus_weight: float = 0.
    reconcile_forecasts: bool = False
    actuated_gap: int = 0
    reserve_queues: float = 0.


VARIANTS = {
    'pressao': PredictiveSettings(1.5, 2.0, 130, 8, 30),
    'progressao': PredictiveSettings(2.5, 1.4, 160, 8, 35, preserve_corridors=True),
    'filas': PredictiveSettings(2.0, 3.5, 110, 10, 25),
    'descarga': PredictiveSettings(2.0, 2.3, 110, 10, 32, 2.7, 1.5),
    'arteriais': PredictiveSettings(3.5, 1.9, 90, 10, 27, 2.6, 1.5),
    'prioridade': PredictiveSettings(2.4, 3.3, 110, 10, 25, 2.6, 1.5,
                                    bus_weight=.75, reconcile_forecasts=True),
    'sincronia': PredictiveSettings(2.8, 2.3, 155, 12, 30, 2.6, 1.5,
                                   preserve_corridors=True, bus_weight=.9, reconcile_forecasts=True),
    'atuado': PredictiveSettings(1.9, 1.4, 105, 10, 24, 2.6, 1.3, bus_weight=.75,
                                reconcile_forecasts=True, actuated_gap=5),
    'atuado_prioritario': PredictiveSettings(2.8, 2.4, 130, 12, 24, 2.5, 1.3,
                                            preserve_corridors=True, bus_weight=1.,
                                            reconcile_forecasts=True, actuated_gap=6),
    'reservas': PredictiveSettings(1.9, 1.4, 105, 10, 24, 2.6, 1.3, bus_weight=.75,
                                  reconcile_forecasts=True, actuated_gap=5, reserve_queues=4.0),
    'reservas_ciclo': PredictiveSettings(2.8, 2.4, 130, 12, 24, 2.5, 1.3,
                                        preserve_corridors=True, bus_weight=1.,
                                        reconcile_forecasts=True, actuated_gap=6, reserve_queues=6.0),
}


class MqttPeers:
    """Each traffic light owns a client and receives publications addressed to it."""

    def __init__(self, address, active):
        host, _, port = address.partition(':')
        if host not in {'127.0.0.1', 'localhost'}:
            raise ValueError('Use um broker MQTT local.')
        self.prefix = f'curitiba/senoidal/{uuid4().hex[:12]}'
        self.cv = Condition()
        self.pending = {}
        self.received = {}
        self.clients = {}
        self.published = self.delivered = 0
        try:
            for signal in sorted(active):
                ready = Event()
                client = Client(CallbackAPIVersion.VERSION2, protocol=MQTTv5,
                                client_id=f'{self.prefix.rsplit("/", 1)[-1]}-{signal}')

                def subscribe(connection, _, flags, code, properties, signal=signal):
                    if not code.is_failure:
                        connection.subscribe(f'{self.prefix}/{signal}')

                def subscribed(connection, _, mid, codes, properties, ready=ready):
                    if codes and not any(code.is_failure for code in codes):
                        ready.set()

                def message(connection, _, packet, signal=signal):
                    if packet.retain or len(packet.payload) > 32768:
                        return
                    try:
                        data = json.loads(packet.payload)
                        key = (signal, data['from'])
                        with self.cv:
                            if self.pending.get(key) == data and key not in self.received:
                                self.received[key] = {**data, 'topic': packet.topic}
                                self.cv.notify_all()
                    except (ValueError, TypeError, KeyError, RecursionError):
                        return

                client.on_connect = subscribe
                client.on_subscribe = subscribed
                client.on_message = message
                client.connect(host, int(port or 1885))
                self.clients[signal] = client
                client.loop_start()
                if not ready.wait(5):
                    raise RuntimeError(f'O broker MQTT não confirmou a assinatura de {signal}.')
        except BaseException:
            self.close()
            raise

    def exchange(self, now, payloads):
        with self.cv:
            self.received.clear()
            self.pending = {(target, sender): dict(kind='mqtt', s=now, to=target, flows=flows, **{'from': sender})
                            for (sender, target), flows in payloads.items()}
            self.published += len(self.pending)
            expected = 0
            for (target, sender), data in self.pending.items():
                info = self.clients[sender].publish(f'{self.prefix}/{target}',
                                                    json.dumps(data, separators=(',', ':')))
                expected += info.rc == 0
            self.cv.wait_for(lambda: len(self.received) >= expected, timeout=.35)
            received = [self.received[key] for key in sorted(self.received)]
            self.delivered += len(received)
            self.pending = {}
            return received

    def close(self):
        for client in self.clients.values():
            client.disconnect()
            client.loop_stop()


class Controller:
    def __init__(self, connection, network, phases, watched, start, model_file, address, coordinated=False,
                 monitor=False, review=False, variant=None, queue_targets=None):
        self.tls = connection.trafficlight
        self.start = start
        self.model = read_json(model_file)
        self.model_hash = sha256(model_file.read_bytes()).hexdigest()
        self.fourier = self.model['approaches']
        self.phases = phases
        self.active = {}
        self.last_phase = {}
        self.actions = Counter()
        self.updates = 0
        self.arrivals = defaultdict(dict)
        self.residual = {}
        self.age_start = {}
        self.open_edges = {}
        self.capacity = {}
        self.decisions = 0
        self.rate = {}
        self.coordinated = coordinated
        self.variant = variant
        self.settings = VARIANTS.get(variant)
        self.corridor = set().union(*network.corridor_edges.values())
        self.brt = network.corridor_edges['sete']
        self.queue_targets = {}
        if self.settings and self.settings.reserve_queues and queue_targets:
            self.queue_targets = {edge: max(20., queue_targets['rede']) for edge in network.edges}
            for key, edges in network.corridor_edges.items():
                for edge in edges:
                    self.queue_targets[edge] = max(20., queue_targets[key])
        self.lengths = {edge: road.getLength() for edge, road in network.edges.items()}
        self.anchor = {}
        self.split = {}
        self.exits = defaultdict(set)
        self.storage = {}
        self.spill = {}
        self.pedestrian_phases = defaultdict(set)
        for signal in sorted(watched):
            groups, lanes = network.signals[signal]
            stages = phases[signal]
            service = [frozenset(edge for edge, indexes in groups.items() if green(state, indexes))
                       for _, state in stages]
            adjustable = {i for i, (nominal, state) in enumerate(stages)
                          if nominal >= MIN_GREEN and service[i] and not any(c in 'yYuU' for c in state)}
            if len({service[i] for i in adjustable}) < 2:
                continue
            self.active[signal] = adjustable
            self.open_edges[signal] = service
            for edge, _, _ in lanes.values():
                self.capacity[signal, edge] = self.capacity.get((signal, edge), 0) + 1
        peers = set(self.active).intersection(set().union(*network.corridor_lights.values()))
        self.routes = network.neighbors(peers)
        self.inputs = {signal: set(network.signals[signal][0]) for signal in self.active}
        if coordinated:
            spine = [network.points[s] for s in network.corridor_lights['sete']]
            radius = self.settings.protected_radius if self.settings else 240
            preserve = self.settings and self.settings.preserve_corridors
            anchor_edges = self.corridor if preserve else self.brt
            for signal, allowed in self.active.items():
                x, y = network.points[signal]
                if (preserve and self.inputs[signal] & anchor_edges
                        or any(hypot(x-a, y-b) <= radius for a, b in spine)):
                    self.anchor[signal] = max(sorted(allowed), key=lambda i: (
                        len(self.open_edges[signal][i] & anchor_edges), phases[signal][i][0]))
            for tls in network.net.getTrafficLights():
                signal = tls.getID()
                if signal not in self.active:
                    continue
                for src, dest, idx in tls.getConnections():
                    edge, out = src.getEdge().getID(), dest.getEdge().getID()
                    if edge in self.inputs[signal] and out in network.edges:
                        self.exits[signal, edge].add(out)
                        lanes = sum(l.allows('passenger') or l.allows('bus') for l in network.edges[out].getLanes())
                        self.storage[out] = max(1., network.edges[out].getLength()*lanes/7.5)
                    if dest.getEdge().getFunction() == 'crossing':
                        self.pedestrian_phases[signal].update(
                            i for i, (_, state) in enumerate(phases[signal]) if green(state, (idx,)))
        self.bus = MqttPeers(address, peers)
        self.monitor_signals = peers if monitor else set()
        self.measurements = {}
        self.measurements_by_mode = {}
        self.flow_windows = defaultdict(lambda: deque(maxlen=WINDOW_MINUTES)) if review else None
        self.flow_corrections = {}
        self.diagnostics = {}
        from .io import sumo_modules
        self.switch_var = sumo_modules()[1].constants.TL_NEXT_SWITCH

    def step(self, now, lights, phase_var, approaches, arrivals, departures, stopped_stock, arrivals_by_mode,
             queue_lengths=None, approaching_buses=None):
        events = []
        if now % EXCHANGE == 0:
            packets = defaultdict(list)
            for (old, eid), count in departures.items():
                routes = [entry for entry in self.routes[eid] if old in self.inputs[entry[0]]]
                for sender, target, approach, seconds in routes:
                    packets[sender, target].append([approach, round(count/len(routes), 2), now+seconds])
            for event in self.bus.exchange(now, packets):
                for edge, count, eta in event['flows']:
                    key = (edge, event['from'], eta)
                    existing = self.arrivals[event['to']].get(key, 0.)
                    self.arrivals[event['to']][key] = existing + count
                events.append(event)
            departures.clear()
        if now % UPDATE == 0:
            for edge, coef in self.fourier.items():
                observed = arrivals[edge]
                nominal = predict(coef, self.start+now-UPDATE/2)
                error = observed * 3600 / UPDATE - nominal
                if self.flow_windows is not None:
                    counts = self.flow_windows[edge]
                    counts.append((observed, nominal*UPDATE/3600))
                    total, expected, tolerance, error = persistent_error(counts)
                    self.flow_corrections[edge] = [len(counts), total, expected, tolerance, error]
                self.residual[edge] = .80*self.residual.get(edge, 0.) + .20*error
                self.updates += 1
                self.rate[edge] = max(0., predict(coef, self.start+now+HORIZON/2)
                                      + self.residual[edge])/3600
                if self.monitor_signals:
                    self.measurements[edge] = observed * 3600 / UPDATE
                    self.measurements_by_mode[edge] = [mode[edge] for mode in arrivals_by_mode]
            arrivals.clear()
            for mode in arrivals_by_mode:
                mode.clear()
        if self.coordinated and now % DECISION == 0:
            self.spill = {eid: min(1., count/self.storage[eid]) for eid,count in stopped_stock.items() if eid in self.storage}
        for signal, allowed in self.active.items():
            observation = lights.get(signal, {})
            phase = observation.get(phase_var)
            if phase is None:
                continue
            changed = phase != self.last_phase.get(signal)
            if changed:
                self.last_phase[signal] = phase
                self.age_start[signal] = now
            protected = signal in self.anchor
            actuated = self.settings and self.settings.actuated_gap
            cadence = 2 if actuated else DECISION
            if now < WARMUP or phase not in allowed or (not changed if protected else now % cadence):
                continue
            packets = self.arrivals.get(signal)
            if packets:
                self.arrivals[signal] = {k: v for k, v in packets.items() if k[2] >= now}
            present = {edge: approaches[edge] for edge in self.inputs[signal] if edge in approaches}
            queues = {edge: queue_lengths[edge] for edge in self.inputs[signal]
                      if queue_lengths and edge in queue_lengths}
            if not protected and not present and not self.arrivals.get(signal) and not queues:
                continue
            age = now - self.age_start[signal]
            remaining = round(observation[self.switch_var]-now)
            minimum = 7 if actuated and phase not in self.pedestrian_phases[signal] else MIN_GREEN
            if (not protected and age < minimum) or remaining < 1:
                continue
            if protected:
                if phase == self.anchor[signal]:
                    partners = sorted(allowed - {phase})
                    partner = max(partners, key=lambda i: self.phases[signal][i][0])
                    planned = self.choose(signal, phase, age, remaining, present, now, partner, queues,
                                          approaching_buses, queue_lengths)
                    self.split[signal] = {phase: planned-remaining, partner: remaining-planned}
                selected = remaining + self.split.get(signal, {}).pop(phase, 0)
            else:
                selected = self.choose(signal, phase, age, remaining, present, now, queues=queues,
                                       approaching_buses=approaching_buses, network_queues=queue_lengths)
            if selected != remaining:
                self.tls.setPhaseDuration(signal, selected)
                self.actions[signal] += 1
                events.append(dict(kind='action', s=now, signal=signal, phase=phase, delta=selected-remaining))
        return events

    def choose(self, signal, phase, age, remaining, present, now, partner=None, queues=None, approaching_buses=None,
               network_queues=None):
        """Evaluate green-end candidates by predicted vehicle-seconds waiting."""
        stages = self.phases[signal]
        latest = max(1, stages[phase][0] + 15 - age)
        candidates = sorted({remaining, 1, min(6, latest), min(15, latest), min(25, latest)})
        if self.settings:
            candidates = sorted({remaining, 1, min(5, latest), min(10, latest), min(18, latest),
                                 min(25, latest), min(max(1, remaining+5), latest)})
        if partner is not None:
            span = self.settings.split_range if self.settings else 4
            candidates = [remaining+d for d in (-span, -span//2, 0, span//2, span)
                          if remaining+d >= MIN_GREEN and stages[partner][0]-d >= MIN_GREEN]
            if not self.settings:
                candidates = [green for green in candidates if abs(green-remaining) in (0, 4)]
            if remaining not in candidates:
                candidates.append(remaining)
        arrivals = defaultdict(list)
        for edge, times in present.items():
            arrivals[edge].extend((t, 1.) for t in times if t <= HORIZON)
        priority = {}
        if self.settings:
            for edge, length in (queues or {}).items():
                outside = max(0., length-min(DETECTOR_METERS, self.lengths[edge]))
                if outside:
                    arrivals[edge].append((0, min(30., outside/7.5)))
            for edge in self.inputs[signal]:
                pressure = min(1.75, (queues or {}).get(edge, 0.)/max(35., self.lengths[edge]))
                preference = self.settings.corridor_weight if edge in self.corridor else 1.
                priority[edge] = preference + self.settings.queue_weight*pressure
                if self.settings.bus_weight and edge in self.brt:
                    priority[edge] += self.settings.bus_weight*min(4, (approaching_buses or {}).get(edge, 0))
                if edge in self.queue_targets:
                    fraction = (queues or {}).get(edge, 0.)/self.queue_targets[edge]
                    priority[edge] += self.settings.reserve_queues*min(2., fraction)**2
        for (edge, _, eta), count in self.arrivals.get(signal, {}).items():
            if now <= eta <= now+HORIZON and eta-now > 3:
                forecast = .65*count
                if self.settings and self.settings.reconcile_forecasts:
                    detected = sum(abs(time-(eta-now)) <= 4 for time in present.get(edge, ()))
                    forecast = max(0., forecast-detected)
                if forecast:
                    arrivals[edge].append((eta-now, forecast))
        for edge in self.inputs[signal]:
            rate = self.rate.get(edge, 0.)
            if rate > .003:
                for t in (25, 35, 45):
                    expected = 10*rate
                    if self.settings and self.settings.reconcile_forecasts:
                        expected -= sum(count for eta, count in arrivals.get(edge, ()) if t-5 < eta <= t+5)
                    if expected > 0:
                        arrivals[edge].append((t, expected))
        for queue in arrivals.values():
            queue.sort()
        service = self.open_edges[signal]
        gap_out = False
        if self.settings and self.settings.actuated_gap and partner is None:
            crossing_waits = sum(t <= 5 for e, ts in present.items() if e not in service[phase] for t in ts)
            soon = self.settings.actuated_gap
            gap_out = crossing_waits >= 1 and not any(
                eta <= soon and count >= .5
                for edge in service[phase] for eta, count in arrivals.get(edge, ()))
        clearance_horizon = HORIZON + sum(duration for duration, _ in stages)
        blocked_until = {}
        spill_risk = {}
        if self.coordinated:
            for edge in arrivals:
                exits = self.exits.get((signal,edge), ())
                if exits:
                    density = sum(self.spill.get(e,0.) for e in exits)/len(exits)
                    blocked_until[edge] = min(35., max(0., density-.45)*65)
                    if self.queue_targets:
                        occupancies = [max(self.spill.get(out, 0.),
                                           (network_queues or {}).get(out, 0.)/self.queue_targets[out])
                                       for out in exits]
                        spill_risk[edge] = max(0., sum(occupancies)/len(exits)-.4)

        def cost(first_green):
            windows = defaultdict(list)
            begin, step = 0, phase
            while begin < clearance_horizon:
                length = first_green if begin == 0 else stages[step][0]
                if begin and step == partner:
                    length += remaining-first_green
                elif begin and partner is None and step in self.active[signal]:
                    length = min(length, self.settings.future_green if self.settings else 22)
                for edge in service[step] & arrivals.keys():
                    startup = self.settings.startup_loss if self.settings and begin else 0.
                    windows[edge].append((max(begin+startup, blocked_until.get(edge, 0)), begin+length))
                begin += length
                step = (step+1) % len(stages)
            delay = 0.
            for edge, arrivals_at_edge in arrivals.items():
                slots = windows[edge]
                headway = self.settings.discharge_headway if self.settings else 2.
                spacing = headway / self.capacity[signal, edge]
                available, index = 0., 0
                for eta, count in arrivals_at_edge:
                    first = max(eta, available)
                    while index < len(slots) and max(first, slots[index][0])+spacing*count > slots[index][1]:
                        index += 1
                    departure = max(first, slots[index][0]) if index < len(slots) else max(first, clearance_horizon)
                    available = departure + spacing*count
                    delay += priority.get(edge, 1.) * count * (departure-eta)
                    if departure < first_green and edge in spill_risk:
                        delay += self.settings.reserve_queues*8*spill_risk[edge]*count
            gap_cost = first_green*min(5, crossing_waits) if gap_out else 0.
            return delay + gap_cost + (.35 if self.settings else .07)*abs(first_green-remaining)
        scores = {t: cost(t) for t in candidates}
        self.decisions += 1
        best = min(candidates, key=lambda t: (scores[t], abs(t-remaining)))
        if signal in self.monitor_signals:
            self.diagnostics[signal] = dict(second=now, phase=phase, remaining=remaining, selected=best,
                                            partner=partner, costs=sorted(scores.items()),
                                            approaches=[
                                                dict(edge=edge, detected=sum(t <= HORIZON for t in present.get(edge, ())),
                                                     stopped=sum(t == 0 for t in present.get(edge, ())),
                                                     mqtt=sum(count for (e, _, eta), count in self.arrivals.get(signal, {}).items()
                                                              if e == edge and now+3 < eta <= now+HORIZON),
                                                     blocked=blocked_until.get(edge, 0))
                                                for edge in sorted(self.inputs[signal])])
        return best

    def summary(self):
        cadence = 2 if self.settings and self.settings.actuated_gap else DECISION
        return dict(policy="mpc", coordinated=self.coordinated, anchored=len(self.anchor), horizon_s=HORIZON, decision_s=cadence, forecasts=self.decisions,
                    variant=self.variant,
                    mqtt_peers=len(self.bus.clients), eligible=sorted(self.active), changes=dict(self.actions), updates=self.updates,
                    published=self.bus.published, delivered=self.bus.delivered, model=self.model_hash,
                    training=self.model['training'], topics=self.bus.prefix)

    def close(self):
        self.bus.close()

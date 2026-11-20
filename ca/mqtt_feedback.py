"""Camera observations and bounded green-time decisions over a local MQTT broker."""
import json
from heapq import heappop
from math import ceil
from threading import Condition, Event
from uuid import uuid4

from .feedback import FeedbackSignals


OFFSET_STEP = 4


def green_action(row):
    """Seconds of green to add, or a negative change to finish the current green."""
    demand, served, other = row['demand'], row['pressure'], row['next_pressure']
    if 'offset_s' in row:
        target = 0
        if (row['next_brt'] and not row['brt'] or other > served + .5
                or demand and served < .45 * demand):
            target = -OFFSET_STEP
        elif row['brt'] or served >= .3 and served > other + .15:
            target = OFFSET_STEP
        return target - row['offset_s']
    if (row['can_shorten'] and not row['brt'] and
            (not demand or row['next_brt'] or
             other >= 1 and (served < .45 * demand or other > 2 * served + 2))):
        return 1 - row['remaining_s']
    if row['can_extend'] and (row['brt'] or
                              served >= 3 and served > 2 * other and not row['next_brt']):
        return 6
    return 0


def allowed_delta(row, delta):
    if type(delta) not in (int, float) or not delta:
        return False
    if 'offset_s' in row:
        return (abs(delta) <= 2 * OFFSET_STEP and row['remaining_s'] + delta > 0
                and row['offset_s'] + delta in (-OFFSET_STEP, 0, OFFSET_STEP))
    return (row['can_shorten'] and delta == 1 - row['remaining_s']
            or row['can_extend'] and delta == 6)


class MqttLoop:
    """Two independent MQTT clients. Only the actuator thread owns TraCI."""

    def __init__(self, address, run):
        from paho.mqtt.client import CallbackAPIVersion, Client, MQTTv5

        host, _, port = address.partition(':')
        if host not in ('127.0.0.1', 'localhost'):
            raise ValueError('O controle MQTT da simulação exige um broker local.')
        self.topic = f'curitiba/v1/{run}/adaptive'
        self.session = uuid4().hex
        self.condition = Condition()
        self.pending = self.reply = None
        self.last_exchange = None
        self.clients = []
        try:
            for role, channel, handler in [('policy', 'observations', self.on_observation),
                                           ('actuator', 'decisions', self.on_decision)]:
                client = Client(CallbackAPIVersion.VERSION2, client_id=f'{role}-{self.session}', protocol=MQTTv5)
                ready = Event()

                def subscribe(c, userdata, flags, code, properties, channel=channel):
                    if not code.is_failure:
                        c.subscribe(f'{self.topic}/{channel}')

                def subscribed(c, userdata, mid, codes, properties, ready=ready):
                    if codes and not any(code.is_failure for code in codes):
                        ready.set()

                client.on_connect = subscribe
                client.on_subscribe = subscribed
                client.on_message = handler
                client.connect(host, int(port or 1883))
                self.clients.append(client)
                client.loop_start()
                if not ready.wait(5):
                    raise ValueError(f'O broker não confirmou a assinatura de {channel}.')
            self.actuator = self.clients[-1]
        except BaseException:
            self.close()
            raise

    def decode(self, msg):
        if msg.retain or len(msg.payload) > 262144:
            return None
        try:
            data = json.loads(msg.payload)
        except (ValueError, RecursionError):
            return None
        if (isinstance(data, dict) and data.get('session') == self.session
                and type(data.get('observed_s')) is int and isinstance(data.get('signals'), dict)):
            return data

    def on_observation(self, client, userdata, msg):
        data = self.decode(msg)
        if data is None:
            return
        actions = {}
        try:
            for signal, row in data['signals'].items():
                delta = green_action(row)
                if delta:
                    actions[signal] = [row['phase'], delta]
        except (KeyError, TypeError, ValueError, OverflowError):
            return
        client.publish(f'{self.topic}/decisions', json.dumps({**data, 'signals': actions}))

    def on_decision(self, client, userdata, msg):
        data = self.decode(msg)
        if data is not None:
            with self.condition:
                if data['observed_s'] == self.pending and self.reply is None:
                    self.reply = data['signals']
                    self.condition.notify()

    def exchange(self, now, rows):
        packet = json.dumps(dict(session=self.session, observed_s=now, signals=rows), allow_nan=False)
        with self.condition:
            self.pending, self.reply = now, None
            try:
                receipt = self.actuator.publish(f'{self.topic}/observations', packet)
                if receipt.rc == 0:
                    self.condition.wait_for(lambda: self.reply is not None, timeout=.5)
                    self.last_exchange = {'time_s': now, 'observed': list(rows),
                                          'decisions': self.reply}
                return self.reply
            finally:
                self.pending = None

    def close(self):
        for client in self.clients:
            client.disconnect()
            client.loop_stop()


class MqttAdaptiveSignals(FeedbackSignals):
    def __init__(self, strategy, brt_lines, transport):
        super().__init__(strategy, brt_lines)
        self.transport = transport
        self.corridor_clock = {}
        self.corridor_stats = {}

    def eligible_stages(self, signal, program, stages, network):
        if program != 'kennedy50':
            return super().eligible_stages(signal, program, stages, network)
        # The short motor-only tails after concurrent pedestrian greens are clearance.
        candidates = [i for i, stage in enumerate(stages) if stage.stable and stage.duration >= 30
                      and any(network.net.getLane(src).getEdge().getName() == 'Avenida Presidente Kennedy'
                              for src in stage.movements)]
        if len(candidates) != 1:
            return False
        self.corridor_phases[signal] = candidates[0]
        return True

    def start(self, conn, network, signal_ids):
        super().start(conn, network, signal_ids)
        tls = conn.trafficlight
        for signal, target in self.corridor_phases.items():
            stages = self.stages[signal]
            current = tls.getPhase(signal)
            nominal_end = tls.getNextSwitch(signal)
            while current != target:
                current = (current + 1) % len(stages)
                nominal_end += stages[current].duration
            competing = None
            for distance in range(1, len(stages)):
                i = (target + distance) % len(stages)
                if stages[i].stable and stages[i].movements.keys() - stages[target].movements.keys():
                    competing = i
                    break
            self.corridor_clock[signal] = nominal_end, sum(s.duration for s in stages), competing
            self.corridor_stats[signal] = dict(observations=0, shortenings=0, extensions=0, max_abs_offset_s=0.)

    def result(self):
        return {**super().result(), 'kennedy_signals': self.corridor_stats}

    def update(self, conn, now, approaching, queued, downstream, buses, platoons, *, filled):
        tls = conn.trafficlight
        rows = {}
        checks = {}
        while self.events and self.events[0][0] <= now:
            event = heappop(self.events)
            _, signal, previous, started = event
            if event != self.checks[signal]:
                continue
            corridor = signal in self.corridor_phases
            if corridor and tls.getProgram(signal) != 'kennedy50':
                continue
            phase = tls.getPhase(signal)
            switch = tls.getNextSwitch(signal)
            stage = self.stages[signal][phase]
            if previous != phase:
                started = now
            eligible = phase == self.corridor_phases[signal] if corridor else stage.adjustable
            if not eligible or switch <= now:
                self.schedule(max(now+1, switch+1), signal, phase, started)
                continue
            if corridor and switch - now > 10:
                self.schedule(switch - 10, signal, phase, started)
                continue
            demand, pressure = self.load(stage, approaching, queued, filled)
            next_index = self.corridor_clock[signal][2] if corridor else self.following[signal][phase]
            following = self.stages[signal][next_index] if next_index is not None else None
            next_pressure = self.load(following, approaching, queued, filled)[1] if following else 0.
            feasible = self.reachable_brt(signal, buses, filled)
            elapsed = now - started + 1
            remaining = switch - now
            rows[signal] = dict(phase=phase, remaining_s=remaining, demand=demand, pressure=pressure,
                                next_pressure=next_pressure, brt=not stage.links.isdisjoint(feasible),
                                next_brt=following is not None and not following.links.isdisjoint(feasible))
            if corridor:
                anchor, cycle, _ = self.corridor_clock[signal]
                nominal = anchor + round((switch - anchor) / cycle) * cycle
                rows[signal]['offset_s'] = switch - nominal
                self.corridor_stats[signal]['observations'] += 1
            else:
                rows[signal].update(can_shorten=elapsed >= ceil(min(12, .6 * stage.duration)) and remaining > 1,
                                    can_extend=remaining <= 3 and elapsed + remaining <= stage.duration)
            checks[signal] = (phase, started, switch)
        if not rows:
            return
        self.stats['feedback_checks'] += len(rows)
        self.stats['mqtt_batches'] += 1
        actions = self.transport.exchange(now, rows)
        if actions is None:
            self.stats['mqtt_missed_batches'] += 1
            actions = {}
        applied = {}
        for signal, (phase, started, switch) in checks.items():
            next_check = min(switch+1, now+3)
            row = rows[signal]
            corridor = 'offset_s' in row
            if corridor:
                next_check = switch + 1
            command = actions.get(signal)
            if isinstance(command, list) and len(command) == 2 and type(command[0]) is int and command[0] == phase:
                delta = command[1]
                if allowed_delta(row, delta):
                    tls.setPhaseDuration(signal, switch + delta - now)
                    applied[signal] = delta
                    self.stats['green_adjustments'] += 1
                    self.stats['mqtt_extensions' if delta > 0 else 'mqtt_shortenings'] += 1
                    self.stats['brt_priority'] += row['brt'] if delta > 0 else row['next_brt']
                    if corridor:
                        stats = self.corridor_stats[signal]
                        stats['extensions' if delta > 0 else 'shortenings'] += 1
                        stats['max_abs_offset_s'] = max(stats['max_abs_offset_s'], abs(row['offset_s'] + delta))
                    next_check = switch + delta + 1
            self.schedule(next_check, signal, phase, started)
        return applied

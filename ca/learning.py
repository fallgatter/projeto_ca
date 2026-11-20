from collections import Counter, defaultdict
from heapq import heapify, heappop
from math import isfinite
from random import Random

from .io import ROOT, read_json, write_json
from .signal_control import MODEL_STRATEGIES, AdaptiveSignals


ACTIONS = (-8, 0, 8)
KIND = 'ca.signal.cycle-bandit.v1'
ONLINE_HALF_LIFE_S = 900
ONLINE_PRIOR_WEIGHT = 8
ONLINE_EXPLORATION = .07


def model_path(config, peak, strategy, path=None, train=False):
    if strategy not in MODEL_STRATEGIES:
        if path or train:
            raise ValueError('--model exige --control ml ou ml-online. --train exige --control ml.')
        return None
    if train:
        if strategy != 'ml' or path:
            raise ValueError('--train gera o modelo inicial e exige --control ml sem --model.')
        return None
    configured = config.get('signal_models', {}).get(peak)
    if not path and not configured:
        raise ValueError(f'Configure um modelo para o pico {peak} ou use --model.')
    path = path or ROOT/configured
    if not path.is_file():
        raise ValueError(f'Modelo de controle indisponível: {path}.')
    return path


class CycleSignals(AdaptiveSignals):
    """Change two greens by opposite amounts and keep the nominal cycle boundary."""

    def __init__(self, strategy, brt_lines, config, model=None, train=False):
        super().__init__(strategy, brt_lines)
        self.random = Random(config['seed'] + 198)
        self.train = train
        self.online = strategy == 'ml-online'
        self.learn = train or self.online
        self.reference = {}
        self.pending = {}
        self.actions = {}
        self.predictions = {}
        self.values = defaultdict(lambda: [[0, 0.] for _ in ACTIONS])
        self.recent = {}
        if model:
            data = read_json(model)
            states = data.get('states') if isinstance(data, dict) else None
            if (not isinstance(states, dict) or not states or data.get('kind') != KIND
                    or data.get('actions_s') != list(ACTIONS)
                    or any(not isinstance(row, list) or len(row) != len(ACTIONS)
                           or any(not isinstance(entry, list) or len(entry) != 2 or type(entry[0]) is not int
                                  or entry[0] < 0 or type(entry[1]) not in (float, int) or not isfinite(entry[1])
                                  for entry in row)
                           for row in states.values())):
                raise ValueError(f'Modelo de controle incompatível: {model}.')
            self.values.update(states)

    def start(self, conn, network, signal_ids):
        super().start(conn, network, signal_ids)
        for signal, stages in self.stages.items():
            # Additional programs include coordinated or externally supplied timings.
            if signal in self.programs:
                continue
            pairs = [(i, j) for i, a in enumerate(stages) for j, b in enumerate(stages[i+1:], i+1)
                     if a.adjustable and b.adjustable and min(a.duration, b.duration) >= 20
                     and a.movements.keys().isdisjoint(b.movements)]
            if not pairs:
                continue
            i, j = max(pairs, key=lambda pair: sum(stages[k].duration for k in pair))
            self.reference[signal] = i, j, sum(stage.duration for stage in stages)
        self.events = [event for event in self.events if event[1] in self.reference]
        heapify(self.events)
        self.stages = {signal: self.stages[signal] for signal in self.reference}
        self.incoming = {lane: self.incoming[lane] for stages in self.stages.values()
                         for stage in stages for lane in stage.movements}

    def observe(self, signal, approaching, queued, downstream, buses):
        first, second, _ = self.reference[signal]
        a, b = (self.stages[signal][i] for i in (first, second))
        stage_costs = []
        brt = buses.get(signal, ())
        for stage in (a, b):
            waiting = sum(queued.get(lane, 0) for lane in stage.movements)
            incoming = sum(approaching.get(lane, 0) for lane in stage.movements)
            priority = not stage.links.isdisjoint(brt)
            blocked = sum(sum(downstream.get(target, 0) for target in exits) / len(exits)
                          for exits in stage.movements.values())
            stage_costs.append((max(0., waiting + .25 * incoming - .35 * blocked) + 3 * priority, priority))
        (cost_a, brt_a), (cost_b, brt_b) = stage_costs
        return cost_a, cost_b, int(brt_a) - int(brt_b)

    def choose(self, a, b, priority, now=0, explore=False):
        balance = a - b
        heuristic = 2 if balance >= 2 else 0 if balance <= -2 else 1
        if self.strategy == 'cycle-pressure':
            return None, heuristic
        bucket = max(-2, min(2, round(balance / 2)))
        state = f'{bucket},{int(a+b >= 6)},{priority}'
        estimates = self.values.get(state, ((0, 0.),) * len(ACTIONS))
        scores = [(n, total / (n + 8)) for n, total in estimates]
        if self.train and self.random.random() < .65:
            return state, self.random.randrange(len(ACTIONS))
        frozen = self.preferred(scores)
        if not self.online:
            return state, frozen
        recent = self.recent_estimates(state, now)
        adjusted = [(n + weight, (ONLINE_PRIOR_WEIGHT * score + total) / (ONLINE_PRIOR_WEIGHT + weight))
                    for (n, score), (weight, total) in zip(scores, recent)]
        choice = self.preferred(adjusted)
        if explore and a+b < 6 and self.random.random() < ONLINE_EXPLORATION:
            self.stats['online_explorations'] += 1
            return state, self.random.choice([i for i in range(len(ACTIONS)) if i != choice])
        if choice != frozen:
            self.stats['online_policy_changes'] += 1
        return state, choice

    @staticmethod
    def preferred(estimates):
        supported = [i for i, (count, _) in enumerate(estimates) if count >= 12]
        if 1 not in supported:
            return 1
        chosen = max(supported, key=lambda i: (estimates[i][1], i == 1))
        return chosen if estimates[chosen][1] - estimates[1][1] > .14 else 1

    def recent_estimates(self, state, now):
        last, estimates = self.recent.get(state, (now, ((0., 0.),) * len(ACTIONS)))
        decay = 2 ** ((last-now) / ONLINE_HALF_LIFE_S)
        return [[weight * decay, total * decay] for weight, total in estimates]

    def record_reward(self, state, action, reward, now):
        if self.online:
            estimates = self.recent_estimates(state, now)
            self.recent[state] = now, estimates
            self.stats['online_updates'] += 1
        else:
            estimates = self.values[state]
        estimates[action][0] += 1
        estimates[action][1] += reward

    def update(self, conn, now, approaching, queued, downstream, buses, platoons):
        if self.learn and now % 5 == 0:
            for signal, sample in self.pending.items():
                a, b, _ = self.observe(signal, approaching, queued, downstream, buses)
                sample[3] += a + b
                sample[4] += 1
        tls = conn.trafficlight
        while self.events and self.events[0][0] <= now:
            _, signal, previous, _ = heappop(self.events)
            phase = tls.getPhase(signal)
            switch = tls.getNextSwitch(signal)
            adjustment = 0
            if phase != previous:
                first, second, cycle = self.reference[signal]
                if phase == 0:
                    expected = self.predictions.get(signal)
                    if expected is not None and abs(now-expected) > .01:
                        self.stats['cycle_timing_errors'] += 1
                    self.predictions[signal] = now + cycle
                    if self.learn and signal in self.pending:
                        state, action, initial, cost, count = self.pending.pop(signal)
                        if count:
                            self.record_reward(state, action, initial - cost/count, now)
                    a, b, priority = self.observe(signal, approaching, queued, downstream, buses)
                    state, action = self.choose(a, b, priority, now, not buses.get(signal)) if a+b else (None, 1)
                    self.actions[signal] = ACTIONS[action]
                    self.stats['decisions'] += 1
                    if state is not None and self.learn:
                        self.pending[signal] = [state, action, a+b, 0., 0]
                if phase == first:
                    adjustment = self.actions.get(signal, 0)
                elif phase == second:
                    adjustment = -self.actions.get(signal, 0)
                if adjustment:
                    tls.setPhaseDuration(signal, switch-now+adjustment)
                    switch += adjustment
                    self.stats['green_adjustments'] += 1
            self.schedule(max(now+1, switch+1), signal, phase, now)

    def extend(self, conn, now, request):
        return False

    def save(self, path):
        write_json(path, {'kind': KIND, 'actions_s': list(ACTIONS), 'states': dict(self.values)})

    def save_online(self, path, now):
        write_json(path, {'kind': 'ca.signal.online-evidence.v1', 'time_s': now, 'actions_s': list(ACTIONS),
                          'half_life_s': ONLINE_HALF_LIFE_S,
                          'states': {state: self.recent_estimates(state, now) for state in sorted(self.recent)}})

    def online_status(self):
        return {key: self.stats[key] for key in ('online_updates', 'online_policy_changes', 'online_explorations')}

    def result(self):
        stats = {**super().result(), 'cycle_timing_errors': self.stats['cycle_timing_errors'],
                 'trained_samples': sum(n for estimates in self.values.values() for n, _ in estimates)}
        if self.online:
            stats.update(self.online_status())
        return stats

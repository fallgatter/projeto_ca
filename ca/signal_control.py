from collections import Counter, defaultdict
from dataclasses import dataclass
from heapq import heappop, heappush


MODEL_STRATEGIES = ('ml', 'ml-online')
CYCLE_STRATEGIES = ('cycle-pressure', *MODEL_STRATEGIES)
FEEDBACK_STRATEGIES = ('feedback', 'feedback-transit', 'mqtt-adaptive')
STRATEGIES = ('fixed', 'gap', 'queue', 'pressure', 'pressure-coordinated', 'transit',
              *CYCLE_STRATEGIES, *FEEDBACK_STRATEGIES)
CONTROL_OPTIONS = (*STRATEGIES, 'by-peak')
LABELS = {
    'fixed': 'Tempo fixo',
    'gap': 'Atuação por presença',
    'queue': 'Atuação por fila',
    'pressure': 'Pressão local',
    'pressure-coordinated': 'Pressão e chegada de pelotões',
    'transit': 'Prioridade BRT seletiva',
    'cycle-pressure': 'Pressão com ciclo fixo',
    'ml': 'Aprendizado por ciclo',
    'ml-online': 'Aprendizado online',
    'feedback': 'Malha fechada com controle de filas',
    'feedback-transit': 'Malha fechada com prioridade BRT',
    'mqtt-adaptive': 'Pressão e prioridade BRT via MQTT',
}


def strategy_for_peak(requested, config, peak):
    strategy = config.get('signal_control_by_peak', {}).get(peak) if requested == 'by-peak' else requested
    if strategy not in STRATEGIES:
        raise ValueError(f'Estratégia semafórica inválida para a janela {peak}: {strategy}.')
    return strategy


def stable_green(state):
    return any(light in 'Gg' for light in state) and not any(light in 'yYuU' for light in state)


@dataclass
class Stage:
    duration: float
    movements: dict
    links: frozenset
    adjustable: bool
    stable: bool


class AdaptiveSignals:
    """Redistribute green within the active SUMO program using virtual approach detectors."""

    def __init__(self, strategy, brt_lines):
        self.strategy = strategy
        self.brt_lines = frozenset(brt_lines)
        self.stages = {}
        self.programs = {}
        self.events = []
        self.checks = {}
        self.incoming = {}
        self.downstream = set()
        self.bus_approaches = {}
        self.current = {}
        self.external_holds = {}
        self.transit_priority = set()
        self.stats = Counter()

    def eligible_stages(self, signal, program, stages, network):
        return (sum(bool(stage.movements) and stage.stable for stage in stages) >= 2
                and any(stage.adjustable for stage in stages))

    def start(self, conn, network, signal_ids):
        tls = conn.trafficlight
        for signal in sorted(signal_ids):
            program = tls.getProgram(signal)
            logics = tls.getAllProgramLogics(signal)
            logic = next((candidate for candidate in logics if candidate.programID == program), None)
            if logic is None or logic.type != 0:
                continue
            controlled = tls.getControlledLinks(signal)
            links = []
            for group in controlled:
                lanes = [(network.net.getLane(src), network.net.getLane(dst)) for src, dst, _ in group]
                motor = [(src.getID(), dst.getID()) for src, dst in lanes
                         if src.allows('bus') or src.allows('passenger')]
                active = any(src.getEdge().getFunction() == 'crossing' or
                             dst.getEdge().getFunction() == 'crossing' or
                             src.allows('bicycle') and not (src.allows('bus') or src.allows('passenger'))
                             for src, dst in lanes)
                links.append((motor, active))
            stages = []
            for index, phase in enumerate(logic.phases):
                green = frozenset(i for i, lamp in enumerate(phase.state) if lamp in 'Gg')
                movements = defaultdict(set)
                for i in sorted(green):
                    for src, dst in links[i][0]:
                        movements[src].add(dst)
                following = (index + 1) % len(logic.phases)
                stable = stable_green(phase.state)
                clearance = logic.phases[following].state
                adjustable = (stable and phase.duration >= 12 and movements
                              and not any(links[i][1] for i in green)
                              and all(clearance[i] in 'yYrR' for i in green))
                stages.append(Stage(phase.duration, dict(movements), green, bool(adjustable), stable))
            # Only operate cyclic fixed programs with a competing motor stage.
            if (any(phase.next and tuple(phase.next) != ((i + 1) % len(stages),)
                    for i, phase in enumerate(logic.phases))
                    or not self.eligible_stages(signal, program, stages, network)):
                continue
            self.stages[signal] = stages
            if len(logics) > 1:
                self.programs[signal] = program
            for stage in stages:
                for lane in stage.movements:
                    self.incoming[lane] = network.net.getLane(lane).getLength()
                self.downstream.update(dst for lanes in stage.movements.values() for dst in lanes)
            self.schedule(tls.getNextSwitch(signal) + 1, signal, -1, 0.)

    def schedule(self, when, signal, phase, started):
        event = (when, signal, phase, started)
        self.checks[signal] = event
        heappush(self.events, event)

    def observe_bus(self, conn, actor, lane):
        previous = self.bus_approaches.get(actor)
        if previous is None or previous[0] != lane:
            next_signals = conn.vehicle.getNextTLS(actor)
            previous = (lane, next_signals[0][:2] if next_signals else None)
            self.bus_approaches[actor] = previous
        return previous[1]

    def update(self, conn, now, approaching, queued, downstream, buses, platoons):
        tls = conn.trafficlight
        while self.events and self.events[0][0] <= now:
            event = heappop(self.events)
            _, signal, previous, started = event
            if self.checks[signal] != event:
                continue
            if signal in self.programs and tls.getProgram(signal) != self.programs[signal]:
                self.current.pop(signal, None)
                continue
            phase = tls.getPhase(signal)
            switch = tls.getNextSwitch(signal)
            stage = self.stages[signal][phase]
            next_check = switch + 1
            if phase != previous:
                started = now
                self.current[signal] = (phase, started)
                self.external_holds.pop(signal, None)
                self.transit_priority.discard(signal)
            if stage.adjustable and self.strategy != 'transit':
                minimum = min(12, stage.duration * .6)
                brt = buses.get(signal, {})
                serving_brt = not stage.links.isdisjoint(brt)
                opposing_brt = any(link not in stage.links for link in brt)
                if self.strategy == 'gap':
                    elapsed = now - started + 1
                    limit = stage.duration + (6 if serving_brt else 0)
                    present = any(approaching.get(lane) for lane in stage.movements)
                    if elapsed >= minimum and (not present or opposing_brt and not serving_brt):
                        limit = min(limit, elapsed + 1)
                    new_switch = max(now + 1, started - 1 + limit)
                    new_switch = max(new_switch, self.external_holds.get(signal, 0))
                    if now < switch and new_switch != switch:
                        tls.setPhaseDuration(signal, new_switch - now)
                        self.stats['green_adjustments'] += 1
                        self.stats['brt_priority'] += serving_brt and new_switch > switch
                    else:
                        new_switch = switch
                    next_check = min(new_switch + 1, now + 3)
                elif phase != previous:
                    score = self.score(stage, approaching, queued, downstream, platoons)
                    competing = [other for other in self.stages[signal]
                                 if other is not stage and other.movements.keys() - stage.movements.keys()]
                    other_score = max((self.score(other, approaching, queued, downstream, platoons)
                                       for other in competing), default=0.)
                    share = score / (score + other_score + 1.)
                    green = minimum + (stage.duration + 7 - minimum) * share
                    if opposing_brt and not serving_brt:
                        green = max(minimum, green - 4)
                    if serving_brt:
                        green = min(stage.duration + 10, green + 6)
                        self.stats['brt_priority'] += 1
                    remaining = max(1, round(green) - 1)
                    tls.setPhaseDuration(signal, remaining)
                    self.stats['green_adjustments'] += 1
                    next_check = now + remaining + 1
            self.schedule(max(now + 1, next_check), signal, phase, started)
        if self.strategy == 'transit':
            self.prioritize_transit(tls, now, buses)

    def prioritize_transit(self, tls, now, buses):
        for signal, requests in buses.items():
            active = self.current.get(signal)
            if active is None or signal in self.transit_priority or signal in self.external_holds:
                continue
            phase, started = active
            stages = self.stages[signal]
            stage = stages[phase]
            if (not stage.adjustable or tls.getPhase(signal) != phase
                    or signal in self.programs and tls.getProgram(signal) != self.programs[signal]):
                continue
            switch = tls.getNextSwitch(signal)
            time_left = switch - now
            if time_left < 1:
                continue
            if not stage.links.isdisjoint(requests):
                if time_left > 4:
                    continue
                new_switch = switch + 6
            else:
                if time_left <= 2 or now-started+1 < max(12, stage.duration*.65):
                    continue
                next_stage = next((stages[index] for index in (*range(phase+1, len(stages)), *range(phase))
                                   if stages[index].stable), None)
                if next_stage is None or next_stage.links.isdisjoint(requests):
                    continue
                new_switch = now + 1
            tls.setPhaseDuration(signal, new_switch - now)
            self.schedule(new_switch + 1, signal, phase, started)
            self.transit_priority.add(signal)
            self.stats.update(green_adjustments=1, brt_priority=1)

    def extend(self, conn, now, request):
        signal, phase = request['signal_id'], request['phase_index']
        active = self.current.get(signal)
        if active is None or active[0] != phase or signal in self.external_holds:
            return False
        stage = self.stages[signal][phase]
        tls = conn.trafficlight
        if (not stage.adjustable or tls.getPhase(signal) != phase
                or signal in self.programs and tls.getProgram(signal) != self.programs[signal]):
            return False
        switch = tls.getNextSwitch(signal)
        finish = switch + request['seconds']
        if switch != request['next_switch_s'] or switch <= now or finish > active[1] - 1 + stage.duration + 10:
            return False
        tls.setPhaseDuration(signal, finish - now)
        self.external_holds[signal] = finish
        self.stats['mqtt_extensions'] += 1
        return True

    def score(self, stage, approaching, queued, downstream, platoons):
        score = 0.
        for src, exits in stage.movements.items():
            demand = queued.get(src, 0) + .35 * approaching.get(src, 0)
            if self.strategy.startswith('pressure'):
                discharge = sum(downstream.get(dst, 0) for dst in exits) / len(exits)
                demand = max(0., demand - .8 * discharge)
            if self.strategy == 'pressure-coordinated':
                demand += .7 * platoons.get(src, 0)
            score += demand
        return score

    def result(self):
        return {'strategy': self.strategy, 'controlled_signals': len(self.stages),
                'brt_lines': sorted(self.brt_lines),
                **dict.fromkeys(('green_adjustments', 'brt_priority', 'mqtt_extensions'), 0),
                **self.stats}

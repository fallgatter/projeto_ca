from heapq import heapify, heappop

from .signal_control import AdaptiveSignals


class FeedbackSignals(AdaptiveSignals):
    """Control green time using upstream demand and downstream space."""

    def __init__(self, strategy, brt_lines):
        super().__init__(strategy, brt_lines)
        self.storage = {}
        self.link_exits = {}
        self.following = {}
        self.corridor_phases = {}

    def start(self, conn, network, signal_ids):
        super().start(conn, network, signal_ids)
        self.stages = {signal: stages for signal, stages in self.stages.items()
                       if signal not in self.programs or signal in self.corridor_phases}
        self.events = [event for event in self.events if event[1] in self.stages]
        heapify(self.events)
        self.incoming = {lane: self.incoming[lane] for stages in self.stages.values()
                         for stage in stages for lane in stage.movements}
        exits = {lane for stages in self.stages.values() for stage in stages
                 for targets in stage.movements.values() for lane in targets}
        self.storage = {lane: network.net.getLane(lane).getLength() for lane in sorted(exits)}
        for signal, stages in self.stages.items():
            self.link_exits[signal] = [tuple(dst for _, dst, _ in group if dst in self.storage)
                                       for group in conn.trafficlight.getControlledLinks(signal)]
            stable = {i for i, stage in enumerate(stages) if stage.stable and stage.movements}
            self.following[signal] = {
                i: next((k % len(stages) for k in range(i+1, i+len(stages)) if k % len(stages) in stable), None)
                for i in range(len(stages))
            }

    def occupancy(self, lane, filled):
        return min(1., filled.get(lane, 0.) / self.storage[lane])

    def load(self, stage, approaching, queued, filled):
        demand = pressure = 0.
        for lane, exits in stage.movements.items():
            waiting = queued.get(lane, 0) + .35 * approaching.get(lane, 0)
            demand += waiting
            room = sum(1-self.occupancy(dst, filled) for dst in exits) / len(exits)
            pressure += waiting * room
        return demand, pressure

    def reachable_brt(self, signal, buses, filled):
        links = self.link_exits[signal]
        return {link for link in buses.get(signal, ())
                if link < len(links) and any(self.occupancy(dst, filled) < .72 for dst in links[link])}

    def update(self, conn, now, approaching, queued, downstream, buses, platoons, *, filled):
        tls = conn.trafficlight
        while self.events and self.events[0][0] <= now:
            event = heappop(self.events)
            _, signal, previous, started = event
            if self.checks[signal] != event:
                continue
            phase = tls.getPhase(signal)
            switch = tls.getNextSwitch(signal)
            stages = self.stages[signal]
            stage = stages[phase]
            if phase != previous:
                started = now
                self.transit_priority.discard(signal)
            next_check = switch + 1
            if stage.adjustable:
                self.stats['feedback_checks'] += 1
                demand, pressure = self.load(stage, approaching, queued, filled)
                next_index = self.following[signal][phase]
                following = stages[next_index] if next_index is not None else None
                other_pressure = self.load(following, approaching, queued, filled)[1] if following else 0.
                feasible_brt = self.reachable_brt(signal, buses, filled)
                can_serve = not stage.links.isdisjoint(feasible_brt)
                next_serves = following is not None and not following.links.isdisjoint(feasible_brt)
                if not stage.links.isdisjoint(buses.get(signal, ())) and not can_serve:
                    self.stats['blocked_brt_checks'] += 1
                elapsed = now-started+1
                new_switch = switch
                if self.strategy == 'feedback':
                    limit = stage.duration + (6 if can_serve else 0)
                    nominal_end = started - 1 + limit
                    new_switch = max(now+1, nominal_end)
                    minimum = min(12, stage.duration * .6)
                    if elapsed >= minimum and not can_serve:
                        if not demand or next_serves or (other_pressure >= 1 and pressure < .45*demand):
                            new_switch = min(new_switch, now+1)
                            if pressure < .45*demand:
                                self.stats['spillback_checks'] += 1
                elif signal not in self.transit_priority:
                    remaining = switch-now
                    if can_serve and 0 < remaining <= 4 and pressure >= .35*demand:
                        new_switch = switch + 6
                    elif (not can_serve and next_serves and remaining > 2
                          and elapsed >= max(12, .65*stage.duration) and pressure <= max(4, 2*other_pressure)):
                        new_switch = now + 1
                if now < switch and new_switch != switch:
                    tls.setPhaseDuration(signal, new_switch-now)
                    self.stats['green_adjustments'] += 1
                    self.stats['brt_priority'] += can_serve and new_switch > switch or next_serves and new_switch < switch
                    if self.strategy == 'feedback-transit':
                        self.transit_priority.add(signal)
                    switch = new_switch
                next_check = min(switch+1, now+3)
            self.schedule(max(now+1, next_check), signal, phase, started)

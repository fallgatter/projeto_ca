import json
import unittest
from threading import Condition
from types import SimpleNamespace
from unittest.mock import Mock

from ca.mqtt_feedback import MqttAdaptiveSignals, MqttLoop, allowed_delta, green_action
from ca.signal_control import Stage


class MqttFeedbackTest(unittest.TestCase):
    def test_kennedy_decision_targets_the_original_clock(self):
        row = dict(demand=8, pressure=7, next_pressure=1, remaining_s=10,
                   brt=False, next_brt=False, offset_s=-4)
        self.assertEqual(green_action(row), 8)
        self.assertTrue(allowed_delta(row, 8))
        self.assertFalse(allowed_delta(row, 9))
        self.assertFalse(allowed_delta(dict(row, remaining_s=3, offset_s=4), -8))
        self.assertEqual(green_action(dict(row, next_pressure=12, offset_s=4)), -8)
        self.assertEqual(green_action(dict(row, demand=0, pressure=0, next_pressure=0, offset_s=4)), -4)

    def test_kennedy_actuator_leaves_the_crossing_phase_to_the_program(self):
        transport = Mock()
        transport.exchange.return_value = {'A': [0, -8]}
        control = MqttAdaptiveSignals('mqtt-adaptive', (), transport)
        control.stages['A'] = [Stage(77, {'in': {'out'}}, frozenset({0}), True, True),
                               Stage(5, {}, frozenset({1}), False, True)]
        control.corridor_phases['A'] = 0
        control.corridor_clock['A'] = (77, 90, None)
        control.corridor_stats['A'] = dict(observations=0, shortenings=0, extensions=0, max_abs_offset_s=0.)
        control.storage['out'] = 100
        control.link_exits['A'] = [('out',)]
        control.schedule(71, 'A', 0, 5)
        tls = Mock()
        tls.getProgram.return_value = 'kennedy50'
        tls.getPhase.return_value = 0
        tls.getNextSwitch.return_value = 81
        conn = SimpleNamespace(trafficlight=tls)
        control.update(conn, 71, {}, {}, {}, {}, {}, filled={})
        tls.setPhaseDuration.assert_called_once_with('A', 2)
        self.assertEqual(control.corridor_stats['A']['max_abs_offset_s'], 4)
        tls.getPhase.return_value = 1
        tls.getNextSwitch.return_value = 78
        control.update(conn, 74, {}, {}, {}, {}, {}, filled={})
        transport.exchange.assert_called_once()
        self.assertEqual(tls.setPhaseDuration.call_count, 1)

    def test_policy_compares_serviceable_demand_and_brt(self):
        row = dict(demand=5, pressure=1, next_pressure=4, remaining_s=8,
                   brt=False, next_brt=False, can_shorten=True, can_extend=False)
        self.assertEqual(green_action(row), -7)
        self.assertEqual(green_action(dict(row, brt=True)), 0)
        self.assertEqual(green_action(dict(row, can_shorten=False)), 0)
        self.assertEqual(green_action(dict(row, pressure=9, next_pressure=0,
                                          remaining_s=2, can_extend=True)), 6)

    def test_late_retained_and_duplicate_decisions(self):
        loop = MqttLoop.__new__(MqttLoop)
        loop.session = 'test'
        loop.condition = Condition()
        loop.pending, loop.reply = 12, None

        def deliver(second=12, session='test', retain=False, signals=None):
            data = dict(session=session, observed_s=second, signals=signals or {})
            loop.on_decision(None, None, SimpleNamespace(payload=json.dumps(data).encode(), retain=retain))

        deliver(11)
        deliver(session='older-run')
        deliver(retain=True)
        self.assertIsNone(loop.reply)
        deliver(signals={'A': [0, 6]})
        deliver(signals={'A': [0, -7]})
        self.assertEqual(loop.reply, {'A': [0, 6]})

    def test_actuator_checks_phase_minimum_budget_and_fallback(self):
        for now, reply, expected in [
            (4, {'A': [0, -26]}, None), (16, {'A': [1, -14]}, None),
            (16, {'A': [0, -15]}, None), (16, None, None),
            (16, {'A': [0, -13]}, 1), (28, {'A': [0, 7]}, None),
            (28, {'A': [0, 6]}, 8),
        ]:
            with self.subTest(now=now, reply=reply):
                transport = Mock()
                transport.exchange.return_value = reply
                control = MqttAdaptiveSignals('mqtt-adaptive', (), transport)
                stage = Stage(30, {'in': {'out'}}, frozenset({0}), True, True)
                control.stages['A'] = [stage, stage]
                control.following['A'] = {0: 1, 1: 0}
                control.storage['out'] = 100
                control.link_exits['A'] = [('out',)]
                control.schedule(now, 'A', 0, 1)
                conn = Mock()
                conn.trafficlight.getPhase.return_value = 0
                conn.trafficlight.getNextSwitch.return_value = 30
                control.update(conn, now, {}, {}, {}, {}, {}, filled={})
                if expected is None:
                    conn.trafficlight.setPhaseDuration.assert_not_called()
                else:
                    conn.trafficlight.setPhaseDuration.assert_called_once_with('A', expected)
                self.assertEqual(control.stats['mqtt_missed_batches'], int(reply is None))

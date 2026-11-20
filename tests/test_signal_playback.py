import unittest

from ca.dashboard import signal_activity, signal_colors


class SignalPlaybackTest(unittest.TestCase):
    def test_seek_reconstructs_state_without_showing_future_messages(self):
        packet = {'time_s': 2, 'observed': ['A'], 'decisions': {}, 'applied': {}}
        rows = [
            {'time_s': 0, 'full': True, 'lights': {'A': 'Gr', 'B': 'rr'}},
            {'time_s': 1, 'full': False, 'lights': {'A': 'yr'}},
            {'time_s': 2, 'full': False, 'lights': {'A': 'rr'}, 'mqtt': packet},
            {'time_s': 3, 'full': True, 'lights': {'A': 'rr', 'B': 'Gr'}},
            {'time_s': 4, 'full': False, 'lights': {}},
            {'time_s': 5, 'full': False, 'lights': {}},
        ]
        self.assertEqual(signal_activity(rows, 1.5), ({'A': 'yr', 'B': 'rr'}, []))
        self.assertEqual(signal_activity(rows, 3.5), ({'A': 'rr', 'B': 'Gr'}, [packet]))
        self.assertEqual(signal_activity(rows, 5), ({'A': 'rr', 'B': 'Gr'}, []))

    def test_colors_follow_movements_of_each_lane(self):
        approaches = [{'signal': 'A', 'links': indexes} for indexes in ([0, 2], [1], [2], [3])]
        colors, lamps = signal_colors(approaches, {'A': 'Gyrs'})
        self.assertEqual(lamps, ['gr', 'y', 'r', 's'])
        self.assertEqual(colors, ['#18a957', '#e8a012', '#da493f', '#da493f'])

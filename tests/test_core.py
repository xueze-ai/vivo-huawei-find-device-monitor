import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vivo'))
from core import evaluate


class GeofenceTests(unittest.TestCase):
    def setUp(self):
        self.cfg = {'crs': 'GCJ02', 'max_age_seconds': 360, 'movement_meters': 100, 'zones': [{'name': '学校', 'lat': 30, 'lon': 110, 'radius_meters': 200, 'buffer_meters': 30}]}
        self.fix = {'lat': 30, 'lon': 110, 'accuracy': 10, 'timestamp': 1000, 'crs': 'GCJ02'}

    def test_first_fix_is_not_arrival(self):
        state, title, _ = evaluate(self.fix, {}, self.cfg, 1000)
        self.assertNotIn('到达', title)
        self.assertEqual(state['zones']['学校'], 'inside')

    def test_departure_and_restart(self):
        state, _, _ = evaluate(self.fix, {}, self.cfg, 1000)
        new = dict(self.fix, lat=30.01, timestamp=1300)
        state, title, _ = evaluate(new, state, self.cfg, 1300)
        self.assertIn('离开学校', title)
        _, title, _ = evaluate(dict(new, timestamp=1600), state, self.cfg, 1600)
        self.assertNotIn('离开', title)

    def test_stale_does_not_change_state(self):
        state, _, _ = evaluate(self.fix, {}, self.cfg, 1000)
        result, title, _ = evaluate(dict(self.fix, lat=31), state, self.cfg, 1300)
        self.assertEqual(result, state)
        self.assertEqual(title, '手机离线或定位未更新')

    def test_exact_radius_decides_departure(self):
        state, _, _ = evaluate(self.fix, {}, self.cfg, 1000)
        result, title, _ = evaluate(dict(self.fix, lat=30.002, timestamp=1300, accuracy=150), state, self.cfg, 1300)
        self.assertEqual(result['zones']['学校'], 'outside')
        self.assertIn('离开', title)

    def test_wrong_crs_rejected(self):
        with self.assertRaises(ValueError):
            evaluate(dict(self.fix, crs='WGS84'), {}, self.cfg, 1000)

    def test_unknown_accuracy_has_no_pending_boundary(self):
        _, _, body = evaluate(dict(self.fix, accuracy=None), {}, self.cfg, 1000)
        self.assertNotIn('待确认', body)


if __name__ == '__main__':
    unittest.main()

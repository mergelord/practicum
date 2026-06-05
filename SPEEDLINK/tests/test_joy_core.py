# -*- coding: utf-8 -*-
import unittest

from joy_core import (
    axis_stats,
    autogen_correction,
    apply_correction,
    apply_profile_axis,
    is_safe_autocenter,
    normalize_with_calibrated_range,
    to_vjoy,
)


class JoyCoreTests(unittest.TestCase):
    def test_axis_stats_empty(self):
        self.assertEqual(axis_stats([])["mean"], 0.0)
        self.assertEqual(axis_stats([])["spread"], 0.0)

    def test_axis_stats_drift_uses_first_and_last_decile(self):
        st = axis_stats([0.0] * 90 + [0.1] * 10)
        self.assertAlmostEqual(st["drift"], 0.1, places=6)

    def test_autogen_detects_throttle_at_edge(self):
        c = autogen_correction({"mean": 0.98, "spread": 0.001, "sd": 0.0001})
        self.assertEqual(c["type"], "throttle")
        self.assertEqual(c["deadzone"], 0.0)

    def test_autogen_stick_center_offset_cancels_mean(self):
        c = autogen_correction({"mean": 0.25, "spread": 0.01, "sd": 0.002})
        self.assertEqual(c["type"], "stick")
        self.assertAlmostEqual(apply_correction(0.25, c), 0.0, places=6)

    def test_deadzone_maps_small_values_to_zero(self):
        c = {"type": "stick", "center_offset": 0.0, "deadzone": 0.1, "scale_pos": 1.0, "scale_neg": 1.0}
        self.assertEqual(apply_correction(0.05, c), 0.0)
        self.assertEqual(apply_correction(-0.05, c), 0.0)

    def test_throttle_passthrough_and_invert(self):
        c = {"type": "throttle", "invert": True}
        self.assertAlmostEqual(apply_correction(0.4, c), -0.4)

    def test_to_vjoy_edges_and_center(self):
        self.assertEqual(to_vjoy(-1.0), 1)
        self.assertEqual(to_vjoy(1.0), 32768)
        self.assertIn(to_vjoy(0.0), (16384, 16385))

    def test_calibrated_range_remaps_to_full_travel(self):
        c = {"calibrated_min": -0.8, "calibrated_max": 0.8}
        self.assertAlmostEqual(normalize_with_calibrated_range(-0.8, c), -1.0)
        self.assertAlmostEqual(normalize_with_calibrated_range(0.8, c), 1.0)
        self.assertAlmostEqual(normalize_with_calibrated_range(0.0, c), 0.0)

    def test_apply_profile_axis_uses_calibrated_range_then_correction(self):
        c = {"type": "stick", "center_offset": 0.0, "deadzone": 0.0, "scale_pos": 1.0, "scale_neg": 1.0,
             "calibrated_min": -0.5, "calibrated_max": 0.5}
        self.assertAlmostEqual(apply_profile_axis(0.5, c), 1.0)
        self.assertAlmostEqual(apply_profile_axis(-0.5, c), -1.0)

    def test_runtime_center_overrides_saved_center_for_stick(self):
        c = {"type": "stick", "center_offset": -0.1, "deadzone": 0.0, "scale_pos": 1.0, "scale_neg": 1.0}
        self.assertAlmostEqual(apply_correction(0.3, c, runtime_center=0.3), 0.0)

    def test_autocenter_safety(self):
        self.assertTrue(is_safe_autocenter({"mean": 0.1, "spread": 0.02}))
        self.assertFalse(is_safe_autocenter({"mean": 0.7, "spread": 0.02}))
        self.assertFalse(is_safe_autocenter({"mean": 0.1, "spread": 0.2}))


if __name__ == "__main__":
    unittest.main()

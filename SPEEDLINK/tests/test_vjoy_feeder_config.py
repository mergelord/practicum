# -*- coding: utf-8 -*-
import unittest

from vjoy_feeder import (
    apply_hold_filter,
    hold_threshold,
    parse_int_auto,
    pause_axis_value,
    pov_to_vjoy_discrete,
    profile_device_ids,
)


class VJoyFeederConfigTests(unittest.TestCase):
    def test_parse_int_auto_accepts_hex_and_decimal(self):
        self.assertEqual(parse_int_auto("0x07B5"), 0x07B5)
        self.assertEqual(parse_int_auto("1973"), 1973)
        self.assertIsNone(parse_int_auto(None))

    def test_profile_device_ids_are_optional_and_profile_driven(self):
        self.assertEqual(profile_device_ids({}), (None, None))
        self.assertEqual(
            profile_device_ids({"device": {"vid": "0x07B5", "pid": "0x0317"}}),
            (0x07B5, 0x0317),
        )

    def test_pov_conversion(self):
        self.assertEqual(pov_to_vjoy_discrete(0xFFFF), -1)
        self.assertEqual(pov_to_vjoy_discrete(0), 0)
        self.assertEqual(pov_to_vjoy_discrete(9000), 1)
        self.assertEqual(pov_to_vjoy_discrete(18000), 2)
        self.assertEqual(pov_to_vjoy_discrete(27000), 3)

    def test_hold_threshold_accepts_preferred_key_and_alias(self):
        self.assertEqual(hold_threshold({}), 0.0)
        self.assertEqual(hold_threshold({"hold_threshold": 0.03}), 0.03)
        self.assertEqual(hold_threshold({"jitter_deadband": "0.02"}), 0.02)
        self.assertEqual(hold_threshold({"hold_threshold": -1}), 0.0)
        self.assertEqual(hold_threshold({"hold_threshold": "bad"}), 0.0)

    def test_hold_filter_keeps_small_jitter_until_real_motion(self):
        state = {}
        corr = {"type": "throttle", "hold_threshold": 0.03}

        self.assertEqual(apply_hold_filter("Z", 0.500, corr, state), 0.500)
        self.assertEqual(apply_hold_filter("Z", 0.510, corr, state), 0.500)
        self.assertEqual(apply_hold_filter("Z", 0.529, corr, state), 0.500)
        self.assertEqual(apply_hold_filter("Z", 0.531, corr, state), 0.531)
        self.assertEqual(apply_hold_filter("Z", 0.540, corr, state), 0.531)

    def test_hold_filter_is_disabled_without_threshold(self):
        state = {}
        corr = {"type": "throttle"}
        self.assertEqual(apply_hold_filter("Z", 0.500, corr, state), 0.500)
        self.assertEqual(apply_hold_filter("Z", 0.510, corr, state), 0.510)
        self.assertEqual(state, {})

    def test_pause_axis_value_centers_sticks_and_holds_throttle(self):
        last = {"X": 0.45, "Z": -0.25}
        self.assertEqual(pause_axis_value("X", {"type": "stick"}, last), 0.0)
        self.assertEqual(pause_axis_value("R", {}, last), 0.0)
        self.assertEqual(pause_axis_value("Z", {"type": "throttle"}, last), -0.25)
        self.assertEqual(pause_axis_value("U", {"type": "throttle"}, last), 0.0)


if __name__ == "__main__":
    unittest.main()

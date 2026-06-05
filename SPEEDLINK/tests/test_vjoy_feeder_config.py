# -*- coding: utf-8 -*-
import unittest

from vjoy_feeder import parse_int_auto, pov_to_vjoy_discrete, profile_device_ids


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


if __name__ == "__main__":
    unittest.main()

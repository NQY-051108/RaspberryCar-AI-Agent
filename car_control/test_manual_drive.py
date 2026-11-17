#!/usr/bin/env python3
"""Keyboard state tests that never import gpiozero or access GPIO."""

import unittest

from manual_drive import handle_key


class FakeController:
    def __init__(self):
        self.calls = []

    def forward(self, speed):
        self.calls.append(("forward", speed))

    def backward(self, speed):
        self.calls.append(("backward", speed))

    def left(self, speed):
        self.calls.append(("left", speed))

    def right(self, speed):
        self.calls.append(("right", speed))

    def stop(self):
        self.calls.append(("stop",))


class ManualDriveTests(unittest.TestCase):
    def setUp(self):
        self.controller = FakeController()

    def test_first_and_repeated_key_do_not_reissue_motor_command(self):
        active, delay = handle_key(self.controller, "w", None, 0.5, 0.25, 0.75)
        self.assertEqual((active, delay), ("w", 0.75))
        self.assertEqual(self.controller.calls, [("forward", 0.5)])

        active, delay = handle_key(self.controller, "w", active, 0.5, 0.25, 0.75)
        self.assertEqual((active, delay), ("w", 0.25))
        self.assertEqual(self.controller.calls, [("forward", 0.5)])

    def test_direction_change_updates_motor_once_with_startup_grace(self):
        active, _ = handle_key(self.controller, "w", None, 0.5, 0.25, 0.75)
        active, delay = handle_key(self.controller, "d", active, 0.5, 0.25, 0.75)
        self.assertEqual((active, delay), ("d", 0.75))
        self.assertEqual(self.controller.calls, [("forward", 0.5), ("right", 0.5)])

    def test_space_stops_and_resets_active_key(self):
        active, _ = handle_key(self.controller, "w", None, 0.5, 0.25, 0.75)
        active, delay = handle_key(self.controller, " ", active, 0.5, 0.25, 0.75)
        self.assertEqual((active, delay), (None, 0.0))
        self.assertEqual(self.controller.calls[-1], ("stop",))

    def test_unmapped_key_does_not_change_motion_state(self):
        active, delay = handle_key(self.controller, "x", "w", 0.5, 0.25, 0.75)
        self.assertEqual((active, delay), ("w", None))
        self.assertEqual(self.controller.calls, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)

#!/usr/bin/env python3
"""Electrical-logic checks using gpiozero mock pins only; never real GPIO."""

import unittest

from gpiozero import Device, DigitalOutputDevice
from gpiozero.pins.mock import MockFactory, MockPWMPin

from motor_controller import MotorController


class ControllerTests(unittest.TestCase):
    def setUp(self):
        Device.pin_factory = MockFactory(pin_class=MockPWMPin)
        self.controller = MotorController(max_speed=0.30)

    def tearDown(self):
        self.controller.close()
        Device.pin_factory.close()

    def assert_outputs(self, right, left):
        pins = self.controller.pins
        factory = Device.pin_factory
        for speed, enable, in1, in2 in (
            (right, pins.right_enable, pins.right_in1, pins.right_in2),
            (left, pins.left_enable, pins.left_in1, pins.left_in2),
        ):
            self.assertAlmostEqual(factory.pin(enable).state, abs(speed))
            if speed:
                self.assertEqual(factory.pin(in1).state, speed > 0)
                self.assertEqual(factory.pin(in2).state, speed < 0)
            else:
                self.assertFalse(factory.pin(in1).state)
                self.assertFalse(factory.pin(in2).state)

    def test_initially_stopped(self):
        self.assert_outputs(0, 0)

    def test_directions_and_stop(self):
        for action, right, left in (
            ("forward", 0.2, 0.2),
            ("backward", -0.2, -0.2),
            ("left", 0.2, -0.2),
            ("right", -0.2, 0.2),
        ):
            with self.subTest(action=action):
                getattr(self.controller, action)(0.2)
                self.assert_outputs(right, left)
                self.controller.stop()
                self.assert_outputs(0, 0)

    def test_unsigned_and_signed_speed_limits(self):
        self.controller.forward(0.9)
        self.assert_outputs(0.3, 0.3)
        self.controller.set_wheel_speed(0.9, -0.9)
        self.assert_outputs(0.3, -0.3)

    def test_invalid_inputs_do_not_start(self):
        for value in (-0.1, 1.1, float("nan"), float("inf")):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.controller.forward(value)
                self.assert_outputs(0, 0)
        for value in (-1.1, 1.1, float("nan"), float("inf")):
            with self.subTest(signed=value):
                with self.assertRaises(ValueError):
                    self.controller.set_wheel_speed(value, 0.2)
                self.assert_outputs(0, 0)

    def test_close_is_repeatable_and_releases_pins(self):
        self.controller.forward(0.2)
        self.controller.close()
        self.controller.close()
        self.controller.stop()
        with self.assertRaises(RuntimeError):
            self.controller.forward(0.2)
        with self.assertRaises(RuntimeError):
            self.controller.set_wheel_speed(0.2, 0.2)
        self.controller = MotorController()
        self.assert_outputs(0, 0)

    def test_initialization_failure_releases_claimed_pins(self):
        self.controller.close()
        blocker = DigitalOutputDevice(26, initial_value=False)
        try:
            with self.assertRaises(Exception):
                MotorController()
        finally:
            blocker.close()
        self.controller = MotorController()
        self.assert_outputs(0, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

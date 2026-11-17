#!/usr/bin/env python3
"""Python 3 motor controller for the XiaoRGEEK/L298-style chassis.

The BCM mapping was verified against the original chassis wiring and vendor code. This
module uses gpiozero on Raspberry Pi OS Bookworm and does not touch GPIO until
``MotorController(dry_run=False)`` is constructed.
"""

from __future__ import annotations

import atexit
import math
from contextlib import suppress
from dataclasses import dataclass


@dataclass(frozen=True)
class MotorPins:
    """BCM pins used by the old XiaoRGEEK L298 wiring."""

    right_enable: int = 13
    left_enable: int = 20
    right_in1: int = 19
    right_in2: int = 16
    left_in1: int = 21
    left_in2: int = 26


@dataclass
class _MotorSide:
    enable: object
    forward: object
    backward: object


class MotorController:
    """Two-motor differential drive with bounded speed and safe stop."""

    def __init__(
        self,
        pins: MotorPins = MotorPins(),
        max_speed: float = 0.50,
        dry_run: bool = False,
    ) -> None:
        if not math.isfinite(max_speed) or not 0.0 < max_speed <= 1.0:
            raise ValueError("max_speed must be in (0, 1]")
        self.pins = pins
        self.max_speed = max_speed
        self.dry_run = dry_run
        self._right: _MotorSide | None = None
        self._left: _MotorSide | None = None
        self._closed = False
        self._last_command = "stop"
        self._devices = []

        if dry_run:
            return

        try:
            from gpiozero import DigitalOutputDevice, PWMOutputDevice
        except ImportError as exc:
            raise RuntimeError(
                "gpiozero is not installed. Install python3-gpiozero and "
                "python3-lgpio on Raspberry Pi OS Bookworm, or use --dry-run."
            ) from exc

        # The old board exposes separate L298 direction inputs and ENA/ENB
        # enable inputs.  PWM is therefore applied to the enable pins.
        def output(device_type, pin, **kwargs):
            device = device_type(pin, **kwargs)
            self._devices.append(device)
            return device

        try:
            # Disable both enables before claiming any direction pin.
            right_enable = output(PWMOutputDevice, pins.right_enable, frequency=1000, initial_value=0)
            left_enable = output(PWMOutputDevice, pins.left_enable, frequency=1000, initial_value=0)
            self._right = _MotorSide(
                enable=right_enable,
                forward=output(DigitalOutputDevice, pins.right_in1, initial_value=False),
                backward=output(DigitalOutputDevice, pins.right_in2, initial_value=False),
            )
            self._left = _MotorSide(
                enable=left_enable,
                forward=output(DigitalOutputDevice, pins.left_in1, initial_value=False),
                backward=output(DigitalOutputDevice, pins.left_in2, initial_value=False),
            )
            self.stop()
        except BaseException:
            for device in reversed(self._devices):
                with suppress(Exception):
                    device.close()
            self._closed = True
            raise
        atexit.register(self.close)

    def _bounded(self, speed: float) -> float:
        if not math.isfinite(speed) or not 0.0 <= speed <= 1.0:
            raise ValueError("speed must be between 0 and 1")
        return min(speed, self.max_speed)

    def _disable_outputs(self) -> None:
        if self.dry_run:
            return
        assert self._right is not None and self._left is not None
        self._right.enable.value = 0
        self._left.enable.value = 0

    def _set(self, action: str, right: float, left: float) -> None:
        if self._closed:
            if action == "stop":
                return
            raise RuntimeError("motor controller is closed")

        right = self._bounded(right)
        left = self._bounded(left)
        self._last_command = action
        if self.dry_run:
            print(f"[dry-run] {action}: right={right:.2f}, left={left:.2f}", flush=True)
            return

        assert self._right is not None and self._left is not None
        if action == "stop":
            self._disable_outputs()
            self._stop_side(self._right)
            self._stop_side(self._left)
            return

        # Remove PWM before changing direction to avoid reversing under power.
        self._disable_outputs()
        if action == "forward":
            self._drive_side(self._right, right)
            self._drive_side(self._left, left)
        elif action == "backward":
            self._drive_side(self._right, -right)
            self._drive_side(self._left, -left)
        elif action == "left":
            self._drive_side(self._right, right)
            self._drive_side(self._left, -left)
        elif action == "right":
            self._drive_side(self._right, -right)
            self._drive_side(self._left, left)
        else:
            raise ValueError(f"unknown action: {action}")

    @staticmethod
    def _drive_side(side: _MotorSide, signed_speed: float) -> None:
        if signed_speed >= 0:
            side.backward.off()
            side.forward.on()
        else:
            side.forward.off()
            side.backward.on()
        side.enable.value = abs(signed_speed)

    @staticmethod
    def _stop_side(side: _MotorSide) -> None:
        side.enable.value = 0
        side.forward.off()
        side.backward.off()

    def forward(self, speed: float = 0.50) -> None:
        self._set("forward", speed, speed)

    def backward(self, speed: float = 0.50) -> None:
        self._set("backward", speed, speed)

    def left(self, speed: float = 0.50) -> None:
        self._set("left", speed, speed)

    def right(self, speed: float = 0.50) -> None:
        self._set("right", speed, speed)

    def set_wheel_speed(self, right: float, left: float) -> None:
        """Set signed wheel speeds: positive forward, negative backward."""
        if (
            not math.isfinite(right)
            or not math.isfinite(left)
            or not -1.0 <= right <= 1.0
            or not -1.0 <= left <= 1.0
        ):
            raise ValueError("wheel speeds must be between -1 and 1")
        right = max(-self.max_speed, min(self.max_speed, right))
        left = max(-self.max_speed, min(self.max_speed, left))
        if self._closed:
            raise RuntimeError("motor controller is closed")
        if self.dry_run:
            print(f"[dry-run] wheels: right={right:.2f}, left={left:.2f}", flush=True)
            return
        assert self._right is not None and self._left is not None
        self._disable_outputs()
        self._drive_side(self._right, right)
        self._drive_side(self._left, left)
        self._last_command = "wheel_speed"

    def stop(self) -> None:
        self._set("stop", 0.0, 0.0)

    @property
    def last_command(self) -> str:
        return self._last_command

    def close(self) -> None:
        if self._closed:
            return
        try:
            self.stop()
        finally:
            for device in self._devices:
                with suppress(Exception):
                    device.close()
            self._devices.clear()
            self._right = None
            self._left = None
            self._closed = True
            if not self.dry_run:
                atexit.unregister(self.close)


# Names retained as a small compatibility layer for old scripts.
def Motor_Forward(controller: MotorController, speed: float = 0.50) -> None:
    controller.forward(speed)


def Motor_Backward(controller: MotorController, speed: float = 0.50) -> None:
    controller.backward(speed)


def Motor_TurnLeft(controller: MotorController, speed: float = 0.50) -> None:
    controller.left(speed)


def Motor_TurnRight(controller: MotorController, speed: float = 0.50) -> None:
    controller.right(speed)


def Motor_Stop(controller: MotorController) -> None:
    controller.stop()

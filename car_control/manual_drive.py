#!/usr/bin/env python3
"""Bounded keyboard drive for the Raspberry Pi car.

Keys: w=forward, s=backward, a=left, d=right, space=stop, q=quit.
The command times out and stops automatically if no key is received.
"""

from __future__ import annotations

import argparse
import math
import select
import signal
import sys
import time

if sys.platform != "win32":
    import termios
    import tty

from motor_controller import MotorController


def handle_key(controller, key, active_key, speed, timeout, startup_timeout):
    motion_keys = {
        "w": controller.forward,
        "s": controller.backward,
        "a": controller.left,
        "d": controller.right,
    }
    if key in motion_keys:
        if key != active_key:
            motion_keys[key](speed)
            return key, startup_timeout
        return active_key, timeout
    if key == " ":
        controller.stop()
        return None, 0.0
    return active_key, None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--speed", type=float, default=0.50, help="0..1; capped by --max-speed")
    parser.add_argument("--max-speed", type=float, default=0.50)
    parser.add_argument(
        "--timeout",
        type=float,
        default=0.25,
        help="stop after no key for this many seconds (SSH has no key-up event)",
    )
    parser.add_argument(
        "--startup-timeout",
        type=float,
        default=0.75,
        help="grace after the first direction key, allowing keyboard auto-repeat to begin",
    )
    parser.add_argument("--dry-run", action="store_true", help="do not access GPIO")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if sys.platform == "win32" and not args.dry_run:
        raise SystemExit("GPIO control must run on the Raspberry Pi; use --dry-run on Windows")
    if not math.isfinite(args.timeout) or not 0.1 <= args.timeout <= 2.0:
        raise SystemExit("--timeout must be between 0.1 and 2.0 seconds")
    if (
        not math.isfinite(args.startup_timeout)
        or not args.timeout <= args.startup_timeout <= 2.0
    ):
        raise SystemExit("--startup-timeout must be between --timeout and 2.0 seconds")
    if not math.isfinite(args.speed) or not 0 <= args.speed <= 1:
        raise SystemExit("--speed must be finite and between 0 and 1")
    controller = MotorController(max_speed=args.max_speed, dry_run=args.dry_run)
    old_settings = None
    if not args.dry_run and not sys.stdin.isatty():
        controller.close()
        raise SystemExit("manual_drive requires an interactive SSH terminal")

    def stop_on_signal(signum: int, _frame: object) -> None:
        # Convert shell hangup/termination into normal Python unwinding so the
        # finally block below can stop and release GPIO devices.
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, stop_on_signal)
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, stop_on_signal)

    try:
        if args.dry_run:
            print("[dry-run] no GPIO or keyboard control started; use run_motion.py to check actions", flush=True)
            return 0
        old_settings = termios.tcgetattr(sys.stdin)
        tty.setcbreak(sys.stdin.fileno())
        print("w前进 s后退 a左转 d右转 空格停车 q退出", flush=True)
        deadline = 0.0
        active_key = None
        while True:
            readable, _, _ = select.select([sys.stdin], [], [], 0.01)
            if readable:
                key = sys.stdin.read(1).lower()
                if not key or key == "q":
                    break
                active_key, key_timeout = handle_key(
                    controller,
                    key,
                    active_key,
                    args.speed,
                    args.timeout,
                    args.startup_timeout,
                )
                if key_timeout is not None:
                    deadline = time.monotonic() + key_timeout if key_timeout else 0.0
            if deadline and time.monotonic() >= deadline:
                controller.stop()
                deadline = 0.0
                active_key = None
    except KeyboardInterrupt:
        pass
    finally:
        try:
            controller.close()
        finally:
            if old_settings is not None:
                try:
                    termios.tcsetattr(sys.stdin, termios.TCSANOW, old_settings)
                except (termios.error, OSError):
                    pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

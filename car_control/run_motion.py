#!/usr/bin/env python3
"""Run one bounded movement action, then stop automatically."""

from __future__ import annotations

import argparse
import math
import signal
import time

from motor_controller import MotorController


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("forward", "backward", "left", "right", "stop"))
    parser.add_argument("--seconds", type=float, default=0.5)
    parser.add_argument("--speed", type=float, default=0.50)
    parser.add_argument("--max-speed", type=float, default=0.50)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not math.isfinite(args.seconds) or args.seconds < 0 or args.seconds > 10:
        parser.error("--seconds must be finite and between 0 and 10")
    if not math.isfinite(args.speed) or not 0 <= args.speed <= 1:
        parser.error("--speed must be finite and between 0 and 1")

    def stop_on_signal(signum: int, _frame: object) -> None:
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, stop_on_signal)
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, stop_on_signal)

    controller = MotorController(max_speed=args.max_speed, dry_run=args.dry_run)
    try:
        if args.action == "forward":
            controller.forward(args.speed)
        elif args.action == "backward":
            controller.backward(args.speed)
        elif args.action == "left":
            controller.left(args.speed)
        elif args.action == "right":
            controller.right(args.speed)
        else:
            controller.stop()
        if args.action != "stop":
            time.sleep(args.seconds)
    except KeyboardInterrupt:
        return 130
    finally:
        controller.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

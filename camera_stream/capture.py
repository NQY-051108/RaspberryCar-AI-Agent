#!/usr/bin/env python3
"""Periodic local JPEG capture with status, CSV metadata, pause marker and disk guard."""
import argparse
import csv
import json
import shutil
import signal
import time
from datetime import datetime
from pathlib import Path

import cv2

running = True


def request_stop(signum, frame):
    global running
    running = False


def atomic_json(path, data):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--interval", type=float, default=0.5)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--quality", type=int, default=90)
    parser.add_argument("--route", default="manual")
    parser.add_argument("--duration", type=float, default=0, help="seconds; 0 runs until Ctrl+C")
    parser.add_argument("--base", default=str(Path.home() / "car_data"))
    parser.add_argument("--min-free-gb", type=float, default=1.0)
    args = parser.parse_args()

    if args.interval <= 0:
        raise SystemExit("--interval must be positive")

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    session = Path(args.base).expanduser() / session_id
    images = session / "images"
    images.mkdir(parents=True, exist_ok=False)
    metadata_path = session / "metadata.csv"
    status_path = session / "status.json"
    pause_file = session / "PAUSE"

    count = 0
    last_file = ""
    final_state = "stopped"
    message = ""

    def update_status(state):
        disk = shutil.disk_usage(session)
        atomic_json(status_path, {
            "state": state,
            "count": count,
            "last_file": last_file,
            "session_dir": str(session),
            "free_bytes": disk.free,
            "free_gb": round(disk.free / (1024 ** 3), 2),
            "updated_at": datetime.now().isoformat(timespec="milliseconds"),
            "message": message,
        })

    cap = cv2.VideoCapture(args.camera, cv2.CAP_V4L2)
    if not cap.isOpened():
        final_state = "camera_open_failed"
        message = f"Could not open camera index {args.camera}"
        update_status(final_state)
        raise SystemExit(message)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)

    started = datetime.now()
    atomic_json(session / "run.json", {
        "session": session_id,
        "started_at": started.isoformat(timespec="milliseconds"),
        "route": args.route,
        "camera_index": args.camera,
        "requested_resolution": [args.width, args.height],
        "actual_resolution": [width, height],
        "camera_fps_reported": fps,
        "save_interval_seconds": args.interval,
    })

    print(f"Capture folder: {session}", flush=True)
    print(f"Camera {args.camera}; actual resolution {width}x{height}; reported FPS {fps}", flush=True)
    print(f"Pause: touch {pause_file}", flush=True)
    print(f"Resume: rm -f {pause_file}", flush=True)
    print("Stop: Ctrl+C", flush=True)

    start_clock = time.monotonic()
    next_save = start_clock
    read_failures = 0

    try:
        with metadata_path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(["index", "filename", "timestamp", "route", "width", "height"])
            update_status("running")

            while running:
                if args.duration > 0 and time.monotonic() - start_clock >= args.duration:
                    break

                disk = shutil.disk_usage(session)
                if disk.free < args.min_free_gb * (1024 ** 3):
                    final_state = "stopped_low_disk"
                    message = "Free space below configured limit"
                    print("Stopping: free disk space reached safety limit.", flush=True)
                    break

                ok, frame = cap.read()
                if not ok:
                    read_failures += 1
                    message = f"Consecutive camera read failures: {read_failures}"
                    update_status("camera_read_error")
                    if read_failures >= 10:
                        final_state = "stopped_camera_error"
                        print("Stopping after 10 consecutive camera read failures.", flush=True)
                        break
                    time.sleep(0.1)
                    continue

                read_failures = 0

                if pause_file.exists():
                    update_status("paused")
                    time.sleep(0.1)
                    continue

                now = time.monotonic()
                if now < next_save:
                    continue

                timestamp = datetime.now()
                filename = f"frame_{count + 1:06d}_{timestamp.strftime('%Y%m%dT%H%M%S_%f')}.jpg"
                destination = images / filename

                if not cv2.imwrite(str(destination), frame, [cv2.IMWRITE_JPEG_QUALITY, args.quality]):
                    final_state = "image_write_error"
                    message = f"Could not write {destination}"
                    print(message, flush=True)
                    break

                count += 1
                last_file = str(destination)
                message = ""
                writer.writerow([
                    count, filename, timestamp.isoformat(timespec="milliseconds"),
                    args.route, width, height
                ])
                file.flush()
                update_status("running")
                print(f"Saved {count}: {filename}", flush=True)
                next_save = now + args.interval

    finally:
        cap.release()
        update_status(final_state)
        print(f"Finished: {count} images; state={final_state}; folder={session}", flush=True)


if __name__ == "__main__":
    main()

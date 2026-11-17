#!/usr/bin/env python3
"""Raspberry Pi camera capture + TCP JPEG stream server.

The server opens one V4L2 camera, encodes frames as JPEG, optionally saves
periodic JPEGs locally, and sends length-prefixed frames to one Windows client.
It does not control motors.
"""
import argparse
import csv
import os
import signal
import socket
import struct
import time
from datetime import datetime
from pathlib import Path

import cv2

RUNNING = True
SAVE_ENABLED = False
SAVE_STATE_CHANGED = False
HEADER = struct.Struct("!I")


def stop_handler(signum, frame):
    global RUNNING
    RUNNING = False


def toggle_save_handler(signum, frame):
    """Toggle image saving while leaving camera capture and streaming active."""
    global SAVE_ENABLED, SAVE_STATE_CHANGED
    SAVE_ENABLED = not SAVE_ENABLED
    SAVE_STATE_CHANGED = True


def send_frame(conn, jpeg_bytes):
    conn.sendall(HEADER.pack(len(jpeg_bytes)))
    conn.sendall(jpeg_bytes)


def main():
    global SAVE_ENABLED, SAVE_STATE_CHANGED
    parser = argparse.ArgumentParser()
    parser.add_argument("--camera", type=int, default=0, help="V4L2 camera index, normally 0")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=float, default=10.0, help="maximum stream FPS")
    parser.add_argument("--jpeg-quality", type=int, default=80)
    parser.add_argument("--host", default="0.0.0.0", help="listen address")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--save-dir", default="", help="optional local JPEG directory; empty disables saving")
    parser.add_argument("--save-interval", type=float, default=0.5)
    args = parser.parse_args()

    if not 1 <= args.jpeg_quality <= 100:
        raise SystemExit("--jpeg-quality must be 1..100")
    if args.fps <= 0 or args.save_interval <= 0:
        raise SystemExit("--fps and --save-interval must be positive")

    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)

    save_dir = None
    csv_file = None
    csv_writer = None
    if args.save_dir:
        save_dir = Path(args.save_dir).expanduser()
        save_dir.mkdir(parents=True, exist_ok=True)
        csv_file = (save_dir / "metadata.csv").open("w", newline="", encoding="utf-8")
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow(["index", "filename", "timestamp", "width", "height"])
        if not hasattr(signal, "SIGUSR1"):
            csv_file.close()
            raise SystemExit("Runtime pause/resume requires a Linux system with SIGUSR1")
        SAVE_ENABLED = True
        SAVE_STATE_CHANGED = False
        signal.signal(signal.SIGUSR1, toggle_save_handler)

    cap = cv2.VideoCapture(args.camera, cv2.CAP_V4L2)
    if not cap.isOpened():
        if csv_file:
            csv_file.close()
        raise SystemExit(
            f"Cannot open camera index {args.camera}; check /dev/video* and camera ownership"
        )

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    camera_fps = cap.get(cv2.CAP_PROP_FPS)

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((args.host, args.port))
    server.listen(1)
    server.settimeout(1.0)

    print(f"Camera: /dev/video{args.camera}, {width}x{height}, reported FPS={camera_fps}", flush=True)
    print(f"Listening on {args.host}:{args.port}", flush=True)
    print(f"Server PID: {os.getpid()}", flush=True)
    print("Start the Windows client now. Press Ctrl+C here to stop.", flush=True)
    if save_dir:
        print(f"Local JPEG saving: {save_dir}", flush=True)
        print("In another SSH window, send SIGUSR1 to this PID to pause/resume image saving.", flush=True)

    next_send = 0.0
    next_save = 0.0
    frame_index = 0
    saved_index = 0

    try:
        while RUNNING:
            try:
                conn, address = server.accept()
            except socket.timeout:
                continue

            print(f"Client connected: {address}", flush=True)
            conn.settimeout(5.0)
            next_send = 0.0
            try:
                while RUNNING:
                    if SAVE_STATE_CHANGED:
                        state = "resumed" if SAVE_ENABLED else "paused"
                        print(f"Image saving {state}", flush=True)
                        SAVE_STATE_CHANGED = False

                    ok, frame = cap.read()
                    if not ok:
                        print("Camera read failed; retrying", flush=True)
                        time.sleep(0.1)
                        continue

                    now = time.monotonic()
                    if now < next_send:
                        continue

                    timestamp = datetime.now()
                    encoded, buffer = cv2.imencode(
                        ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, args.jpeg_quality]
                    )
                    if not encoded:
                        print("JPEG encoding failed", flush=True)
                        continue
                    jpeg_bytes = buffer.tobytes()

                    if save_dir and SAVE_ENABLED and now >= next_save:
                        saved_index += 1
                        filename = (
                            f"frame_{saved_index:06d}_"
                            f"{timestamp.strftime('%Y%m%dT%H%M%S_%f')}.jpg"
                        )
                        path = save_dir / filename
                        path.write_bytes(jpeg_bytes)
                        csv_writer.writerow([
                            saved_index,
                            filename,
                            timestamp.isoformat(timespec="milliseconds"),
                            width,
                            height,
                        ])
                        csv_file.flush()
                        next_save = now + args.save_interval

                    send_frame(conn, jpeg_bytes)
                    frame_index += 1
                    next_send = now + 1.0 / args.fps
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, TimeoutError, socket.timeout):
                print("Client disconnected", flush=True)
            finally:
                conn.close()

    finally:
        server.close()
        cap.release()
        if csv_file:
            csv_file.close()
        print(f"Stopped. Stream frames sent: {frame_index}; local images saved: {saved_index}", flush=True)


if __name__ == "__main__":
    main()

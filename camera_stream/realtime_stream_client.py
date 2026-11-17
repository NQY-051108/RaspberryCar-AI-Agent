#!/usr/bin/env python3
"""Windows OpenCV client for realtime_stream_server.py."""
import argparse
import socket
import struct
import time

import cv2
import numpy as np

HEADER = struct.Struct("!I")


def recv_exact(sock, size):
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            return None
        data.extend(chunk)
    return bytes(data)


def open_connection(host, port, timeout):
    sock = socket.create_connection((host, port), timeout=timeout)
    sock.settimeout(timeout)
    print(f"Connected to {host}:{port}", flush=True)
    return sock


def show_status(window, message):
    image = np.zeros((120, 640, 3), dtype=np.uint8)
    cv2.putText(image, message[:72], (15, 55), cv2.FONT_HERSHEY_SIMPLEX,
                0.55, (0, 220, 255), 1, cv2.LINE_AA)
    cv2.putText(image, "q / Esc: quit", (15, 90), cv2.FONT_HERSHEY_SIMPLEX,
                0.5, (220, 220, 220), 1, cv2.LINE_AA)
    cv2.imshow(window, image)
    return (cv2.waitKey(1) & 0xFF) in (ord("q"), 27)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True, help="Raspberry Pi IP, e.g. 192.168.88.100")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--window", default="Raspberry Pi Camera")
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--reconnect-delay", type=float, default=1.0)
    args = parser.parse_args()

    if args.timeout <= 0 or args.reconnect_delay <= 0:
        raise SystemExit("--timeout and --reconnect-delay must be positive")

    sock = None
    print("Press q or Esc in the video window to exit.")

    frames = 0
    start = time.monotonic()
    last_report = start
    try:
        while True:
            if sock is None:
                if show_status(args.window, f"Connecting to {args.host}:{args.port}..."):
                    break
                try:
                    sock = open_connection(args.host, args.port, args.timeout)
                except (OSError, TimeoutError) as exc:
                    print(f"Waiting for Pi stream: {exc}", flush=True)
                    if show_status(args.window, f"Pi stream unavailable: {exc}"):
                        break
                    time.sleep(args.reconnect_delay)
                    continue

            try:
                header = recv_exact(sock, HEADER.size)
                if header is None:
                    raise ConnectionError("Pi closed the stream")
                size = HEADER.unpack(header)[0]
                if size <= 0 or size > 10 * 1024 * 1024:
                    raise ValueError(f"Invalid JPEG packet size: {size}")

                payload = recv_exact(sock, size)
                if payload is None:
                    raise ConnectionError("Incomplete JPEG packet")
            except OSError as exc:
                print(f"Stream disconnected: {exc}; retrying in {args.reconnect_delay:g}s", flush=True)
                sock.close()
                sock = None
                if show_status(args.window, "Stream disconnected; reconnecting..."):
                    break
                time.sleep(args.reconnect_delay)
                continue

            image = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                print("Skipped an invalid JPEG frame")
                continue

            frames += 1
            now = time.monotonic()
            if now - last_report >= 1.0:
                fps = frames / max(now - start, 1e-6)
                cv2.putText(
                    image,
                    f"stream {fps:.1f} FPS | frames {frames} | q/Esc: quit",
                    (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (0, 255, 0),
                    2,
                    cv2.LINE_AA,
                )
                last_report = now

            cv2.imshow(args.window, image)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
    except KeyboardInterrupt:
        print("Interrupted by user", flush=True)
    finally:
        if sock is not None:
            sock.close()
        cv2.destroyAllWindows()
        print(f"Exited after {frames} frames")


if __name__ == "__main__":
    main()

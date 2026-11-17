#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
树莓派摄像头实时 YOLOv8 检测（浏览器查看，无需显示器/桌面）
----------------------------------------------------------
用法：
  ~/pi_venv/bin/python pi_camera_demo.py --model best_320.onnx
  ~/pi_venv/bin/python pi_camera_demo.py --model best_416.onnx --camera 0 --width 640 --height 480 --port 8080

运行后：
  * 树莓派本机浏览器打开  http://localhost:8080
  * PC/手机浏览器打开      http://<树莓派IP>:8080
  页面里是摄像头实时画面 + YOLOv8 检测框/标签/FPS。

其他：
  --save out.mp4   同时录制带框视频
  Ctrl+C 退出
"""
import argparse
import json
import os
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from pi_infer import detect, draw, load_names, make_session  # noqa: E402


def lan_ip():
    # 优先用 hostname -I（离网环境也能拿到局域网 IP）
    try:
        out = os.popen("hostname -I 2>/dev/null").read().strip().split()
        for ip in out:
            if ip and not ip.startswith("127."):
                return ip
    except Exception:  # noqa: BLE001
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.168.88.1", 80))
        ip = s.getsockname()[0]
        s.close()
        if not ip.startswith("127."):
            return ip
    except OSError:
        pass
    try:
        ip = socket.gethostbyname(socket.gethostname())
        if not ip.startswith("127."):
            return ip
    except OSError:
        pass
    return "127.0.0.1"


def open_camera(index, width, height, fps, fourcc):
    cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
    if not cap.isOpened():
        cap.release()
        return None
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)
    if fourcc:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
    ok, frame = cap.read()
    if not ok:
        cap.release()
        return None
    h, w = frame.shape[:2]
    print("[camera] opened /dev/video%d  %dx%d (requested %dx%d @%d)" % (index, w, h, width, height, fps))
    return cap


class Pipeline:
    """后台线程：读摄像头 -> 推理 -> 画框 -> 编码 JPEG。"""

    def __init__(self, args, session, names):
        self.args = args
        self.session = session
        self.names = names
        self.cap = open_camera(args.camera, args.width, args.height, args.fps, args.fourcc)
        self.lock = threading.Lock()
        self.jpeg = None
        self.stats = {"fps": 0.0, "infer_ms": 0.0, "detections": 0, "uptime": 0}
        self.running = True
        self.writer = None
        self.t0 = time.time()
        self.n = 0

    def run(self):
        while self.running:
            ok, frame = self.cap.read()
            if not ok:
                time.sleep(0.05)
                continue
            boxes, scores, cls_ids, tm = detect(
                self.session, frame, self.names, self.args.conf, self.args.iou)
            draw(frame, boxes, scores, cls_ids, self.names)
            self.n += 1
            fps = self.n / max(time.time() - self.t0, 1e-6)
            hud = "FPS %.1f | infer %.0f ms | det %d" % (
                fps, tm["infer"] * 1000, len(boxes))
            cv2.putText(frame, hud, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            if self.args.save:
                if self.writer is None:
                    h, w = frame.shape[:2]
                    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                    self.writer = cv2.VideoWriter(self.args.save, fourcc, max(fps, 1.0), (w, h))
                self.writer.write(frame)
            ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.args.quality])
            if ok:
                with self.lock:
                    self.jpeg = buf.tobytes()
                    self.stats = {"fps": round(fps, 1), "infer_ms": round(tm["infer"] * 1000, 1),
                                  "detections": len(boxes), "uptime": int(time.time() - self.t0)}
            time.sleep(0.001)

    def close(self):
        self.running = False
        try:
            self.cap.release()
        except Exception:  # noqa: BLE001
            pass
        if self.writer is not None:
            self.writer.release()


PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>YOLOv8 Pi Camera</title>
<style>
 body{margin:0;background:#111;color:#eee;font-family:Arial,sans-serif;text-align:center}
 h2{margin:10px 0 4px} #info{font-size:14px;color:#8f8}
 img{max-width:100%;height:auto;border:2px solid #333;margin-top:8px}
</style></head><body>
<h2>YOLOv8 交通标志实时检测 (Raspberry Pi)</h2>
<div id="info">connecting...</div>
<img src="/stream">
<script>
setInterval(async()=>{
 try{const r=await fetch('/stats');const j=await r.json();
  document.getElementById('info').textContent =
   `FPS ${j.fps} | 推理 ${j.infer_ms} ms | 目标 ${j.detections} 个 | 已运行 ${j.uptime} s`;}
 catch(e){}
},1000);
</script></body></html>
"""


class Handler(BaseHTTPRequestHandler):
    pipeline = None

    def log_message(self, fmt, *args):  # 安静一点
        pass

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/stats":
            with self.pipeline.lock:
                body = json.dumps(self.pipeline.stats).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/snapshot.jpg":
            with self.pipeline.lock:
                frame = self.pipeline.jpeg
            if frame is None:
                self.send_error(503, "no frame yet")
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(frame)))
            self.end_headers()
            self.wfile.write(frame)
        elif self.path == "/stream":
            self.send_response(200)
            self.send_header("Age", "0")
            self.send_header("Cache-Control", "no-cache, private")
            self.send_header("Pragma", "no-cache")
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()
            try:
                while self.pipeline.running:
                    with self.pipeline.lock:
                        frame = self.pipeline.jpeg
                    if frame is None:
                        time.sleep(0.05)
                        continue
                    self.wfile.write(b"--frame\r\n")
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(("Content-Length: %d\r\n\r\n" % len(frame)).encode())
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
                    time.sleep(0.01)
            except (BrokenPipeError, ConnectionResetError):
                pass
        else:
            self.send_error(404)


def main():
    ap = argparse.ArgumentParser(description="YOLOv8 camera demo on Raspberry Pi (web stream)")
    ap.add_argument("--model", default="best_320.onnx", help="best_640/416/320.onnx")
    ap.add_argument("--camera", type=int, default=0, help="摄像头编号（/dev/videoN）")
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--fourcc", default="MJPG", help="摄像头格式：MJPG 通常更快；留空用默认")
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--iou", type=float, default=0.45)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--quality", type=int, default=80, help="JPEG 质量 1-100")
    ap.add_argument("--save", default="", help="同时录制 mp4（如 out.mp4）")
    ap.add_argument("--names", default=os.path.join(HERE, "class_names.txt"))
    args = ap.parse_args()

    if not os.path.isfile(args.model) and not os.path.isabs(args.model):
        args.model = os.path.join(HERE, args.model)
    names = load_names(args.names)
    print("=" * 74)
    print("YOLOv8 实时检测 (web)")
    print("  model :", args.model)
    print("  camera: /dev/video%d  %dx%d @%d  fourcc=%s" % (args.camera, args.width, args.height, args.fps, args.fourcc))
    print("=" * 74)

    session = make_session(args.model, args.threads)
    pipe = Pipeline(args, session, names)
    if pipe.cap is None:
        print("[错误] 摄像头打不开 /dev/video%d，先运行: ~/pi_venv/bin/python pi_camera_test.py" % args.camera)
        return 1
    th = threading.Thread(target=pipe.run, daemon=True)
    th.start()

    Handler.pipeline = pipe
    server = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    ip = lan_ip()
    print("\n浏览器打开:")
    print("  本机 : http://localhost:%d/" % args.port)
    print("  局域网: http://%s:%d/" % (ip, args.port))
    print("\nCtrl+C 退出\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[退出]")
    finally:
        pipe.close()
        server.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())

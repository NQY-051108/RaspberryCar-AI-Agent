#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
树莓派摄像头自检脚本
--------------------
在部署包里先运行本脚本，确认 USB 摄像头能被 OpenCV 打开：
    ~/pi_venv/bin/python pi_camera_test.py

会依次尝试 /dev/video0~3 的 V4L2 设备，打印分辨率/帧率，并保存抓拍图
（camera_test_0.jpg 等），方便判断摄像头是否正常。
"""
import glob
import os
import sys
import time

import cv2


def list_video_nodes():
    nodes = sorted(glob.glob("/sys/class/video4linux/video*"))
    out = []
    for n in nodes:
        name_file = os.path.join(n, "name")
        name = open(name_file).read().strip() if os.path.isfile(name_file) else "?"
        out.append((os.path.basename(n), name))
    return out


def try_open(index, fourcc=None):
    """尝试打开摄像头并读 10 帧，返回 (ok, 信息字符串)。"""
    cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
    if not cap.isOpened():
        cap.release()
        return False, "打不开"
    try:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 30)
        if fourcc:
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
        ok, frame = cap.read()
        if not ok or frame is None:
            return False, "能打开但读不到画面"
        n, t0 = 0, time.time()
        while n < 10:
            ok, frame = cap.read()
            if not ok:
                break
            n += 1
        dt = time.time() - t0
        h, w = frame.shape[:2]
        fps = n / dt if dt > 0 else 0
        fourcc_val = int(cap.get(cv2.CAP_PROP_FOURCC))
        fourcc_str = "".join([chr((fourcc_val >> (8 * i)) & 0xFF) for i in range(4)])
        out_name = "camera_test_%d.jpg" % index
        cv2.imwrite(out_name, frame)
        cap.release()
        return True, "分辨率 %dx%d | 实测 %.1f FPS | fourcc=%s | 抓拍已保存 %s" % (w, h, fps, fourcc_str, out_name)
    finally:
        cap.release()


def main():
    print("=" * 74)
    print("树莓派摄像头自检")
    print("=" * 74)
    try:
        import onnxruntime  # noqa: F401
        print("onnxruntime: 已安装")
    except Exception as e:  # noqa: BLE001
        print("onnxruntime: 未安装（%s）" % e)
    print("opencv     :", cv2.__version__)
    print("video 节点 :")
    nodes = list_video_nodes()
    for dev, name in nodes[:8]:
        print("  %-10s %s" % (dev, name))
    if not nodes:
        print("  （无 /dev/video*：请确认 USB 摄像头已插好）")

    print("-" * 74)
    found = []
    # 优先尝试 0 号（通常就是 USB 摄像头），再试 1~3
    for idx in (0, 1, 2, 3):
        for fourcc in ("MJPG", None):
            ok, info = try_open(idx, fourcc)
            tag = "MJPG" if fourcc else "默认格式"
            print("/dev/video%d (%s): %s" % (idx, tag, info))
            if ok:
                found.append((idx, tag, info))
                break
    print("-" * 74)
    if found:
        print("结论：摄像头可用 ✔")
        for idx, tag, info in found:
            print("  camera=%d (%s) %s" % (idx, tag, info))
        print("\n下一步运行实时检测（浏览器查看）:")
        print("  ~/pi_venv/bin/python pi_camera_demo.py --model best_320.onnx --camera %d --port 8080" % found[0][0])
        return 0
    print("结论：没有能打开的摄像头 ✘")
    print("排查建议：")
    print("  1) 确认摄像头插在 USB 口、lsusb 能看到；")
    print("  2) 确认当前用户有 video 权限（id 命令查看，应为 groups 里包含 video）；")
    print("  3) 如果是 CSI 排线摄像头，不能用 OpenCV 直接打开，需要用 picamera2；")
    print("  4) 换个 USB 口 / 换根线 / 重启后再试。")
    return 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
树莓派部署环境自检
------------------
把 pi_deploy.zip 解压到树莓派后，先运行本脚本，确认软硬件都满足要求：
    python3 pi_check_env.py

检查项：64 位架构 / Python / 磁盘 / onnxruntime / OpenCV / 模型文件 /
        模型推理 / 摄像头设备 / 树莓派摄像头工具 / 供电/温度/CPU。
"""
import glob
import os
import platform
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
results = []


def run(cmd, timeout=8):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True,
                              timeout=timeout).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def add(name, ok, detail=""):
    results.append((name, ok, detail))
    print("[%s] %-34s %s" % ("PASS" if ok else "FAIL", name, detail))


print("=" * 74)
print("树莓派部署环境自检")
print("=" * 74)

# 1) 架构
machine = platform.machine()
is_aarch64 = machine in ("aarch64", "arm64")
add("64-bit OS (aarch64)", is_aarch64, machine)

# 2) OS / Python
osrel = {}
try:
    for line in open("/etc/os-release"):
        if "=" in line:
            k, v = line.strip().split("=", 1)
            osrel[k] = v.strip('"')
except OSError:
    pass
add("OS version", True, "%s %s" % (osrel.get("NAME", "?"), osrel.get("VERSION", "?")))
pv = platform.python_version()
add("Python >= 3.9", sys.version_info >= (3, 9), pv)

# 3) 磁盘
try:
    total, used, free = shutil.disk_usage("/")
    add("free disk > 500MB", free > 500 * 1024 * 1024, "%.1f GB free" % (free / 1e9))
except OSError as e:
    add("free disk", False, str(e))

# 4) onnxruntime / opencv
try:
    import onnxruntime as ort
    add("onnxruntime", True, ort.__version__)
except Exception as e:  # noqa: BLE001
    add("onnxruntime", False, "未安装：pip install onnxruntime -i https://pypi.tuna.tsinghua.edu.cn/simple (%s)" % e)
try:
    import cv2
    add("opencv (cv2)", True, cv2.__version__)
except Exception as e:  # noqa: BLE001
    add("opencv (cv2)", False, "未安装：sudo apt install -y python3-opencv (%s)" % e)

# 5) 模型文件
models = [m for m in ("best_640.onnx", "best_416.onnx", "best_320.onnx")
          if os.path.isfile(os.path.join(HERE, m))]
add("ONNX models present", len(models) > 0, ", ".join(models))

# 6) 推理冒烟测试（用 320 模型 + 样例图）
infer_ok, infer_msg = False, ""
try:
    sys.path.insert(0, HERE)
    from pi_infer import detect, imread_unicode, load_names, make_session
    names = load_names(os.path.join(HERE, "class_names.txt"))
    sample_dir = os.path.join(HERE, "sample_images")
    imgs = glob.glob(os.path.join(sample_dir, "*.jpg")) or glob.glob(os.path.join(sample_dir, "*.png"))
    model = os.path.join(HERE, "best_320.onnx" if os.path.isfile(os.path.join(HERE, "best_320.onnx")) else models[0])
    if imgs and names:
        sess = make_session(model, 4)
        img = imread_unicode(imgs[0])
        t0 = time.time()
        for _ in range(3):  # warmup
            detect(sess, img, names, 0.25, 0.45)
        t1 = time.time()
        for _ in range(10):
            boxes, scores, cls_ids, tm = detect(sess, img, names, 0.25, 0.45)
        t2 = time.time()
        infer_ok = True
        infer_msg = "%s | warmup %.2fs, 10 次平均 %.1f ms/帧 (~%.1f FPS)" % (
            os.path.basename(model), t1 - t0, (t2 - t1) / 10 * 1000, 10 / (t2 - t1))
except Exception as e:  # noqa: BLE001
    infer_msg = str(e)[:160]
add("model inference smoke test", infer_ok, infer_msg)

# 7) 摄像头
video_devs = sorted(glob.glob("/dev/video*"))
add("video devices (/dev/video*)", len(video_devs) > 0, ", ".join(video_devs[:6]) or "无（USB 摄像头未接入？CSI 摄像头不出现 /dev/video* 是正常的）")
cam_tools = [t for t in ("rpicam-hello", "libcamera-hello", "rpicam-still", "libcamera-still") if shutil.which(t)]
add("CSI camera tools (info)", True, (", ".join(cam_tools) or "无") + "（USB 摄像头用下面的 OpenCV 检查）")

# 7b) OpenCV 打开 USB 摄像头（rpicam 对 UVC 摄像头可能报 no cameras available，这是正常的）
cam_ok, cam_msg = False, ""
try:
    import cv2 as _cv
    for idx in (0, 1, 2):
        cap = _cv.VideoCapture(idx, _cv.CAP_V4L2)
        if not cap.isOpened():
            cap.release()
            continue
        ok, frame = cap.read()
        if ok and frame is not None:
            h, w = frame.shape[:2]
            snap = os.path.join(HERE, "camera_test_%d.jpg" % idx)
            _cv.imwrite(snap, frame)
            cam_ok = True
            cam_msg = "camera=%d %dx%d，抓拍已存 %s" % (idx, w, h, os.path.basename(snap))
        cap.release()
        if cam_ok:
            break
    if not cam_ok:
        cam_msg = "打不开 /dev/video*，先运行 pi_camera_test.py 排查"
except Exception as e:  # noqa: BLE001
    cam_msg = str(e)[:120]
add("USB camera capture (OpenCV)", cam_ok, cam_msg)

# 8) 供电 / 温度
throttled = run("vcgencmd get_throttled")
if throttled:
    add("power OK (throttled=0x0)", throttled.endswith("0x0"), throttled)
temp = run("vcgencmd measure_temp") or run("cat /sys/class/thermal/thermal_zone0/temp")
if temp:
    try:
        tval = float(temp.replace("temp=", "").replace("'C", "").strip())
        if tval > 1000:
            tval /= 1000.0
        add("temperature < 75C", tval < 75, "%.1f C" % tval)
    except ValueError:
        add("temperature", True, temp)
else:
    add("temperature", True, "n/a")

# 9) CPU / governor
add("CPU cores", True, str(os.cpu_count()))
gov = run("cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
if gov:
    add("CPU governor", True, gov + ("（想跑满可改 performance）" if gov != "performance" else "（performance）"))

# 汇总
print("=" * 74)
fails = [r for r in results if not r[1]]
print("结果：%d 项通过，%d 项失败" % (len(results) - len(fails), len(fails)))
if fails:
    print("\n需要处理：")
    for name, _, detail in fails:
        print("  - %-32s %s" % (name, detail))
    print("\n处理完后重新运行: python3 pi_check_env.py")
    sys.exit(1)
print("\n全部通过 ✔ 可以开始: python3 pi_benchmark.py --images sample_images --threads 1,2,4")

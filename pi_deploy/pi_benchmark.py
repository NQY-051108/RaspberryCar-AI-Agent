#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
树莓派端推理性能基准测试（ONNX Runtime / CPU）
------------------------------------------------
在树莓派上对比 best_640.onnx / best_416.onnx / best_320.onnx 以及不同线程数的
延迟和帧率，用来决定最终部署用哪个输入尺寸。

用法：
  python3 pi_benchmark.py --images sample_images
  python3 pi_benchmark.py --images sample_images --models best_640.onnx best_416.onnx best_320.onnx --threads 1,2,4
  python3 pi_benchmark.py --images sample_images --repeats 2
"""
import argparse
import os
import platform
import sys
import time

import cv2
import numpy as np
import onnxruntime as ort

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pi_infer import collect_sources, detect, imread_unicode, load_names, make_session  # noqa: E402


def bench_model(model, images, names, threads, conf, iou, repeats):
    session = make_session(model, threads)
    inp = session.get_inputs()[0]
    print("\n" + "=" * 74)
    print("model: %s | input: %s %s | threads: %d" % (model, inp.name, inp.shape, threads))
    print("=" * 74)
    lat = {"pre": [], "infer": [], "post": [], "total": []}
    # warmup
    for _ in range(2):
        for img in images[:2]:
            detect(session, img, names, conf, iou)
    for _ in range(repeats):
        for img in images:
            _, _, _, tm = detect(session, img, names, conf, iou)
            for k in lat:
                lat[k].append(tm[k])
    n = len(lat["total"])
    a = {k: np.array(v) * 1000 for k, v in lat.items()}
    for k in ("pre", "infer", "post", "total"):
        print("  %-6s mean %7.1f ms | p95 %7.1f ms | max %7.1f ms"
              % (k, a[k].mean(), np.percentile(a[k], 95), a[k].max()))
    print("  -> 单帧平均总延迟 %.1f ms = 理论最高 %.1f FPS（%d 次采样）"
          % (a["total"].mean(), 1000.0 / a["total"].mean(), n))
    return a["total"].mean()


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", default=os.path.join(here, "sample_images"), help="测试图片目录")
    ap.add_argument("--models", nargs="+",
                    default=["best_640.onnx", "best_416.onnx", "best_320.onnx"])
    ap.add_argument("--threads", default="4", help="逗号分隔，例如 1,2,4")
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--iou", type=float, default=0.45)
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--names", default=os.path.join(here, "class_names.txt"))
    args = ap.parse_args()

    names = load_names(args.names)
    files = collect_sources(args.images)
    images = []
    for f in files:
        img = imread_unicode(f)
        if img is not None:
            images.append(img)
    if not images:
        print("[错误] 测试图片为空:", args.images)
        return 1

    print("=" * 74)
    print("树莓派端推理基准测试")
    print("=" * 74)
    print("OS        :", platform.platform())
    print("CPU cores :", os.cpu_count())
    print("onnxruntime:", ort.__version__)
    print("opencv    :", cv2.__version__)
    print("images    : %d 张（%s）" % (len(images), args.images))

    thread_list = [int(t) for t in str(args.threads).split(",") if t.strip()]
    results = []
    for m in args.models:
        model = m if os.path.isabs(m) else os.path.join(here, m)
        if not os.path.isfile(model):
            print("[跳过] 模型不存在:", model)
            continue
        for t in thread_list:
            mean_ms = bench_model(model, images, names, t, args.conf, args.iou, args.repeats)
            results.append((os.path.basename(model), t, mean_ms, 1000.0 / mean_ms))

    print("\n" + "=" * 74)
    print("汇总（均值）")
    print("=" * 74)
    print("%-18s %8s %12s %10s" % ("model", "threads", "latency(ms)", "max FPS"))
    for name, t, ms, fps in sorted(results, key=lambda x: x[2]):
        print("%-18s %8d %12.1f %10.1f" % (name, t, ms, fps))
    return 0


if __name__ == "__main__":
    sys.exit(main())

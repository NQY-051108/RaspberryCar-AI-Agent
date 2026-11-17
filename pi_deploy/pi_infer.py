#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
树莓派端 YOLOv8 交通标志推理脚本（ONNX Runtime，无需 PyTorch / ultralytics）
--------------------------------------------------------------------------
用法示例：
  # 单张图片 / 整个文件夹，保存带框结果
  python3 pi_infer.py --model best_640.onnx --source sample_images --save out
  # 指定置信度/IOU
  python3 pi_infer.py --model best_416.onnx --source test.jpg --conf 0.3 --iou 0.45 --save out
  # USB 摄像头实时检测（Ctrl+C 退出）
  python3 pi_infer.py --model best_320.onnx --source 0 --show

输出：终端打印每帧 FPS 和检测到的目标（类别/置信度/框），可选保存图片。
"""
import argparse
import os
import sys
import time

import cv2
import numpy as np
import onnxruntime as ort

IMG_EXTS = (".jpg", ".jpeg", ".png", ".bmp")
PAD_VALUE = 114


def imread_unicode(path):
    """安全读图：用 imdecode 读文件，避免 OpenCV 在 Linux 上处理中文/非 UTF-8 文件名时崩溃。"""
    try:
        buf = np.fromfile(path, dtype=np.uint8)
        if buf.size == 0:
            return None
        return cv2.imdecode(buf, cv2.IMREAD_COLOR)
    except Exception:  # noqa: BLE001
        return None


def imwrite_unicode(path, img):
    """安全写图：先 imencode 再写文件，支持中文/非 ASCII 文件名。"""
    try:
        ext = os.path.splitext(path)[1] or ".jpg"
        ok, buf = cv2.imencode(ext, img)
        if ok:
            with open(path, "wb") as f:
                f.write(buf.tobytes())
        return ok
    except Exception:  # noqa: BLE001
        return False



def load_names(path):
    if path and os.path.isfile(path):
        return [l.strip() for l in open(path, encoding="utf-8") if l.strip()]
    return []


def letterbox(img, new_shape, color=(PAD_VALUE, PAD_VALUE, PAD_VALUE)):
    """等比缩放 + 居中填充，返回 (图像, 缩放比, pad_x, pad_y)。"""
    h, w = img.shape[:2]
    if isinstance(new_shape, int):
        new_shape = (new_shape, new_shape)
    r = min(new_shape[0] / h, new_shape[1] / w)
    new_w, new_h = int(round(w * r)), int(round(h * r))
    if (w, h) != (new_w, new_h):
        img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    dw, dh = new_shape[1] - new_w, new_shape[0] - new_h
    pad_x, pad_y = dw // 2, dh // 2
    img = cv2.copyMakeBorder(img, pad_y, dh - pad_y, pad_x, dw - pad_x,
                             cv2.BORDER_CONSTANT, value=color)
    return img, r, pad_x, pad_y


def xywh2xyxy(boxes):
    out = np.empty_like(boxes)
    out[:, 0] = boxes[:, 0] - boxes[:, 2] / 2
    out[:, 1] = boxes[:, 1] - boxes[:, 3] / 2
    out[:, 2] = boxes[:, 0] + boxes[:, 2] / 2
    out[:, 3] = boxes[:, 1] + boxes[:, 3] / 2
    return out


def nms(boxes, scores, iou_thr):
    """纯 numpy NMS，返回保留索引。"""
    if len(boxes) == 0:
        return np.array([], dtype=np.int64)
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)
    order = scores.argsort()[::-1]
    keep = []
    while order.size:
        i = order[0]
        keep.append(i)
        if order.size == 1:
            break
        rest = order[1:]
        xx1 = np.maximum(x1[i], x1[rest])
        yy1 = np.maximum(y1[i], y1[rest])
        xx2 = np.minimum(x2[i], x2[rest])
        yy2 = np.minimum(y2[i], y2[rest])
        inter = np.maximum(0.0, xx2 - xx1) * np.maximum(0.0, yy2 - yy1)
        iou = inter / (areas[i] + areas[rest] - inter + 1e-9)
        order = rest[iou <= iou_thr]
    return np.array(keep, dtype=np.int64)


def make_session(model_path, threads):
    so = ort.SessionOptions()
    so.intra_op_num_threads = threads
    so.inter_op_num_threads = 1
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    return ort.InferenceSession(model_path, sess_options=so, providers=["CPUExecutionProvider"])


def detect(session, img, names, conf_thr, iou_thr, input_size=None):
    """对一张 BGR 图做检测，返回 (boxes_xyxy, scores, class_ids, 各阶段耗时dict)。"""
    inp = session.get_inputs()[0]
    in_shape = inp.shape  # [1,3,H,W]
    ih, iw = (int(in_shape[2]), int(in_shape[3])) if isinstance(in_shape[2], int) else (input_size, input_size)

    t0 = time.perf_counter()
    padded, ratio, pad_x, pad_y = letterbox(img, (ih, iw))
    blob = padded[:, :, ::-1].transpose(2, 0, 1)  # BGR->RGB, HWC->CHW
    blob = np.ascontiguousarray(blob, dtype=np.float32) / 255.0
    blob = blob[None]
    t1 = time.perf_counter()

    out = session.run(None, {inp.name: blob})[0]
    t2 = time.perf_counter()

    pred = out[0] if out.ndim == 3 else out
    if pred.shape[0] == 4 + len(names):
        pred = pred.T  # -> (N, 4+nc)
    boxes = pred[:, :4]
    cls_scores = pred[:, 4:]
    cls_ids = cls_scores.argmax(axis=1)
    scores = cls_scores[np.arange(len(cls_ids)), cls_ids]
    m = scores >= conf_thr
    boxes, scores, cls_ids = boxes[m], scores[m], cls_ids[m]
    if len(boxes):
        boxes = xywh2xyxy(boxes)
        keep = nms(boxes, scores, iou_thr)
        boxes, scores, cls_ids = boxes[keep], scores[keep], cls_ids[keep]
        # 还原到原图坐标
        boxes[:, [0, 2]] = (boxes[:, [0, 2]] - pad_x) / ratio
        boxes[:, [1, 3]] = (boxes[:, [1, 3]] - pad_y) / ratio
        h, w = img.shape[:2]
        boxes[:, [0, 2]] = np.clip(boxes[:, [0, 2]], 0, w - 1)
        boxes[:, [1, 3]] = np.clip(boxes[:, [1, 3]], 0, h - 1)
    t3 = time.perf_counter()

    times = {"pre": t1 - t0, "infer": t2 - t1, "post": t3 - t2,
             "total": t3 - t0}
    return boxes, scores, cls_ids, times


def draw(img, boxes, scores, cls_ids, names):
    colors = [(0, 0, 255), (0, 160, 0), (255, 100, 0), (0, 200, 255),
              (200, 0, 200), (0, 140, 255), (128, 128, 0), (255, 0, 128)]
    for b, s, c in zip(boxes, scores, cls_ids):
        x1, y1, x2, y2 = map(int, b)
        color = colors[int(c) % len(colors)]
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
        label = "%s %.2f" % (names[int(c)] if int(c) < len(names) else str(int(c)), float(s))
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(img, (x1, max(0, y1 - th - 4)), (x1 + tw + 2, y1), color, -1)
        cv2.putText(img, label, (x1 + 1, max(10, y1 - 3)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    return img


def collect_sources(src):
    if os.path.isfile(src):
        return [src]
    if os.path.isdir(src):
        files = [os.path.join(src, f) for f in sorted(os.listdir(src))
                 if f.lower().endswith(IMG_EXTS)]
        return files
    return []


def main():
    ap = argparse.ArgumentParser(description="YOLOv8 ONNX inference for Raspberry Pi")
    ap.add_argument("--model", required=True, help="best_640.onnx / best_416.onnx / best_320.onnx")
    ap.add_argument("--source", required=True, help="图片路径 / 文件夹 / 摄像头编号(如 0)")
    ap.add_argument("--names", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "class_names.txt"))
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--iou", type=float, default=0.45)
    ap.add_argument("--threads", type=int, default=4, help="CPU 线程数（Pi 4 建议 4，Pi 5 可 4）")
    ap.add_argument("--save", default="", help="保存图片/视频的目录（不填则不保存）")
    ap.add_argument("--show", action="store_true", help="摄像头模式下显示窗口（需桌面环境）")
    args = ap.parse_args()

    names = load_names(args.names)
    session = make_session(args.model, args.threads)
    inp = session.get_inputs()[0]
    print("model   :", args.model)
    print("input   :", inp.name, inp.shape, "| outputs:", [o.shape for o in session.get_outputs()])
    print("classes :", len(names))

    if args.source.isdigit():  # 摄像头
        cap = cv2.VideoCapture(int(args.source))
        if not cap.isOpened():
            print("[错误] 摄像头打不开:", args.source)
            return 1
        writer = None
        frames, t_start = 0, time.time()
        win = "pi_infer"
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                boxes, scores, cls_ids, tm = detect(session, frame, names, args.conf, args.iou)
                frames += 1
                fps = frames / max(time.time() - t_start, 1e-6)
                draw(frame, boxes, scores, cls_ids, names)
                cv2.putText(frame, "FPS %.1f  infer %.0fms" % (fps, tm["infer"] * 1000),
                            (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                if args.save:
                    os.makedirs(args.save, exist_ok=True)
                    if writer is None:
                        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                        writer = cv2.VideoWriter(os.path.join(args.save, "output.mp4"),
                                                 fourcc, 15, (frame.shape[1], frame.shape[0]))
                    writer.write(frame)
                if args.show:
                    cv2.imshow(win, frame)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break
        except KeyboardInterrupt:
            pass
        finally:
            cap.release()
            if writer is not None:
                writer.release()
            cv2.destroyAllWindows()
        return 0

    files = collect_sources(args.source)
    if not files:
        print("[错误] 找不到图片:", args.source)
        return 1
    print("images  :", len(files))
    if args.save:
        os.makedirs(args.save, exist_ok=True)

    lat = {"pre": [], "infer": [], "post": [], "total": []}
    t_start = time.time()
    for i, f in enumerate(files):
        img = imread_unicode(f)
        if img is None:
            print("  [跳过] 读不到:", f)
            continue
        boxes, scores, cls_ids, tm = detect(session, img, names, args.conf, args.iou)
        for k in lat:
            lat[k].append(tm[k])
        fps = 1.0 / max(tm["total"], 1e-6)
        print("  %-40s det=%-3d infer=%5.1fms  total=%5.1fms (~%.1f FPS)"
              % (os.path.basename(f), len(boxes), tm["infer"] * 1000, tm["total"] * 1000, fps))
        if args.save:
            out = draw(img.copy(), boxes, scores, cls_ids, names)
            imwrite_unicode(os.path.join(args.save, os.path.basename(f)), out)

    n = len(lat["total"])
    if n:
        print("\n==== summary (%d images) ====" % n)
        for k in ("pre", "infer", "post", "total"):
            a = np.array(lat[k]) * 1000
            print("  %-6s mean %6.1f ms | p95 %6.1f ms" % (k, a.mean(), np.percentile(a, 95)))
        print("  平均单帧总延迟 %.1f ms -> 理论最高 %.1f FPS" % (
            np.mean(lat["total"]) * 1000, 1.0 / np.mean(lat["total"])))
        print("  总耗时 %.1f s" % (time.time() - t_start))
    return 0


if __name__ == "__main__":
    sys.exit(main())

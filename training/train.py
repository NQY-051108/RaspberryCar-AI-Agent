# -*- coding: utf-8 -*-
"""
YOLOv8 交通标志检测 —— 训练程序
=================================================
按顺序完成：环境/数据自检 -> 训练 -> 验证 -> 预测样例。

常用命令（在 training/ 下执行）：
    python train.py --check        # 只做训练前自检，不训练
    python train.py                # 全量训练（默认 yolov8n / 200 epochs）
    python train.py --model yolov8s.pt --batch 4 --name traffic_sign_v8s
    python train.py --quick        # 快速冒烟测试（1 epoch、10% 数据，用于确认流程）
    python train.py --resume       # 从上一次中断的 last.pt 继续训练

说明：
  * 相对命令行路径以仓库根目录为基准，输出默认放在 runs/；
  * 数据默认位于 datasets/，参见 training/README.md；
  * fliplr/flipud 固定为 0：方向性交通标志不能镜像，否则类别语义会被破坏；
  * RTX 3050 4GB 实测 yolov8n + 640 + batch 8 峰值显存约 1.1GB（安全）。
"""
import argparse
import os
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HOME = str(Path(__file__).resolve().parents[1])
DEFAULT_DATA = os.path.join(HOME, "datasets", "data.yaml")
DEFAULT_PROJECT = os.path.join(HOME, "runs")


# ----------------------------------------------------------------------------
# 参数
# ----------------------------------------------------------------------------
def parse_args():
    p = argparse.ArgumentParser(description="YOLOv8 traffic-sign detector training")
    p.add_argument("--model", default="yolov8n.pt", help="模型权重：yolov8n.pt / yolov8s.pt / 绝对路径")
    p.add_argument("--data", default=DEFAULT_DATA, help="data.yaml 路径")
    p.add_argument("--epochs", type=int, default=200, help="训练轮数（默认 200）")
    p.add_argument("--imgsz", type=int, default=640, help="输入尺寸（默认 640）")
    p.add_argument("--batch", type=int, default=8, help="batch size（默认 8；OOM 时改 4）")
    p.add_argument("--device", default="0", help="'0'=第一块 GPU，'cpu'=CPU")
    p.add_argument("--workers", type=int, default=4, help="DataLoader 线程数（报错时改 0）")
    p.add_argument("--patience", type=int, default=40, help="早停耐心值")
    p.add_argument("--name", default="traffic_sign_v8n", help="本次训练的输出目录名")
    p.add_argument("--project", default=DEFAULT_PROJECT, help="runs 根目录")
    p.add_argument("--no-cache", action="store_true", help="不把图片缓存进内存")
    p.add_argument("--no-predict", action="store_true", help="训练结束后不生成预测样张")
    p.add_argument("--check", action="store_true", help="只做自检（环境 + 数据 + 权重）")
    p.add_argument("--quick", action="store_true", help="快速冒烟：1 epoch + 10%% 数据 + 320 尺寸")
    p.add_argument("--resume", action="store_true", help="从 run 目录下的 last.pt 续训")
    return p.parse_args()


def resolve_path(p):
    """Resolve command-line paths relative to the repository root."""
    expanded = os.path.expanduser(p)
    return expanded if os.path.isabs(expanded) else os.path.join(HOME, expanded)


def dataset_root(data_path, config):
    """Match Ultralytics: omitted path uses YAML parent; relative path uses DATASETS_DIR."""
    root = Path(config.get("path") or Path(data_path).parent)
    if not root.is_absolute():
        from ultralytics.utils import DATASETS_DIR
        root = Path(DATASETS_DIR) / root
    return str(root.resolve())


# ----------------------------------------------------------------------------
# 第 1 步：自检
# ----------------------------------------------------------------------------
def preflight(args):
    print("=" * 78)
    print("第 1 步 / 检查环境")
    print("=" * 78)
    ok = True

    try:
        import torch
        import ultralytics

        print("  Python      :", sys.version.split()[0])
        print("  torch       :", torch.__version__, "| CUDA:", torch.version.cuda)
        print("  ultralytics :", ultralytics.__version__)
        cuda_ok = torch.cuda.is_available()
        print("  CUDA 可用   :", cuda_ok)
        if cuda_ok:
            name = torch.cuda.get_device_name(0)
            free, total = torch.cuda.mem_get_info(0)
            print("  GPU         : %s  (显存空闲 %.2f / %.2f GB)" % (name, free / 1e9, total / 1e9))
        else:
            print("  [警告] CUDA 不可用，训练将非常慢；可加 --device cpu 但仅建议测试。")
            if args.device != "cpu":
                ok = False
    except Exception as e:  # noqa: BLE001
        print("  [错误] 导入 torch/ultralytics 失败:", repr(e))
        return False

    # ---- 数据 ----
    print("\n" + "=" * 78)
    print("第 2 步 / 检查数据集")
    print("=" * 78)
    data_path = resolve_path(args.data)
    print("  data.yaml   :", data_path, "| 存在:", os.path.isfile(data_path))
    if not os.path.isfile(data_path):
        print("  [错误] 找不到 data.yaml")
        return False
    try:
        import yaml

        d = yaml.safe_load(open(data_path, encoding="utf-8"))
        root = dataset_root(data_path, d)
        names = d.get("names") or {}
        print("  path        :", root)
        print("  train / val : %s / %s" % (d.get("train"), d.get("val")))
        print("  classes     :", len(names))
        for split in ("train", "val"):
            img_dir = os.path.join(root, d[split])
            lbl_dir = os.path.join(root, "labels", split)
            if not os.path.isdir(img_dir):
                print("  [错误] 图片目录不存在:", img_dir)
                return False
            imgs = [f for f in os.listdir(img_dir) if f.lower().endswith((".jpg", ".jpeg", ".png"))]
            lbls = [f for f in os.listdir(lbl_dir) if f.lower().endswith(".txt") and f != "classes.txt"]
            empty = sum(1 for t in lbls if os.path.getsize(os.path.join(lbl_dir, t)) == 0)
            boxes = 0
            for t in lbls:
                with open(os.path.join(lbl_dir, t), encoding="utf-8-sig") as f:
                    boxes += sum(1 for line in f if line.strip())
            missing = len(imgs) - len(lbls)
            print("  %-5s      : 图片 %d | 标注 %d | 空标注 %d | 目标框 %d | 缺标注 %d"
                  % (split, len(imgs), len(lbls), empty, boxes, missing))
            if missing > 0:
                print("  [错误] 有 %d 张图片没有标注文件（会被当成背景图训练）" % missing)
                ok = False
    except Exception as e:  # noqa: BLE001
        print("  [错误] 读取 data.yaml / 数据集失败:", repr(e))
        return False

    # ---- 权重 ----
    print("\n" + "=" * 78)
    print("第 3 步 / 检查模型权重")
    print("=" * 78)
    model_path = resolve_path(args.model)
    print("  model       :", model_path, "| 存在:", os.path.isfile(model_path))
    if not os.path.isfile(model_path) and not os.path.isfile(model_path + ".pt"):
        print("  [错误] 本地权重不存在；请先获取官方权重并放到仓库根目录，或用 --model 指定路径。")
        ok = False

    print("\n" + "=" * 78)
    print("自检结果:", "通过 ✔" if ok else "有问题 ✘（见上面 [错误]/[警告]）")
    print("=" * 78)
    return ok


# ----------------------------------------------------------------------------
# 第 2 步：训练
# ----------------------------------------------------------------------------
def train(args):
    from ultralytics import YOLO

    data_path = resolve_path(args.data)
    model_path = resolve_path(args.model)
    project = resolve_path(args.project)

    if args.resume:
        last = os.path.join(project, args.name, "weights", "last.pt")
        print("=" * 78)
        print("断点续训:", last)
        print("=" * 78)
        if not os.path.isfile(last):
            print("[错误] 找不到 last.pt:", last)
            return None
        model = YOLO(last)
        model.train(resume=True)
        return os.path.join(project, args.name, "weights", "best.pt")

    kwargs = dict(
        data=data_path,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        workers=args.workers,
        patience=args.patience,
        cache=not args.no_cache,
        amp=True,
        fliplr=0.0,      # 关键：方向性标志不能水平翻转
        flipud=0.0,      # 不能垂直翻转
        seed=0,
        deterministic=True,
        project=project,
        name=args.name,
        exist_ok=False,
        plots=True,
    )
    if args.quick:
        kwargs.update(epochs=1, imgsz=320, batch=4, fraction=0.1,
                      name="quick_smoke", exist_ok=True, plots=False, patience=1)

    print("=" * 78)
    print("第 4 步 / 开始训练")
    print("=" * 78)
    for k, v in kwargs.items():
        print("  %-14s = %s" % (k, v))
    print("=" * 78)

    t0 = time.time()
    model = YOLO(model_path)
    try:
        model.train(**kwargs)
    except KeyboardInterrupt:
        print("\n[中断] 用户按了 Ctrl+C。可用 --resume 从 last.pt 继续。")
        return None
    except RuntimeError as e:  # noqa: BLE001
        if "out of memory" in str(e).lower():
            print("\n[错误] 显存不足：请把 --batch 改成 4，或 --imgsz 改成 512 再试。")
        raise
    print("\n训练耗时: %.1f 分钟" % ((time.time() - t0) / 60))

    run_dir = os.path.join(project, kwargs["name"])
    best = os.path.join(run_dir, "weights", "best.pt")
    print("runs 目录  :", run_dir)
    print("best 权重  :", best, "| 存在:", os.path.isfile(best))
    return best


# ----------------------------------------------------------------------------
# 第 3 步：验证 + 预测
# ----------------------------------------------------------------------------
def evaluate(args, best):
    from ultralytics import YOLO

    data_path = resolve_path(args.data)
    project = resolve_path(args.project)
    run_name = "quick_smoke" if args.quick else args.name
    print("\n" + "=" * 78)
    print("第 5 步 / 用 best.pt 独立验证 val 集")
    print("=" * 78)
    model = YOLO(best)
    try:
        r = model.val(data=data_path, imgsz=args.imgsz if not args.quick else 320,
                      batch=args.batch, device=args.device, split="val",
                      project=project, name=run_name + "_val", exist_ok=True, plots=False)
        print("  mAP50    :", round(float(getattr(r.box, "map50", 0)), 4))
        print("  mAP50-95 :", round(float(getattr(r.box, "map", 0)), 4))
    except Exception as e:  # noqa: BLE001
        print("  [警告] 验证失败:", repr(e))

    if args.no_predict:
        return
    print("\n" + "=" * 78)
    print("第 6 步 / 生成 val 集预测样张")
    print("=" * 78)
    root = os.path.dirname(data_path)
    try:
        import yaml
        d = yaml.safe_load(open(data_path, encoding="utf-8"))
        src = os.path.join(dataset_root(data_path, d), d["val"])
        model.predict(source=src, imgsz=args.imgsz if not args.quick else 320,
                      conf=0.25, device=args.device, save=True,
                      project=project, name=run_name + "_predict", exist_ok=True, verbose=False)
        print("  预测结果:", os.path.join(project, run_name + "_predict"))
    except Exception as e:  # noqa: BLE001
        print("  [警告] 预测失败:", repr(e))


# ----------------------------------------------------------------------------
def main():
    args = parse_args()
    print("\nYOLOv8 交通标志训练程序 | 工作目录:", HOME, "\n")
    if not preflight(args):
        sys.exit(1)
    if args.check:
        print("\n自检完成（--check 模式，不训练）。")
        return

    best = train(args)
    if not best or not os.path.isfile(best):
        print("\n[错误] 训练未产生 best.pt，退出。")
        sys.exit(2)
    evaluate(args, best)
    print("\n全部完成 ✔  结果目录:", os.path.join(resolve_path(args.project), "quick_smoke" if args.quick else args.name))


if __name__ == "__main__":
    main()

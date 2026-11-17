# PC 训练与导出

训练脚本用于 YOLOv8n 20 类交通标志，默认 640 输入、batch 8、最多 200 轮、patience 40；不使用水平或垂直翻转。训练完成后验证并保存预测结果。树莓派端仅部署 ONNX Runtime。

## 环境与数据

在仓库根目录创建独立 Python 环境，按 [PyTorch 官方安装说明](https://pytorch.org/get-started/locally/) 选择与你的显卡和驱动匹配的 PyTorch，再安装：

```bash
python -m pip install -r training/requirements.txt
```

已有训练记录使用 Ultralytics 8.4.176、PyTorch 2.14.1+cu126；导出记录使用 ONNX 1.23.2、onnxslim 0.1.99。依赖清单作为安装入口；复现实验时需另固定兼容的 PyTorch/CUDA 组合。

数据不随仓库发布。自行准备以下结构，并把 `training/data.example.yaml` 复制成 `datasets/data.yaml`。示例省略 `path`，数据根目录由 YAML 文件所在目录决定；如果填写 `path`，建议用本机数据集绝对路径，避免与 Ultralytics 全局 `datasets_dir` 设置混淆。

```text
datasets/
├── data.yaml
├── images/train/       # 训练图片
├── images/val/         # 验证图片
├── labels/train/       # 同名 YOLO txt 标注（背景图保留空 txt）
└── labels/val/
```

类别 ID 顺序需与示例 YAML、`predefined_classes.txt` 和 `pi_deploy/class_names.txt` 一致。原有类别拼写保留，不能只更改名称顺序而不处理标注和权重。

从 [Ultralytics 官方发行](https://github.com/ultralytics/assets/releases) 获取 `yolov8n.pt` 放在仓库根目录，或用 `--model` 指定已有权重。

## 训练

以下命令均从仓库根目录运行：

```bash
python training/train.py --check
python training/train.py --quick
python training/train.py
python training/train.py --data /path/to/data.yaml --model /path/to/yolov8n.pt --project /path/to/runs
python training/train.py --resume
```

命令行相对路径以仓库根目录为基准，默认数据为 `datasets/data.yaml`、输出为 `runs/traffic_sign_v8n/`。默认使用 GPU 0；CPU 测试加 `--device cpu`。`--quick` 会运行实际训练，使用 1 轮、10% 数据、320 输入；`--check` 只做环境与数据检查，不训练。

## 导出部署模型

训练结束后，在仓库根目录执行 Ultralytics CLI 导出（不会控制小车）：

```bash
yolo export model=runs/traffic_sign_v8n/weights/best.pt format=onnx imgsz=320 opset=12 simplify=True
```

将生成的 `runs/traffic_sign_v8n/weights/best.onnx` 复制并重命名为 `pi_deploy/best_320.onnx`。再分别以 `imgsz=416`、`imgsz=640` 导出，每次立即复制为 `best_416.onnx`、`best_640.onnx`，避免下一次导出覆盖。本脚本不自动导出；部署与下载方式见 [pi_deploy](../pi_deploy/README.md)。

训练权重和 ONNX 文件不进入 Git 历史；本次已训练模型可从 [模型发布页](../models/README.md) 获取。原始训练结果摘要见 [实验记录](../docs/experiments/README.md)。

# 树莓派交通标志识别

USB 摄像头采集 → YOLOv8n ONNX 推理 → 检测框/标签绘制 → 浏览器 MJPEG 预览。推理代码不会向底盘发送控制指令。

## 安装

要求树莓派 64 位系统、Python 3、USB UVC 摄像头。首次安装系统组件：

```bash
sudo apt update
sudo apt install -y python3-venv v4l-utils
cd ~/RaspberryCar-AI-Agent/pi_deploy
bash pi_setup.sh
```

安装脚本创建或复用 `~/pi_venv`，不会删除已有环境。可用 `CAR_PI_VENV=/其他目录 bash pi_setup.sh` 指定独立环境。仓库不带离线安装包；无网络时，先在其他电脑准备适配树莓派架构和 Python 版本的 wheel 文件到 `wheels_pi/`，再运行 `bash pi_setup.sh --offline`。

已核对的设备环境为 Python 3.11.2、ONNX Runtime 1.31.1、OpenCV 5.0.0.93、numpy 2.4.6。依赖清单不强制锁定这些版本；其他环境需要自行验证 wheel 兼容性。Windows 视频客户端需要带 GUI 的 OpenCV，建议与本目录 headless 环境分开安装。

从 [模型说明](../models/README.md) 下载模型到本目录，保留 `class_names.txt` 原顺序。无需在树莓派安装 PyTorch 或 Ultralytics。

## 运行与诊断

以下命令在本目录执行。环境检查只报告状态，摄像头诊断会打开摄像头并保存抓拍图：

```bash
~/pi_venv/bin/python pi_check_env.py
~/pi_venv/bin/python pi_camera_test.py
~/pi_venv/bin/python pi_camera_demo.py --model best_320.onnx --camera 0 --port 8080
```

运行识别后，同一局域网访问 `http://<树莓派IP>:8080/`；按 `Ctrl+C` 停止。端口只用于可信局域网，服务没有身份认证。不要同时启动 `camera_stream` 的预览或采集程序占用同一摄像头。

离线图片推理和基准测试使用你自己准备的图片目录；仓库没有附带原始数据集或 `sample_images/`：

```bash
~/pi_venv/bin/python pi_infer.py --model best_320.onnx --source /path/to/images --save out
~/pi_venv/bin/python pi_benchmark.py --images /path/to/images --threads 1,2,4
```

基准测试默认比较本目录 `best_320.onnx`、`best_416.onnx`、`best_640.onnx`，缺少的模型会跳过。耗时依赖输入尺寸、线程数、散热和系统负载，应在自己的设备上测量。

## 可选 systemd 服务

`yolo-camera.service` 是默认用户 `pi`、仓库目录 `/home/pi/RaspberryCar-AI-Agent`、虚拟环境 `/home/pi/pi_venv` 的模板。先核对并修改 `User`、`WorkingDirectory` 和 `ExecStart`，确认手动启动成功、模型已放入工作目录，再执行：

```bash
bash install_service.sh
```

此命令会安装服务、启用开机启动并立即重启识别程序。查看与停止：

```bash
systemctl status yolo-camera --no-pager
journalctl -u yolo-camera -f
sudo systemctl stop yolo-camera
sudo systemctl disable yolo-camera
```

发布源码不表示设备当前已安装或启动此服务。

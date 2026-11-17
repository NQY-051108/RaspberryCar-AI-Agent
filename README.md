# RaspberryCar-AI-Agent

基于树莓派 4B 的小车项目，包含手动底盘控制、图像采集与实时预览、YOLOv8n 交通标志训练，以及 ONNX Runtime 端侧识别。

当前识别与底盘是独立模块；识别结果自动驱动小车、传感器避障和 LLM Agent 接入属于后续工作。

| 目录 | 内容 |
|---|---|
| [car_control](car_control/README.md) | Bookworm 64 位底盘控制、SSH 键盘控制、mock GPIO 测试 |
| [camera_stream](camera_stream/README.md) | 周期采集、树莓派实时流、Windows 预览客户端 |
| [pi_deploy](pi_deploy/README.md) | ONNX 推理、浏览器实时识别、环境诊断与性能测试 |
| [training](training/README.md) | PC 训练、验证、预测及 ONNX 导出说明 |
| [models](models/README.md) | 当前模型下载、尺寸和 SHA256 |
| [docs/experiments](docs/experiments/README.md) | 本次训练的精选结果 |

## 获取代码与模型

```bash
git clone https://github.com/NQY-051108/RaspberryCar-AI-Agent.git
cd RaspberryCar-AI-Agent
```

模型作为 [v0.1.0-models Release](https://github.com/NQY-051108/RaspberryCar-AI-Agent/releases/tag/v0.1.0-models) 附件提供。按 [模型说明](models/README.md) 把 `best_320.onnx` 下载到 `pi_deploy/`。

## 树莓派实时识别

在 Raspberry Pi OS / Debian Bookworm 64 位、Python 3.11、USB UVC 摄像头环境下部署：

```bash
cd ~/RaspberryCar-AI-Agent/pi_deploy
bash pi_setup.sh
~/pi_venv/bin/python pi_camera_demo.py --model best_320.onnx --camera 0 --port 8080
```

电脑或手机在同一局域网访问 `http://<树莓派IP>:8080/`。`Ctrl+C` 停止。普通预览、采集和识别都需要摄像头，应分别运行。

底盘接线、安装和操作见 [底盘说明](car_control/README.md)，第一次实车动作前先运行 mock 测试并准备实体断电措施。

## 无硬件测试

安装底盘测试与视频客户端依赖后，在仓库根目录执行：

```bash
python -m pip install -r car_control/requirements.txt -r camera_stream/requirements-client.txt
python -m unittest discover -s car_control -p "test_*.py" -v
python -m unittest discover -s camera_stream -p "test_realtime_stream_*.py" -v
```

上述测试使用 mock GPIO / 本地 socket，不打开摄像头或驱动电机。`camera_stream/tools/test_camera.py`、`pi_camera_test.py` 是需要设备的诊断工具，应按相应说明手动运行。

## 源码来源与边界

源码按 2026-11-17 已下载的设备文件及本地同源工程整理；底盘和识别部署文件经 SHA256 对照。摄像头采集根目录使用 11 月 16 日设备快照，客户端来自 PC。此次发布没有重新在实车上运行程序。旧 Python 2 厂商 SDK、旧迁移版、凭据、虚拟环境、原始数据集和重复论文快照均未收录。

训练数据配置含 20 类，现有验证集只覆盖其中 13 类。实验指标及适用范围见 [实验记录](docs/experiments/README.md)。

第三方依赖和模型的许可说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

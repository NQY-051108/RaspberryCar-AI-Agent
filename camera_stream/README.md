# 树莓派摄像头实时可视化

这套脚本适用于：树莓派通过 SSH 管理、Windows 电脑通过 OpenCV 弹窗查看。树莓派运行服务器，Windows 运行客户端。脚本不控制电机；电机/底盘程序应保持独立。

按步骤执行的日常采集命令、实时窗口启动、停止流程和 `Cannot open camera` 排查见：[树莓派摄像头采集操作手册](树莓派摄像头采集操作手册.md)。

## 1. 部署目录

将仓库克隆到树莓派主目录后，摄像头文件位于 `~/RaspberryCar-AI-Agent/camera_stream/`：

- `realtime_stream_server.py`
- `realtime_stream_client.py`（也可只放在 Windows 电脑）

在树莓派 SSH 中可检查脚本语法：

```bash
chmod +x ~/RaspberryCar-AI-Agent/camera_stream/realtime_stream_server.py
python3 -m py_compile ~/RaspberryCar-AI-Agent/camera_stream/realtime_stream_server.py
```

## 2. 树莓派检查与安装

```bash
sudo apt update
sudo apt install -y python3-opencv v4l-utils
python3 -c "import cv2; print(cv2.__version__)"
ls -l /dev/video*
v4l2-ctl --list-devices
```

已知 USB 摄像头通常是 `/dev/video0`，但不要只凭编号猜测；以 `v4l2-ctl --list-devices` 为准。

## 3. 树莓派启动服务器

先查 IP：

```bash
hostname -I
```

假设树莓派 IP 是 `192.168.88.100`，启动实时预览服务器：

```bash
python3 ~/RaspberryCar-AI-Agent/camera_stream/realtime_stream_server.py \
  --camera 0 \
  --width 640 \
  --height 480 \
  --fps 10 \
  --port 9000
```

此时 SSH 窗口应显示 `Listening on 0.0.0.0:9000`，等待 Windows 客户端连接。不要关闭这个窗口。

如果希望同时在树莓派本地保存采集图片，使用下面这一条命令。**这时不要再启动 `capture.py`**，因为实时流服务器已经独占摄像头，并负责同时预览和保存：

```bash
python3 ~/RaspberryCar-AI-Agent/camera_stream/realtime_stream_server.py \
  --camera 0 --width 640 --height 480 --fps 10 --port 9000 \
  --save-dir ~/car_data/stream_$(date +%Y%m%d_%H%M%S) \
  --save-interval 0.5
```

启动后，先看到 `Listening on 0.0.0.0:9000`，再启动 Windows 客户端。只有客户端连接后，服务器才会读取、发送和保存帧。图片由树莓派本地写盘，网络只传预览帧。

运行关系如下：

```text
realtime_stream_server.py  (唯一打开 /dev/video0 的进程)
       ├──► Windows 客户端实时窗口
       └──► ~/car_data/stream_时间/ (由 --save-dir 指定的 JPEG 目录)
```

## 4. 运行中暂停和恢复图片采集

带 `--save-dir` 启动后，服务器默认处于“保存中”。启动输出会包含服务进程号，例如：

```text
Server PID: 1234
Local JPEG saving: /home/pi/car_data/road_A_20261030_143000
```

保持实时窗口和服务器不退出，在树莓派另开一个 SSH 窗口执行下面的命令。将 `1234` 换成服务器打印的实际 PID：

```bash
kill -USR1 1234
```

服务器终端会打印 `Image saving paused`，此时画面仍然实时更新，但 JPG 和 `metadata.csv` 暂停增加。需要继续采集时，再执行一次相同命令：

```bash
kill -USR1 1234
```

服务器终端会打印 `Image saving resumed`，JPG 和 CSV 恢复写入。这个命令只适用于带 `--save-dir` 的服务器；只看实时画面时无需使用。

注意：当前服务器的 `--save-dir` 直接保存 JPEG 和 `metadata.csv` 到指定目录，不会再创建 `images` 子目录。WinSCP 中应直接打开服务器启动时打印的 `SAVE_DIR` 路径。

## 5. Windows 端安装和启动

电脑端克隆本仓库后，客户端位于：

```text
camera_stream\realtime_stream_client.py
```

在仓库根目录的 Windows PowerShell 或 CMD 中执行：

```powershell
py -m pip install opencv-python numpy
py camera_stream\realtime_stream_client.py --host 192.168.88.100 --port 9000
```

如果 `py` 不可用，用：

```powershell
python -m pip install opencv-python numpy
python camera_stream\realtime_stream_client.py --host 192.168.88.100 --port 9000
```

窗口标题是 `Raspberry Pi Camera`，左上角会显示接收 FPS 和帧数。按 `q` 或 `Esc` 关闭窗口，客户端会关闭连接；树莓派服务器会回到等待下一次连接的状态。

## 6. 退出树莓派服务器

回到运行服务器的 SSH 窗口按 `Ctrl+C`。服务器会释放摄像头并退出。

## 7. 连接测试

Windows 端启动客户端前，可在 PowerShell 测试端口：

```powershell
Test-NetConnection 192.168.88.100 -Port 9000
```

看到 `TcpTestSucceeded : True` 后再运行客户端。

## 8. 常见问题

- `Cannot open camera`: 检查 `ls /dev/video*`、`v4l2-ctl --list-devices`，退出其他占用摄像头的程序，并把 `--camera 0` 改为正确编号。
- `Connection refused`: 树莓派服务器没有启动、端口写错或 IP 写错。
- `TcpTestSucceeded : False`: 电脑和树莓派不在同一个局域网，或树莓派 IP 已变化；重新运行 `hostname -I`。
- 能连接但窗口黑屏：检查摄像头遮挡、USB 连接、分辨率是否支持；先改成 `--width 640 --height 480`。
- 延迟较大：将树莓派端 `--width 320 --height 240 --fps 8 --jpeg-quality 70`，并使用稳定 Wi-Fi/网线。
- `Address already in use`: 9000 端口已有程序，先停止旧服务器，或两端都改用另一个端口。
- 关闭窗口后摄像头仍被占用：确认客户端按 `q`/`Esc`退出，再在服务器 SSH 窗口按 `Ctrl+C`；检查 `pgrep -af realtime_stream`。
- 暂停后仍看到实时画面：这是正常现象；暂停只停止 JPG/CSV 写入，不停止摄像头和视频流。恢复时再次对同一 PID 执行 `kill -USR1 <PID>`。
- `kill: ... No such process`：PID 已经退出或填错；回到服务器窗口重新启动并使用新的 `Server PID`。
- 不要同时运行旧的拍照程序、`capture.py` 和本服务器，否则多个程序会争抢同一个 `/dev/video0`。实时预览和采集时只运行本服务器；需要单独采集时先退出本服务器，再运行 `capture.py`。

## 9. 安全和底盘注意事项

服务器监听局域网地址，只在可信局域网使用；它没有身份认证。这个视频服务不发送电机命令，也不会自动驾驶。把它和底盘控制程序分开运行；测试移动时先限速，并准备实体急停。

## 10. 本地自检

代码上传到树莓派后，可在树莓派执行下面的测试。它不会打开摄像头，只检查暂停/恢复开关：

```bash
cd ~/RaspberryCar-AI-Agent/camera_stream
python3 -m py_compile realtime_stream_server.py test_realtime_stream_server.py
python3 test_realtime_stream_server.py
```

## 11. 单独周期采集与硬件诊断

需要电脑断开后仍持续采集时，先退出实时流和识别程序，再运行独立周期采集：

```bash
python3 ~/RaspberryCar-AI-Agent/camera_stream/capture.py --camera 0 --interval 0.5 --route road_A
```

它会在 `~/car_data/时间戳/` 保存 `images/`、`metadata.csv`、`run.json` 和 `status.json`；在该批次目录创建 `PAUSE` 文件可暂停，移除后恢复，`Ctrl+C` 停止。默认剩余空间低于 1 GiB 时停止保存。它与实时流预览是两种独立采集入口，同一摄像头只运行其中一种。

`tools/test_camera.py` 是直接打开摄像头并保存照片的诊断工具，只在树莓派上按需执行，不纳入普通单元测试发现。

# Raspberry Pi OS Bookworm 64 位底盘控制

该目录是从旧 32 位 Python 2 项目迁出的**底盘手动运动第一阶段**，包含短时点动、SSH 键盘遥控和 mock GPIO 单元测试。BCM 管脚经过原有底盘接线和厂商控制程序核对，旧 SDK 不随仓库发布：

| 功能 | BCM GPIO |
| --- | ---: |
| 右电机 ENA/PWM | 13 |
| 左电机 ENB/PWM | 20 |
| 右电机方向 IN1/IN2 | 19 / 16 |
| 左电机方向 IN3/IN4 | 21 / 26 |

使用 `gpiozero` + `lgpio`。导入模块不会操作 GPIO，创建 `MotorController(dry_run=False)` 才会打开管脚。限速是 PWM 占空比上限，不是实测车速；驱动板电压和电机电流尚未实测。轮架空短测：30%、35% 时电机有声但轮子几乎不动；38%、40% 时两侧轮子明显转动。落地短测：40% PWM 下动作 0.3 秒和 0.7 秒都只移动很小距离；50% PWM 下动作 0.5 秒能明显前进。因此默认速度设为 50%、默认上限仍为 50%。这说明当前负载下 40% 不足以可靠起步，但不能据此断定电池、驱动板或机械传动在其他负载下都正常。

## 部署与环境检查

将本仓库克隆到树莓派主目录后，本模块位于（默认用户名为 pi）：

```text
/home/pi/RaspberryCar-AI-Agent/car_control/
```

Bookworm 上如依赖尚未安装，SSH 执行一次：

```bash
sudo apt update
sudo apt install -y python3-gpiozero python3-lgpio
```

先不动电机，运行：

```bash
cd ~/RaspberryCar-AI-Agent/car_control
python3 -m py_compile motor_controller.py manual_drive.py run_motion.py test_motor_controller.py test_manual_drive.py
python3 test_motor_controller.py
python3 test_manual_drive.py
python3 run_motion.py forward --seconds 0.3 --speed 0.15 --dry-run
python3 manual_drive.py --dry-run
```

`test_motor_controller.py` 强制使用 gpiozero mock pins，不申请真实 GPIO；`test_manual_drive.py` 只测试按键状态机，不访问 GPIO。预期分别六项和四项测试通过。

## 首次真实电机点动

**只有你准备好亲自看车和操作实体断电/急停时才继续。** 关掉旧控制软件，抬起小车使驱动轮离地，固定车架，确认电池和驱动板无焦味/过热/裸线短路。若无独立实体急停，应在车旁能立即拔掉电机驱动电源；该动作不是拔树莓派 SD 卡。不要在有人或障碍物附近做首次测试。

确认旧程序、GPIO 引脚无人占用：

```bash
pgrep -af 'wifirobots|forward.py|ForthBackLeftRight|manual_drive|run_motion'
sudo fuser -v /dev/gpiochip0 2>/dev/null || true
```

每次只执行一条，观察完再执行下一条；默认强制 `lgpio`，速度为 50% PWM、最长 0.3 秒：

```bash
cd ~/RaspberryCar-AI-Agent/car_control
GPIOZERO_PIN_FACTORY=lgpio python3 run_motion.py forward --seconds 0.3 --speed 0.50 --max-speed 0.50
GPIOZERO_PIN_FACTORY=lgpio python3 run_motion.py backward --seconds 0.3 --speed 0.50 --max-speed 0.50
GPIOZERO_PIN_FACTORY=lgpio python3 run_motion.py left --seconds 0.25 --speed 0.50 --max-speed 0.50
GPIOZERO_PIN_FACTORY=lgpio python3 run_motion.py right --seconds 0.25 --speed 0.50 --max-speed 0.50
```

各命令结束会设 PWM 为 0、清方向脚并释放 GPIO。任何方向不对、只有单轮动作、异响、焦味或电流异常，马上切断电机电源，不要提高速度；先核对电机接线和左右定义。实体断电/急停独立于程序。

## SSH 键盘遥控

确认抬轮点动方向正常后再使用，保持人在小车旁、场地清空：

```bash
cd ~/RaspberryCar-AI-Agent/car_control
GPIOZERO_PIN_FACTORY=lgpio python3 manual_drive.py --speed 0.50 --max-speed 0.50 --timeout 0.25 --startup-timeout 0.75
```

`w` 前进，`s` 后退，`a` 左转，`d` 右转，空格停车，`q` 退出。SSH 终端通常只传送按键字符和自动重复字符，没有可靠的物理松键事件。每次开始或切换方向时使用默认 0.75 秒启动宽限，覆盖键盘开始自动重复前的等待；收到同方向重复字符后，改用 0.25 秒无按键超时停车，近似按键释放。重复字符只刷新超时，不会重复切换电机输出，以免控制输出出现短暂停顿。若长按仍会中途停顿，可将 `--startup-timeout` 调高到 1 秒；若想松键后更快停车，可将 `--timeout` 调低，但不要低于终端重复字符间隔。短按方向键但没有自动重复时，小车可能持续运动至启动宽限到期；空格始终可以主动停车。`Ctrl+C`、正常 shell hangup/terminate 也会执行清 PWM 与释放 GPIO。SSH 丢失、系统崩溃或掉电时不能把软件停车当作保证，必须保留手边实体急停。

## 文件、测试范围与未迁移功能

- `motor_controller.py`：两个 L298 方向输入和 ENA/ENB PWM，最大速度限幅，停车和资源释放。
- `run_motion.py`：前后左右/停止的有界时长动作，单次动作最多 10 秒。
- `manual_drive.py`：带无按键超时停车的交互式 SSH 键盘控制。
- `test_motor_controller.py`：逻辑检查，固定 gpiozero mock 后端，不会驱动实车。
- `test_manual_drive.py`：按键首次触发、自动重复、方向切换和空格停车测试，不会驱动实车。

旧项目的 TCP/Bluetooth 控制协议、循迹红外/超声波、摄像头循迹和基于时间的路线功能尚未迁移。确认底盘接线和方向后，再把这些功能逐项接入唯一 `MotorController`；目前不含传感器避障、失联独立看门狗、定位、YOLO 或 AI Agent，不要用于自主巡航或无人值守。

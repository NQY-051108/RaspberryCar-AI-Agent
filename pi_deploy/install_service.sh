#!/bin/bash
# 安装/更新摄像头检测系统服务（开机自启）
# 用法： cd ~/RaspberryCar-AI-Agent/pi_deploy && bash install_service.sh
set -e
cd "$(dirname "$0")"

sudo cp yolo-camera.service /etc/systemd/system/yolo-camera.service
sudo systemctl daemon-reload
sudo systemctl enable yolo-camera.service
sudo systemctl restart yolo-camera.service
sleep 3
echo "=========== 服务状态 ==========="
systemctl status yolo-camera.service --no-pager -l | head -12
IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo
echo "浏览器打开: http://$IP:8080/"
echo "查看日志  : journalctl -u yolo-camera -f"
echo "停止服务  : sudo systemctl stop yolo-camera"
echo "启动服务  : sudo systemctl start yolo-camera"

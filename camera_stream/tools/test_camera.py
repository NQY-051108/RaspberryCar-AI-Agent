import cv2
from pathlib import Path
from datetime import datetime

output = Path.home() / "car_data" / "camera_test"
output.mkdir(parents=True, exist_ok=True)

for index in range(3):
    cap = cv2.VideoCapture(index, cv2.CAP_V4L2)

    if not cap.isOpened():
        print(f"摄像头 {index} 无法打开")
        continue

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    ok, frame = cap.read()
    cap.release()

    if ok:
        filename = datetime.now().strftime(
            f"camera{index}_%Y%m%d_%H%M%S.jpg"
        )
        path = output / filename
        cv2.imwrite(str(path), frame)
        print(f"拍摄成功: {path}")
        print(f"图像尺寸: {frame.shape[1]} x {frame.shape[0]}")
        break
    else:
        print(f"摄像头 {index} 打开成功，但读取画面失败")

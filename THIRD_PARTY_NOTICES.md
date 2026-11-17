# 第三方来源与许可

- 模型采用 Ultralytics YOLOv8n 训练与导出。当前 ONNX 元数据标注 **AGPL-3.0**，参见 [Ultralytics 许可说明](https://www.ultralytics.com/license)。分发或使用这些模型时应保留并遵循其适用条款。本仓库没有将模型重新声明为 MIT。
- 运行依赖包括 ONNX Runtime、OpenCV、numpy、gpiozero/lgpio；PC 训练另依赖 Ultralytics、PyTorch、PyYAML 及导出工具。这些项目各自的许可证随其官方发行版提供。
- 底盘引脚定义来自小车原有硬件与厂商控制程序核对；旧厂商 SDK、编译模块及手册没有随本仓库再分发。
- 原始训练图像和标注没有随源码发布。共享数据集时需另行说明来源和使用条件。

仓库当前没有为全部自有源码指定统一开源许可证。第三方来源、模型许可和数据使用条件不因代码公开而改变。

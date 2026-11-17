# 当前模型

从 [v0.1.0-models](https://github.com/NQY-051108/RaspberryCar-AI-Agent/releases/tag/v0.1.0-models) 下载下列文件。三份 ONNX 与 2026-11-17 已下载的树莓派部署副本逐字节一致，未重新导出。

| 文件 | 字节数 | 用途 / 本地放置位置 |
|---|---:|---|
| [best_320.onnx](https://github.com/NQY-051108/RaspberryCar-AI-Agent/releases/download/v0.1.0-models/best_320.onnx) | 12639002 | 默认实时识别模型，放入 `pi_deploy/` |
| [best_416.onnx](https://github.com/NQY-051108/RaspberryCar-AI-Agent/releases/download/v0.1.0-models/best_416.onnx) | 12667982 | 416 输入对照模型，放入 `pi_deploy/` |
| [best_640.onnx](https://github.com/NQY-051108/RaspberryCar-AI-Agent/releases/download/v0.1.0-models/best_640.onnx) | 12765006 | 640 输入对照模型，放入 `pi_deploy/` |
| [best.pt](https://github.com/NQY-051108/RaspberryCar-AI-Agent/releases/download/v0.1.0-models/best.pt) | 6508650 | 已训练的 PyTorch 权重，用于微调或重新导出 |

在仓库根目录下载默认模型：

```bash
curl -L --fail -o pi_deploy/best_320.onnx https://github.com/NQY-051108/RaspberryCar-AI-Agent/releases/download/v0.1.0-models/best_320.onnx
```

Windows PowerShell 可用：

```powershell
Invoke-WebRequest -Uri https://github.com/NQY-051108/RaspberryCar-AI-Agent/releases/download/v0.1.0-models/best_320.onnx -OutFile pi_deploy/best_320.onnx
Get-FileHash pi_deploy/best_320.onnx -Algorithm SHA256
```

对照 [SHA256SUMS](SHA256SUMS) 验证文件完整性；Linux 可在 `pi_deploy/` 运行 `sha256sum best_320.onnx`。下载后文件会被 `.gitignore` 忽略。

模型为 20 类交通标志检测，类别顺序见 `pi_deploy/class_names.txt`。已训练模型的元数据保留训练环境路径和 AGPL-3.0 标识，路径只表示原训练环境，不是部署必需目录。许可来源见 [第三方说明](../THIRD_PARTY_NOTICES.md)。

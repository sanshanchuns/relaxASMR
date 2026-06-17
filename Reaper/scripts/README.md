# Reaper · 共享脚本

## upscale · Real-ESRGAN 超分

本地 Real-ESRGAN 路径（可改环境变量）：

```bash
export REAL_ESRGAN_HOME=/home/leo/workspace/Real-ESRGAN
```

### 视频（720p → ~4K）

等价于你之前的命令：

```bash
cd Reaper/scripts

./upscale.sh /mnt/c/Users/acele/Downloads/720p.mp4 \
  -o /mnt/c/Users/acele/Downloads/4k_SR.mp4 \
  -s 3 -t 512 --suffix 4k
```

- 默认模型：`RealESRGAN_x4plus`
- 默认 `-s 3`（视频）、`-t 512`
- 若不写 `-o`：输出 `{输入目录}/{原名}_4k.mp4`
- 若 `-o` 写 **完整 .mp4 路径**：脚本跑完后 **自动 rename** 到该文件名

### 图片（概念图 / 封面）

```bash
./upscale.sh ../../VisualDesign/forest/assets/CN-299_duanqiao_medium_rain_day_v1.png \
  -o ../../VisualDesign/forest/assets/upscaled/ \
  -s 2 --suffix 4k
```

- 默认 `-s 4`（图片）；1920 宽素材常用 `-s 2` 到 4K
- 输出：`{目录}/{原名}_4k.png`

### 常用参数

| 参数 | 说明 |
|------|------|
| `-s 3` | 放大倍数 |
| `-t 512` | 分块（防显存 OOM） |
| `-n RealESRGAN_x4plus` | 实景模型 |
| `--suffix 4k` | 输出名 `{原名}_4k.*` |
| `--fp32` | 半精度报错时用 |
| `--image` / `--video` | 强制模式 |

### 帮助

```bash
./upscale.sh -h
```

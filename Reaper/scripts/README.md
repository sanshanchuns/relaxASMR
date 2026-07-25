# Reaper 共享脚本

Rain / Lake 等工程共用。媒体路径指向仓库 `assets/`。

## 日常只用这 3 个（Reaper 里）

| 脚本 | 何时用 |
|------|--------|
| **`asmr_loop_track.lua`** | **循环层** · 把一条轨 loop 至工程时长 |
| **`asmr_vol_envelope.lua`** | **`1_rain` 长时音量包络** · 时长 / 点数 / ±dB / 正弦·余弦 |
| **`asmr_scatter_track.lua`** | **稀疏层散布**（手动填间隔/随机度，逐轨运行） |

### 在 Reaper 里怎么运行

脚本在 **`Reaper/scripts/`**；也会同步到 **`Reaper/Projects/Rain/scripts/`**。

1. 打开子工程 `.rpp`（例如 `.../MVI_6923/MVI_6923.rpp`），**Ctrl+S 保存一次**
2. 菜单 **Actions → ReaScript: Load**
3. 循环层逐轨运行 **`asmr_loop_track.lua`**（或只 loop 需要的轨）
4. 对 **`1_rain`** 运行 **`asmr_vol_envelope.lua`**（弹窗填：时长、点数、最大/最小 dB、正弦或余弦）
5. 对 `2_impact`、`5_wildlife` 等逐轨运行 **`asmr_scatter_track.lua`** → **Ctrl+S**
6. 日志：**View → Show console**（Mac 上 **`~`** 键）

## 稀疏散布：`asmr_scatter_track.lua`

| 场景 | 操作 |
|------|------|
| **Impact / Wildlife 等稀疏轨** | 输入层 id：`2_impact`、`5_wildlife`（或 `0` 选中当前轨）→ **弹窗填参数**（时长、间隔、随机度） |
| **循环层** | 先用 **`asmr_loop_track`**，再按需写包络 |

不再从 `asmr_config.lua` 读取间隔/随机度；`scatter_layers` 仅保留轨号、素材路径与音量。

Group 父轨存在时，脚本按 **轨名（如 `3_impact`）** 匹配，不依赖 TCP 轨号。

## 命令行（仓库根目录）

| 脚本 | 用途 |
|------|------|
| `generate_subproject.py --scene <id>` | 从 `scripts/scenes/<id>.json` 生成 `.rpp`（兼容旧 `.lua`） |
| **`create_rain_subproject.py --video <mp4>`** | **一键**：loop 视频 → 分析 + JSON 配置 + `.rpp` |
| `analyze_video_audio.py --scene <id> --update-doc` | 视频原声 → `video_analysis.md` §二 |
| `repair_rpp_paths.py` | 修复 rpp 内媒体路径 |
| [`scripts/video_export/export_mp4.sh`](../../scripts/video_export/export_mp4.sh) | 循环视频 + 音频 → MP4（含 YouTube 物料） |

## 库文件（勿单独加载）

| 文件 | 说明 |
|------|------|
| `asmr_paths.lua` | 仓库根、场景配置路径解析 |
| `scene_config.py` | 场景配置 JSON 读写（`save_scene_config` / `load_scene_config`） |
| `asmr_config_parser.py` | 仅用于读取旧 `.lua` 配方 |

## Rain 子工程流程

**从 loop 视频一键创建（推荐）：**

```bash
python3 Reaper/scripts/create_rain_subproject.py \
  --video assets/loop_video/rain_video/MVI_6918/MVI_6918_loop_3_fade_0.5.mp4
```

自动：探测视频 · 首帧启发式 · `baseURL/material/<id>_video_analysis.md` + `scripts/scenes/<id>.json` + `.rpp`。

**仅重新生成 `.rpp`（配置已写好）：**

```bash
python3 Reaper/scripts/generate_subproject.py --scene MVI_6918
```

`--media-mode` 默认 **auto**（无需手动指定）：

| 运行环境 | 自动选择 | RPP 内路径示例 |
|----------|----------|----------------|
| macOS | `absolute` | `/Users/.../assets/...` |
| WSL + baseURL 在 `/mnt/e` | `wsl_unc` | `E:\自然之声\to_youtube\audio\...` |
| WSL + 仓库在 `/home/...` | `wsl_unc` | `\\wsl.localhost\Ubuntu\home\...` |
| Windows + 仓库在本机盘 | `absolute` | `C:\...\assets\...` |
| Linux 原生 | `absolute` | `/home/.../assets/...` |

强制覆盖：`RELAXASMR_MEDIA_MODE=absolute` 或 `--media-mode wsl_unc`。`/mnt/x` 若必须走 UNC：`RELAXASMR_MEDIA_WIN_DRIVE=0`。

打开 `.rpp` → **`asmr_loop_track`** → **`asmr_vol_envelope`**（`1_rain`）→ **`asmr_scatter_track`** → 手调 Group / Master 限幅 → 渲染 wav → [`scripts/video_export/export_mp4.sh`](../../../scripts/video_export/export_mp4.sh) 合成 mp4。

混音质量：人工对照 [`design/rain_series/scoring_rubric.md`](../../design/rain_series/scoring_rubric.md)；后续 **爆款声纹** 见 [`benchmark/README.md`](../../benchmark/README.md)。

场景配置在 `Rain/scripts/scenes/<id>.json`（旧 `.lua` 仍可读取）。

## 系列

- **Rain**：睡眠 · 默认 3 h
- **Lake**：专注 + 钢琴 · 勿与 Rain 配置混用

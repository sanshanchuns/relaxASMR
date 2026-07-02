# Reaper 共享脚本

Rain / Lake 等工程共用。媒体路径指向仓库 `assets/`。

## 日常只用这 4 个（Reaper 里）

| 脚本 | 何时用 |
|------|--------|
| **`asmr_apply_recipe.lua`** | **首选** · 铺循环 + 全部稀疏 + **`1_rain` 音量包络（Dynamic）** |
| **`asmr_scatter_track.lua`** | **只重做一条稀疏轨**（见下） |
| **`asmr_loop_track.lua`** | **只循环一条轨**（试验素材长度时） |
| **`asmr_score_mix.lua`** | **RS-PASS 混音打分**（唯一入口：渲染 → 打分 → 可选一键改轨） |

### RS-PASS 混音打分（`asmr_score_mix.lua` · 唯一入口）

> 只需 Load 这一个脚本。轨级「一键应用」已内联，**不要**再 Load `asmr_score_apply.lua`（已删除）。

1. 保存 `.rpp` · 混音调好后运行脚本（共享 `Reaper/scripts/` 或子工程 `scripts/`）
2. **有时间选区** → 只渲染并分析选区（最长 300s）
3. **无选区** → 从工程开头分析前 300s（长工程不会渲染 3h 全长）
4. 报告 → `<场景>/output/score/mix_score.md` · 含 RS-PASS 七维 + 色噪声类型 + RPP 修改建议
5. 依赖本仓库 **`benchmark/`**（经 `scripts/video_export/scoring_bridge.py` 调用）· 需 python3 + ffmpeg
6. 自定义分析时长：Reaper **ExtState** `relaxASMR` / `score_duration`（秒）
7. **打分后**弹出轨级建议；可 **一键应用** 音量微调 / `1_rain` 包络 / Group HF EQ（换素材类须手动）

Windows Reaper + WSL 工程时会自动 `wsl python3 …`。

### 在 Reaper 里怎么运行

脚本在 **`Reaper/scripts/`**；创建子工程时也会复制到 **`<场景>/scripts/`**（与 `asmr_config.lua` 同目录）。

1. 打开子工程 `.rpp`（例如 `.../MVI_6923/MVI_6923.rpp`），**Ctrl+S 保存一次**
2. 菜单 **Actions → ReaScript: Load**（或 **New/Load ReaScript**）
3. 选 **`asmr_apply_recipe.lua`**：
   - 子工程内：`Reaper/Projects/Rain/subprojects/<场景>/scripts/asmr_apply_recipe.lua`
   - 或共享目录：`Reaper/scripts/asmr_apply_recipe.lua`
4. 弹窗选 **确定**（循环+稀疏）→ 完成后 **Ctrl+S**
5. 日志：**View → Show console**（Mac 上 **`~`** 键）

> 子工程 `scripts/` 里的 `rain_setup_project.lua` 是旧版入口，**请用 `asmr_apply_recipe.lua`**（含 **`1_rain` 长时音量包络**）。

## 稀疏散布：只用 `asmr_scatter_track.lua`

| 场景 | 操作 |
|------|------|
| **Rain 子工程、配方里已有 scatter_layers** | 输入层 id：`2_impact`、`5_wildlife`（或 `0` 选中当前轨）→ **自动读 asmr_config** |
| **无配方 / 临时试间隔** | 输入轨后 **无配方匹配** → 弹出手动参数（时长、间隔、随机度） |
| **整片 3h 全部稀疏层** | 用 **`asmr_apply_recipe`**，不要逐个跑 scatter |

已删除 `asmr_scatter_config_track.lua`（功能合并进 `asmr_scatter_track`）。

Group 父轨存在时，脚本按 **轨名（如 `3_impact`）** 匹配，不依赖 TCP 轨号。

## 命令行（仓库根目录）

| 脚本 | 用途 |
|------|------|
| `generate_subproject.py --scene <id>` | 从 `asmr_config.lua` 生成 `.rpp`（含 Group 总线） |
| **`create_rain_subproject.py --video <mp4>`** | **一键**：loop 视频 → 分析 + 配方 + 脚手架 + `.rpp` |
| `analyze_video_audio.py --scene <id> --update-doc` | 视频原声 → `video_analysis.md` §二 |
| **`asmr_score_mix.lua`** | **RS-PASS 混音打分**（时间选区 / 整工程前 300s → `output/score/`） |
| [`benchmark/score.py`](../../benchmark/score.py) | 成品 / 混音 RS-PASS（本仓库内置） |
| `repair_rpp_paths.py` | 修复 rpp 内媒体路径 |
| [`scripts/video_export/export_mp4.sh`](../../scripts/video_export/export_mp4.sh) | 循环视频 + 音频 → MP4（含物料 + benchmark） |

## 库文件（勿单独加载）

| 文件 | 说明 |
|------|------|
| `asmr_paths.lua` | 仓库根、`asmr_config`、按层 id 找轨 |
| `asmr_vol_envelope.lua` | 长时音量包络（由 apply_recipe / score_mix 调用） |
| `asmr_config_parser.py` | Python 读配方 |
| `dump_asmr_config.lua` | 配方 → JSON（generate 用） |

## Rain 子工程流程

**从 loop 视频一键创建（推荐）：**

```bash
python3 Reaper/scripts/create_rain_subproject.py \
  --video assets/loop_video/rain_video/MVI_6918/MVI_6918_loop_3_fade_0.5.mp4
```

自动：探测视频 ·（若有）内嵌音轨六层分析 · 首帧启发式 · `video_analysis.md` + `asmr_config.lua` + `.rpp`（Group **ReaEQ + ReaComp** · 轨 `5_wildlife` **ReaVerbate** · 轨 7 视频）。

**仅重新生成 `.rpp`（配方已写好）：**

```bash
python3 Reaper/scripts/generate_subproject.py --scene MVI_6918
```

`--media-mode` 默认 **auto**（无需手动指定）：

| 运行环境 | 自动选择 | RPP 内路径示例 |
|----------|----------|----------------|
| macOS | `absolute` | `/Users/.../assets/...` |
| WSL 内跑脚本 | `wsl_unc` | `\\wsl.localhost\Ubuntu\home\...` |
| Windows + 仓库在本机盘 | `absolute` | `C:\...\assets\...` |
| Linux 原生 | `absolute` | `/home/.../assets/...` |

强制覆盖：`RELAXASMR_MEDIA_MODE=absolute` 或 `--media-mode wsl_unc`。

打开 `.rpp` → **`asmr_apply_recipe.lua`**（铺循环/稀疏 + **`1_rain` 长时音量包络**）→ 手调 Group / Master 限幅 → 渲染 wav → [`scripts/video_export/export_mp4.sh`](../../../scripts/video_export/export_mp4.sh) 合成 mp4（自动物料 + benchmark）。

`asmr_config.lua` 在子工程 `scripts/` 下（非 `Audio Files/`）。

## 系列

- **Rain**：睡眠 · 默认 3 h
- **Lake**：专注 + 钢琴 · 勿与 Rain 配方混用

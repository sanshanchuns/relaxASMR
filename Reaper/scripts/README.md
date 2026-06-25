# Reaper 共享脚本

多工程共用（Rain / Lake / …）。媒体路径指向仓库 `assets/`。

## 脚本一览

| 脚本 | 用途 |
|------|------|
| `asmr_paths.lua` | 仓库根目录、`asmr_config.lua` 加载 |
| `asmr_loop_track.lua` | 单轨循环至 N 小时 |
| `asmr_scatter_track.lua` | **通用随机散布**：轨道、时长、次数/间隔、随机度 0–1 |
| `asmr_scatter_config_track.lua` | 单轨散布，参数从工程 `scripts/asmr_config.lua` 读取 |
| `asmr_apply_recipe.lua` | 一键：循环层 + 全部稀疏层 + **带 `vol_envelope` 的轨音量包络** |
| `asmr_vol_envelope.lua` | 长时单周期 Volume 包络逻辑（模块，供 apply_recipe 调用） |
| `asmr_apply_vol_envelope.lua` | 仅重刷配方中的音量包络（不改 item） |
| `asmr_apply_group_eq.lua` | Group 轨添加/刷新 **JS ASMR Sleep HF EQ**（不依赖 ReaEQ API） |
| `fx/asmr_sleep_hf_eq.jsfx` | Group 总线 JS 削高频（参数可直接写在 rpp） |
| `generate_subproject.py` | 从 config 生成 `.rpp` |
| `analyze_video_audio.py` | 分析视频嵌入式音轨 → 七层 Markdown（可写入 `video_analysis.md`） |
| `score_mix.py` | 按 `design/rule.md` 给渲染成品打 包裹感/安全感 分（成品声学 + 配方结构） |
| `dump_asmr_config.lua` | config → JSON（供 Python） |
| `repair_rpp_paths.py` | 修复已有 rpp 中的路径 |

## 生成子工程

```bash
python3 Reaper/scripts/generate_subproject.py --scene MVI_6918
```

默认 **不复制**媒体：RPP 内用 WSL UNC 直接引用 `assets/`（格式对齐 `Demo.rpp`：`SOURCE MP3`、`FILE "\\\\wsl.localhost\\..." 1`）。**视频轨 VOLPAN = 0（-inf dB）**，仅最终渲染用。

打开后运行 `asmr_apply_recipe.lua` 铺音频层（**轨 1–7**；`render_only` 视频轨不改动）。主雨层 `2_rain` 可配 `vol_envelope` 实现 3h 单周期缓慢起伏；仅重刷包络用 `asmr_apply_vol_envelope.lua`。

`asmr_config.lua` 位于 **与 `.rpp` 同级的 `scripts/`**，不在 `Audio Files/` 下；脚本已处理 `RECORD_PATH` 指向 `Audio Files` 的情况。

### 视频原声分析

```bash
python3 Reaper/scripts/analyze_video_audio.py --scene MVI_6918 --update-doc
```

写入子工程 `video_analysis.md` **§二**「视频原声拆解」。

在 Windows Reaper 中打开：

`\\wsl.localhost\Ubuntu\home\leo\workspace\relaxASMR\Reaper\Projects\Rain\subprojects\MVI_6918\MVI_6918.rpp`

## 随机散布参数（asmr_scatter_track）

| 参数 | 说明 |
|------|------|
| track | 轨道号，0=当前选中 |
| duration_h | 工程时长（小时），0=读工程长度 |
| count | 总出现次数；**0=按间隔自动铺满** |
| min_gap_min / max_gap_min | 最小/最大间隔（分钟） |
| randomness | 0~1，越大间隔与位置抖动越大 |
| fade_ms | 淡入淡出（毫秒） |

## 系列区分

- **Rain**：睡眠，默认 3 h 可配置
- **Lake**：专注 + 钢琴 solo，勿与 Rain 配方混用

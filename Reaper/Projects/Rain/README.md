# Rain 系列 · Reaper 工程

**Rain = 睡眠系列**（长时雨声铺底）。**专注 + 钢琴 solo = Lake 系列**，两者勿混。

雨声多层混音：总工程目录 + 多个子工程。媒体引用 `assets/`。

## 产出物

| 文件 | 说明 |
|------|------|
| `<scene>.rpp` | Reaper 工程（含 Group 总线） |
| `scripts/scenes/<scene>.json` | 场景配置（轨结构、素材路径、时长；CLI 写入，GUI 可不落盘） |
| `scripts/fx/asmr_sleep_hf_eq.jsfx` | Group 削高频 JS |
| `baseURL/material/<scene>_video_analysis.md` | 画面分析文档 |

## 生成流程

**一键（只给 loop 视频）：**

```bash
python3 Reaper/scripts/create_rain_subproject.py \
  --video <baseURL 或仓库内的 loop MP4>
```

产出 `material/<scene>_video_analysis.md`、`scripts/scenes/<scene>.json`、`<scene>.rpp`。

**仅重新生成 `.rpp`（配置已存在）：**

```bash
python3 Reaper/scripts/generate_subproject.py --scene MVI_6918
```

打开工程后：`asmr_loop_track` → `asmr_vol_envelope`（`1_rain`）→ 逐轨 `asmr_scatter_track`。

**模板自带：**

- 轨 **Group** · **ReaEQ + ReaComp**
- 轨 1–6 六层素材 · 轨 `5_wildlife` **ReaVerbate** · 轨 7 视频（静音，仅渲染）
- **Dynamic** = 无轨，手动运行 `asmr_vol_envelope.lua` 写 `1_rain` 包络

## 轨布局

| 轨 | layer_id | 层 |
|----|----------|-----|
| Group | 总线 | ReaEQ + ReaComp |
| 1 | `1_rain` | Rain（Dynamic 主载包络） |
| 2 | `2_impact` | Impact scatter |
| 3 | `3_environment` | Environment loop |
| 4 | `4_water` | Water |
| 5 | `5_wildlife` | Wildlife scatter · ReaVerbate |
| 6 | `6_human` | Human loop |
| 7 | video | 仅渲染 |

模板定义：[`scripts/layer_template.lua`](scripts/layer_template.lua) · JS 源：[`scripts/fx/asmr_sleep_hf_eq.jsfx`](scripts/fx/asmr_sleep_hf_eq.jsfx)

## `scripts/` 目录

| 文件 | 用途 |
|------|------|
| `scenes/<scene_id>.json` | 场景配置（CLI `create_rain_subproject.py` 写入；`generate_subproject.py` 读取） |
| `layer_template.lua` | 轨布局 + Group FX 模板（仅 Python 生成 `.rpp` 时用） |
| `fx/asmr_sleep_hf_eq.jsfx` | Group 削高频 JSFX 源文件 |
| `asmr_loop_track.lua` | 循环层铺至工程时长 |
| `asmr_vol_envelope.lua` | `1_rain` 长时音量包络 |
| `asmr_scatter_track.lua` | 稀疏层随机散布 |
| `asmr_paths.lua` | 路径/场景解析库（由 `Reaper/scripts/` 同步，勿单独运行） |

已移除旧流程脚本 `rain_bootstrap.lua` / `rain_setup_project.lua` / `rain_paths.lua`（建轨与散布已由 `generate_subproject.py` 生成 `.rpp` 完成）。

## MVI_6888

- 分析与配方（初版）：[`subprojects/MVI_6888/video_analysis.md`](subprojects/MVI_6888/video_analysis.md)
- 视频：`assets/loop_video/rain_video/MVI_6888/MVI_6888_loop_8_fade_0.5.mp4`（无内嵌音轨）

## MVI_6918

- 分析与配方：[`subprojects/MVI_6918/video_analysis.md`](subprojects/MVI_6918/video_analysis.md)

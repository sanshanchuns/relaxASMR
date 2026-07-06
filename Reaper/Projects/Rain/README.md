# Rain 系列 · Reaper 工程

**Rain = 睡眠系列**（长时雨声铺底）。**专注 + 钢琴 solo = Lake 系列**，两者勿混。

雨声多层混音：总工程目录 + 多个子工程。媒体引用 `assets/`。

## 子工程产出物

每个 `subprojects/<scene>/` 包含：

| 文件 | 说明 |
|------|------|
| `video_analysis.md` | 画面拆解 + 原声拆解 + 七层配方（唯一分析/配方文档） |
| `<scene>.rpp` | 3 h 可配置子工程（含 **Group Folder + 总线 FX**） |
| `scripts/asmr_config.lua` | Reaper 配方数据（与 `video_analysis.md` §三 同步） |
| `scripts/fx/asmr_sleep_hf_eq.jsfx` | Group 削高频 JS（生成时从模板复制） |

## 生成流程

**一键（只给 loop 视频）：**

```bash
python3 Reaper/scripts/create_rain_subproject.py \
  --video assets/loop_video/rain_video/<MVI_xxxx>/<...>_loop_*_fade_*.mp4
```

产出 `video_analysis.md`、`scripts/asmr_config.lua`、`<scene>.rpp`；打开工程后运行 **`asmr_apply_recipe.lua`**（铺循环 + `1_rain` 包络），再逐轨 **`asmr_scatter_track.lua`**（手动填散布参数）。

**仅生成 `.rpp`（配方已存在）：**

```bash
python3 Reaper/scripts/generate_subproject.py --scene MVI_6918
```

**模板自带：**

- 轨 **Group** · **ReaEQ + ReaComp**
- 轨 1–6 六层素材 · 轨 `5_wildlife` **ReaVerbate** · 轨 7 视频（静音，仅渲染）
- **Dynamic** = 无轨，由 `vol_envelope` 等自动化穿插调节

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

## MVI_6888

- 分析与配方（初版）：[`subprojects/MVI_6888/video_analysis.md`](subprojects/MVI_6888/video_analysis.md)
- 视频：`assets/loop_video/rain_video/MVI_6888/MVI_6888_loop_8_fade_0.5.mp4`（无内嵌音轨）

## MVI_6918

- 分析与配方：[`subprojects/MVI_6918/video_analysis.md`](subprojects/MVI_6918/video_analysis.md)

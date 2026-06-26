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

产出 `video_analysis.md`、`scripts/asmr_config.lua`、`<scene>.rpp`；打开工程后运行 **`asmr_apply_recipe.lua`**（轨 2 长时包络在配方 `vol_envelope` 里，由脚本写入，不预画在 rpp）。

**仅生成 `.rpp`（配方已存在）：**

```bash
python3 Reaper/scripts/generate_subproject.py --scene MVI_6918
```

生成器将素材 **直接引用** `assets/`（WSL UNC 全路径，不复制到 `Audio Files`）。

**模板自带：**

- 轨 **Group**（Folder 父轨）· **ReaEQ + ReaComp**
- 轨 1–7 在 Folder 内 · 轨 `6_life` 带 **ReaVerbate** · 轨 8 视频在 Folder 末（静音，仅渲染）

## 打开工程后

1. Reaper 打开 `MVI_6918.rpp`
2. 运行 `asmr_apply_recipe.lua`（循环 + 稀疏 + 轨 2 包络；**按轨名匹配，不受 Group 占位影响**）

详见 [`Reaper/scripts/README.md`](../../scripts/README.md)。

## 轨布局

| 轨 | 层 | 模式 | 说明 |
|----|-----|------|------|
| **Group** | 总线 | Folder | **ReaEQ + ReaComp**（模板自动） |
| 1 | 1_base | loop | 混音 |
| 2 | 2_rain | loop | 混音 |
| 3 | 3_impact | scatter | 混音 |
| 4 | 4_water | loop | 混音 |
| 5 | 5_env | loop | 混音 |
| 6 | 6_life | scatter | 混音 · **ReaVerbate** |
| 7 | 7_comfort | loop | 心理舒适 · 安全感锚点（可叠多条） |
| **8** | **视频 looper** | — | **Folder 末轨 · 仅渲染，混音时不改** |

模板定义：[`scripts/layer_template.lua`](scripts/layer_template.lua) · JS 源：[`scripts/fx/asmr_sleep_hf_eq.jsfx`](scripts/fx/asmr_sleep_hf_eq.jsfx)

## MVI_6888

- 分析与配方（初版）：[`subprojects/MVI_6888/video_analysis.md`](subprojects/MVI_6888/video_analysis.md)
- 视频：`assets/loop_video/rain_video/MVI_6888/MVI_6888_loop_8_fade_0.5.mp4`（无内嵌音轨）

## MVI_6918

- 分析与配方：[`subprojects/MVI_6918/video_analysis.md`](subprojects/MVI_6918/video_analysis.md)

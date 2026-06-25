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

```bash
# 1. 写 video_analysis.md（§一画面 → §二原声 → §三配方）+ asmr_config.lua
python3 Reaper/scripts/generate_subproject.py --scene MVI_6918
```

生成器会将素材 **直接引用** `assets/`（WSL UNC 全路径，不复制到 `Audio Files`）。

**模板自带：**

- 轨 **Group**（Folder 父轨）· `JS ASMR Sleep HF EQ` + `ReaComp`
- 轨 1–7 在 Folder 内 · 轨 8 视频在 Folder 末（静音，仅渲染）

首次打开若 JS 未识别，运行一次 `asmr_apply_group_eq.lua`（会安装到 `Effects/relaxASMR/`）。

## 打开工程后

1. Reaper 打开 `MVI_6918.rpp`
2. 运行 `asmr_apply_recipe.lua`（循环 + 稀疏 + 轨 2 包络；**按轨名匹配，不受 Group 占位影响**）

详见 [`Reaper/scripts/README.md`](../../scripts/README.md)。

## 轨布局

| 轨 | 层 | 模式 | 说明 |
|----|-----|------|------|
| **Group** | 总线 | Folder | **JS 削高频 + ReaComp**（模板自动） |
| 1 | 1_base | loop | 混音 |
| 2 | 2_rain | loop | 混音 |
| 3 | 3_impact | scatter | 混音 |
| 4 | 4_water | loop | 混音 |
| 5 | 5_env | loop | 混音 |
| 6 | 6_life | scatter | 混音 |
| 7 | 7_comfort | loop | 心理舒适 · 安全感锚点（可叠多条） |
| **8** | **视频 looper** | — | **Folder 末轨 · 仅渲染，混音时不改** |

模板定义：[`scripts/layer_template.lua`](scripts/layer_template.lua) · JS 源：[`scripts/fx/asmr_sleep_hf_eq.jsfx`](scripts/fx/asmr_sleep_hf_eq.jsfx)

## MVI_6918

- 分析与配方：[`subprojects/MVI_6918/video_analysis.md`](subprojects/MVI_6918/video_analysis.md)

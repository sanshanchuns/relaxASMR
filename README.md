# relaxASMR 工程化工作流

本项目是一套高度自动化的 ASMR 视频工作流，由底层 Python 脚本与 Reaper 脚本配合，并封装为易用的 GUI 界面 (`python -m gui`)。

---

## 5 步工作流（GUI）

| 步骤 | 操作 | 效果 |
|------|------|------|
| **1** | 选择 MP4 | 拷贝至 `assets/loop_video/rain_video/MVI_XXXX/` |
| **2** | 宫格选声源 + 分析 | CLIP/VLM 匹配 `1_rain` 等；生成物料（标题、缩略图等） |
| **3** | 新建 Reaper 工程 | 按下方「工程生成规则」生成 `.rpp`（可勾选覆盖已有工程） |
| **4** | 混音 + 合成 MP4 | Headless 渲染 WAV → FFmpeg 合成；默认片头 5 秒 fade-in |
| **5** | 上传 YouTube | 读取物料 + 成片自动上传 |

数据根目录（baseURL）默认：`/mnt/e/自然之声/to_youtube/`（见 `scripts/config/paths.py`）。

---

## Reaper 工程生成规则（步骤 3）

本节是**人类可读规范**；实现以代码为准（见文末「规则存放位置」）。用户可在 `gui/user_config.json` 覆盖部分响度参数。

### 轨道结构（Rain 四层 + 视频）

| 轨号 | layer_id | 名称 | 模式 | 选中声源时 |
|------|----------|------|------|------------|
| 1 | `1_rain` | 主雨势 | 循环 `LOOP 1` 铺满成片时长 | 写循环 item |
| 2 | `2_impact` | 雨打树叶 | 循环 `LOOP 1` 铺满成片时长 | 写循环 item |
| 3 | `3_random` | 远处雷声 | 稀疏散布（oneshot） | 随机 **100** 个 item |
| 4 | `4_wildlife` | 野生生态 | 稀疏散布（oneshot） | 按间隔公式自动算个数 |
| 5 | video | 循环视频 | 仅渲染用 | 轨道静音 `vol=0` |

未选声源的轨：**留空**，不写入 item。

### 稀疏散布（`3_random` / `4_wildlife`）

| 层 | 个数 | 间隔（分钟） | 随机度 | 说明 |
|----|------|--------------|--------|------|
| `3_random` | **固定 100** | min 5 / max 15（用于位置 jitter） | 0.6 | 素材均为**远处雷声** |
| `4_wildlife` | 按 `(成片时长 − 素材长) ÷ 平均间隔` 估算 | min 12 / max 28 | 0.55 | — |

- 散布 item 的 `VOLPAN` **固定 1.0**；只调**轨道推子**。
- 位置：在 `[0, 成片时长 − 素材长]` 内均匀分段 + 随机 jitter。

### 轨道音量 / 响度归一

生成工程时（`build_scene_config_from_gui`）用 **ffmpeg loudnorm** 测 LUFS-I（integrated），最长分析 180 秒；多文件时取**最响**一条。

| 层 | 机制 | 默认目标 / 推子 |
|----|------|-----------------|
| **`1_rain`** | 动态 LUFS → 轨道推子 | 目标 **−28 LUFS-I**（`lufs_target_min/max`） |
| **`3_random`** | 动态 LUFS → 轨道推子 | 目标 = 主 bed **+3 LU**（即 **−25 LUFS-I**）；`random_lufs_offset_db` 默认 `3` |
| **`2_impact`** | legacy 固定推子 | **0.5** |
| **`4_wildlife`** | legacy 固定推子 | **0.28** |

推子换算：`gain_db = target_lufs − measured_lufs + lufs_fx_compensation_db`，`vol = 10^(gain_db/20)`，限制在 `[0.01, 128]`。

- **`3_random` 测量失败**：推子 fallback **0.35**。
- **`1_rain` 测量失败**：保持模板默认 vol（1.0）。
- 主 bed 与 `3_random` **各自**归一化到不同 LUFS 目标，不是「主轨推子 × 比例」。

### Group 总线与 FX

- **Group**：开头 **5 秒** fade-in（`GROUP_FADE_IN_SEC`）；**ReaLimit**（Ceiling −1 dB）。
- **轨级 FX（生成时写入，默认旁路）**：`1_rain` ReaEQ；`4_wildlife` ReaVerbate。
- **`1_rain` 长时包络**：`.rpp` 内为平直推子；打开工程后手动运行 `asmr_vol_envelope.lua`。

### Reaper 渲染 / 时间选区（`.rpp` 默认值）

- **Render bounds**：**Entire Project**（`RENDER_RANGE 1 …`，bounds=1）；Headless 渲染（`-renderproject`）据此输出完整成片。
- **Time selection**：默认选中**前 5 分钟**（`SELECTION` / `SELECTION2` = 300 s），便于在 Reaper 内试听；与 Render bounds 独立（bounds=2 才是 Time selection）。
- **工程长度**：`MAXPROJLEN` 仍为成片时长（如 3 h = 10800 s）。

### 视频导出（步骤 4）

- 默认 **片头 5 秒** fade-in（`VIDEO_FADE_IN=5`），与 Group 5 秒 fade-in 对齐。
- 可选：`--no-video-fade-in`、`--video-fade-in SEC`。

---

## 用户可配置项（`gui/user_config.json`）

| 键 | 默认 | 作用 |
|----|------|------|
| `lufs_target_min` / `lufs_target_max` | −28 | 主 bed `1_rain` 的 LUFS 目标 |
| `random_lufs_offset_db` | **+3** | `3_random` 相对主 bed 的 LU 偏移 |
| `lufs_fx_compensation_db` | 0 | EQ 链响度补偿（dB） |
| `duration_hours` | 3 | 默认成片时长 |
| `theme` | — | GUI 浅/深色 |

---

## 规则存放位置（实现源码）

此前规则**分散在代码中**，没有单独设计文档；**本 README 为汇总说明**，修改默认值时请同步改代码常量。

| 内容 | 文件 |
|------|------|
| LUFS 目标、偏移、legacy 推子、`3_random` fallback | `scripts/new_reaper_project/audio_loudness.py` |
| 层配方（轨号、散布 count/gap、时长） | `Reaper/scripts/rain_subproject_lib.py` → `build_asmr_config()` |
| GUI 步骤 3 选源 + 响度写入 | `Reaper/scripts/rain_subproject_lib.py` → `build_scene_config_from_gui()` |
| `.rpp` 生成（散布 item、Group fade、FX） | `Reaper/scripts/generate_subproject.py` |
| baseURL、素材路径 | `scripts/config/paths.py` |
| 视频 fade-in | `scripts/video_export/export_mp4.sh` |
| Reaper 内手动散布脚本 | `Reaper/scripts/asmr_scatter_track.lua` |
| 系列设计背景（非生成默认值） | `design/rain_series/rain_sound_design.md` |

场景 JSON（若存在）：`Reaper/Projects/Rain/scripts/scenes/<scene_id>.json`（由 `create_rain_subproject.py` 写入；GUI 步骤 3 可直接 `build_rpp` 不写 JSON）。

---

## 快速启动

```bash
cd /path/to/relaxASMR
python -m gui
```

WSL 下 Reaper 媒体路径：`/mnt/e/...` → `E:\...` 盘符；`/home/...` 仓库 → `\\wsl.localhost\Ubuntu\...` UNC（见 `Reaper/scripts/media_paths.py`）。

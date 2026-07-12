# preset_db · 雨声库（1_rain/sounds）重新生成

从 Natural Rain VST preset 批量渲染 **2160 条**无缝循环雨声，替换 `baseURL/audio/1_rain/sounds/` 下的旧 10s 素材。

入口脚本（仓库根目录执行）：

```bash
python3 -m scripts.video_analysis.regenerate_rain_sounds <子命令>
```

等价 shell 包装：`scripts/video_analysis/regenerate_rain_sounds.sh`

---

## 背景

旧库为 **10s WAV**，首尾含静音，GUI 循环拼接会出现空档。新流程：

1. VST 渲染 **42s** 长片段（留 VST 暖机/收尾余量）
2. 在稳定段内 **滑动搜索最佳 30s 窗口**（最小化首尾 RMS / Mel 频谱差）
3. 安装到 `sounds/`，供 Reaper `asmr_loop_track` 与 GUI 声音库使用

实测 optimize 裁切后循环接缝 RMS 差通常 **≤ 0.05 dB**（旧固定裁切约 3–10 dB）。

---

## 目录结构

```
scripts/video_analysis/preset_db/
├── README.md                          ← 本文
├── natural_rain_rpps/                 源 RPP 模板（10s，2160 个）
│   └── render_jobs/                   prepare 生成的 42s 渲染工程
├── natural_rain_presets/              .rain preset 文件
├── natural_rain_regen/                运行元数据
│   ├── manifest.json                  本次任务参数与 job_stems 列表
│   ├── trim_report.json               裁切/接缝评分报告
│   └── batch_session.lua              当前批次 Reaper 脚本（自动生成）
└── natural_rain_attachments/          附件与批量 Lua
    ├── batch_render_regen.lua         prepare 生成的全量 Lua（可选 GUI 运行）
    └── Parameters_Explanation.md      VST 参数说明

<仓库根>/tmp/rain_regen/               临时 WAV（本地盘，完成后自动删除）
├── regen_raw/                         42s Reaper 渲染输出
└── regen_trimmed/                     30s optimize 成片（安装前 staging）

baseURL/audio/1_rain/
└── sounds/                            ★ 最终产物（30s 循环 WAV，2160 条）
```

**原则**

- **baseURL** 只放最终渲染产物（wav / mp4 / 物料）；临时 wav 在工程 `tmp/`。
- **preset_db** 放 RPP、Lua、manifest、报告等工程文件（可进 git，大体积 wav 已在 `.gitignore` 排除 `tmp/rain_regen/`）。

---

## 默认参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `render_s` | **42** | Reaper 渲染时长（秒） |
| `output_s` | **30** | 最终成片时长（秒） |
| `search_margin_head/tail` | **2** | 在 `[2s, render_s−30−2s]` 内搜索最佳窗口 |
| `optimize_metric` | `combined` | `seam + mel×8` 综合评分 |
| `trim_mode` | `optimize` | 滑动窗口裁切（非固定去头尾） |

---

## 推荐流程：分批（每批 50 条）

每批：**单 Reaper 进程渲染 → optimize 裁切 → 安装到 sounds**，临时 wav 自动清理。

```bash
# 1. 生成 2160 个 render_jobs + manifest（只需跑一次，或参数变更后重跑）
python3 -m scripts.video_analysis.regenerate_rain_sounds prepare

# 2. 跑一批（50 条：render → trim → install）
python3 -m scripts.video_analysis.regenerate_rain_sounds batch --size 50

# 3. 连续跑完全部剩余批次
python3 -m scripts.video_analysis.regenerate_rain_sounds batch --size 50 --all
```

**断点续跑**：已写入 `sounds/` 的条目会自动跳过；`regen_raw` 里已有的 wav 在 render 时 `--skip-existing` 跳过。

**进度查看**（若后台运行）：

```bash
tail -f tmp/rain_regen/batch.log   # 若手动 tee 了日志
ls baseURL/audio/1_rain/sounds/*.wav | wc -l
```

---

## 子命令说明

| 子命令 | 作用 |
|--------|------|
| `prepare` | 从 `natural_rain_rpps/*.rpp` 生成 `render_jobs/`（42s）+ `manifest.json` + `batch_render_regen.lua` |
| `render` | Reaper 渲染 → `tmp/rain_regen/regen_raw/` |
| `trim` | optimize 裁切 → `tmp/rain_regen/regen_trimmed/`（默认删对应 raw） |
| `install` | 复制 trimmed → `sounds/`（默认不备份、不清空已有） |
| **`batch`** | **一批内串联 render → trim → install（推荐）** |
| `verify` | 检测 `sounds/` 首尾接缝 RMS 差 |
| `cleanup` | 手动清理 `tmp/rain_regen/` 及 baseURL 旧临时目录 |
| `repair-trim` | 仅对现有 sounds 做静音裁切（不重新渲染 VST） |
| `pipeline` | prepare → render → trim → install 一键（适合小批量测试） |

### 分步示例（调试）

```bash
python3 -m scripts.video_analysis.regenerate_rain_sounds prepare --limit 10
python3 -m scripts.video_analysis.regenerate_rain_sounds render --limit 10
python3 -m scripts.video_analysis.regenerate_rain_sounds trim --mode optimize
python3 -m scripts.video_analysis.regenerate_rain_sounds install
python3 -m scripts.video_analysis.regenerate_rain_sounds verify --limit 20
```

### 测试单条

```bash
python3 -m scripts.video_analysis.regenerate_rain_sounds prepare --limit 1 --offset 659
python3 -m scripts.video_analysis.regenerate_rain_sounds batch --size 1
```

---

## Reaper 渲染方式

默认 **单进程 + ReaScript**（每批只启动一次 Reaper，避免 2160 次冷启动）：

1. Python 写入 `natural_rain_regen/batch_session.lua`（仅含本批待渲染 rpp）
2. 调用 `reaper.exe -nosplash batch_session.lua`
3. Lua 循环：`Main_openProject` → `Main_OnCommand(42230)`（Render）→ 最后 Quit

回退为逐条 `-renderproject`（慢）：`render --no-use-lua` 或 `batch --no-use-lua`。

**前置条件**

- Windows Reaper 已安装且 Rain VST 可用（路径见 `gui/user_config.json` → `reaper_exe`）
- WSL 下通过 `wslpath -w` 写 Windows 原生路径；42s wav 输出到工程 `tmp/`（Reaper 可写）

---

## optimize 裁切原理

在 42s raw 中，于搜索区间（默认 2s ~ 10s 起点）以 **50ms** 步长滑动 **30s** 窗口，对候选段计算：

- **seam**：首尾 50ms RMS 差（dB，越小越好）
- **mel**：首尾 Mel 频谱 L2 差
- **combined**：`seam + mel × 8`（默认优化目标）

选出 cost 最小的窗口导出为 30s 成片。

相关实现：`scripts/video_analysis/rain_sound_loop.py`（`find_best_loop_window` / `trim_wav_best_window`）。

---

## manifest.json 字段

`natural_rain_regen/manifest.json` 记录一次 prepare 的全局配置，供 render / trim / batch 读取：

- `render_s`, `output_s`, `search_margin_head/tail`, `optimize_metric`
- `job_stems`：本次任务全部 preset 名称（有序）
- `jobs_dir`, `raw_dir`, `trimmed_dir`, `sounds_dir`：路径快照

---

## 常见问题

**Q: prepare 后 render_jobs 里 RPP 输出路径在哪？**  
A: `RENDER_FILE` 指向 `<仓库>/tmp/rain_regen/regen_raw/<stem>.wav`（Windows 路径形如 `\\wsl.localhost\Ubuntu\home\...`）。

**Q: 安装会清空已有 sounds 吗？**  
A: `batch` / 默认 `install` **增量追加**，`clear_sounds` 默认 true 但 batch 模式强制 `clear_sounds=false`。全量替换请先手动清空 `sounds/`。

**Q: 临时 wav 何时删除？**  
A: trim 成功后删 raw；install 成功后删 trimmed（均可用 `--keep-raw` / `--keep-temp` 保留）。

**Q: 如何只修复旧 10s 库、不重新渲染？**  
A: `python3 -m scripts.video_analysis.regenerate_rain_sounds repair-trim --dry-run` 预览后去掉 `--dry-run`。

---

## 相关文件

| 文件 | 说明 |
|------|------|
| `scripts/video_analysis/regenerate_rain_sounds.py` | 主 CLI |
| `scripts/video_analysis/rain_sound_loop.py` | 静音检测 / optimize 窗口 / 接缝评分 |
| `gui/reaper_launch.py` | `run_reaper_lua()` / `render_reaper_project()` |
| `scripts/config/paths.py` | `baseURL` / `audio_dir()` 解析 |

# relaxASMR 对话上下文摘要（供新 Agent 接续）

## 项目与路径

- **仓库**：`/home/leo/workspace/relaxASMR`
- **GUI**：`python -m gui` → `gui/app.py`
- **配置**：`gui/user_config.json`（含 `theme`、`export_outputs`、`duration_hours` 等）
- **baseURL**：`scripts/config/paths.py` → `base_url()`，典型为 `/mnt/e/自然之声/to_youtube`
- **关键目录**：
  - 物料：`baseURL/material/`（`MVI_xxx_material.json|md`、`MVI_xxx_thumbnail.jpg`）
  - 成片：`baseURL/export/`（`MVI_xxx_3h_fhd.mp4` / `_4k.mp4`、混音 WAV）

---

## 本会话已完成改动（按模块）

### GUI 工作流（`gui/app.py`）

| 区域 | 改动要点 |
|------|----------|
| **步骤 1** | 「打开物料目录」在「开始分析」后；深浅模式按钮同排；「开始分析」蓝色高亮；MP4 路径单行不换行 |
| **步骤 3** | 按钮顺序：新建Reaper工程 → 打开Reaper工程 → 成片时长 → 覆盖.rpp；「新建Reaper工程」蓝色高亮 |
| **步骤 4** | 混音/合成按钮蓝色高亮；完成后状态显示 **平均码率 + 体积**（如 `6.2 Mbps · 10G`） |
| **覆盖确认** | 步骤3覆盖 rpp、步骤4覆盖合格 WAV/MP4 前弹窗确认 |
| **主题** | `gui/ui_theme.py` 浅/深色切换，写入 `user_config.json` 的 `theme` |
| **进度** | `gui/job_progress.py` 主线程 250ms 刷新 Elapsed/Remaining；日志过滤 PROGRESS 行 |
| **线程安全** | `gui/tk_thread.py`：后台线程不得直接 `after()`；素材库/上传日志用队列调度 |

### 视频合成（`scripts/video_export/export_mp4.sh`）

- **默认质量模式**（非固定码率）：**CRF/CQ**，按画面复杂度自适应
  - 4K：CRF/CQ 20，maxrate 25M
  - FHD：CRF/CQ 22，maxrate 10M
- 可选 `--video-bitrate` 回到固定码率（4K 20M / FHD 8M）
- 3h 粗估体积：FHD ~6–12G，4K ~15–25G（旧固定 30M 时两者都 ~38G）

### 稀疏层响度（此前会话延续）

- 2/3/4 配方去掉固定 `vol`
- **3_random**：动态 LUFS，目标 = 主 bed **-10 LU**（可配 `random_lufs_offset_db`）
- 2_impact / 4_wildlife：legacy 推子 0.5 / 0.28

### 步骤 5 一键上传 YouTube

1. **物料兼容**：优先 `MVI_xxx_material.json`，否则 `MVI_xxx_material.md`（`material_store.py` / `material_metadata_path`）
2. **默认带封面**：`baseURL/material/MVI_xxx_thumbnail.jpg`
3. **物料/封面缺失时**：**不要求**步骤1已选 MP4；在 **baseURL 根目录**按同序号找 `MVI_xxx*.mp4`，自动跑完整「开始分析」，再上传
4. **仅当 baseURL 也找不到 loop** 才弹窗阻止
5. **上传日志**（`youtube_upload.py`）打印：物料文件、标题、描述（多行缩进）、封面文件名；设置封面时再打一次

---

## 重要代码入口

```
gui/app.py
  _upload_youtube()           # 步骤5
  _ensure_material_for_upload()
  _ensure_thumbnail_for_upload()
  _loop_video_for_upload()    # 仅 baseURL 找 loop，不用 GUI 选中视频
  _make_upload_progress_updater()
  _format_export_status()     # 追加码率+体积

gui/export_wav.py
  format_mp4_export_stats_suffix()  # ffprobe 均码 + 文件大小

gui/ui_theme.py / gui/job_progress.py / gui/tk_thread.py

scripts/video_export/export_mp4.sh   # CRF/CQ 质量编码
scripts/video_upload/youtube_upload.py # 上传 + 元数据日志
scripts/video_upload/material_store.py
scripts/config/paths.py              # material_metadata_path, get_thumbnail_path
```

---

## 测试（已通过）

- `scripts/tests/test_ui_theme.py`
- `scripts/tests/test_tk_thread.py`
- `scripts/tests/test_job_progress.py`
- `scripts/tests/test_export_wav.py`（含体积/码率后缀）
- `scripts/tests/test_upload_progress.py`
- `scripts/tests/test_scatter_layer_vol.py` 等

---

## 用户偏好 / 规则

- 回复用**中文**
- 不要主动 git commit
- GUI 日志**只 append**，进度不进日志（避免刷屏）
- 代码改动宜**小范围、匹配现有风格**

---

## 未做 / 可选后续

- 素材库宫格在**深色模式**下的单元格样式（主窗口已主题化）
- 若用户要更细的上传前校验或 md→json 批量迁移，需另开任务

---

## 给新 Agent 的快速验证

```bash
cd /home/leo/workspace/relaxASMR
python -m gui
python -m pytest scripts/tests/test_export_wav.py scripts/tests/test_job_progress.py -q
```

上传 6989 场景：有 `MVI_6989_material.md` 无 json 即可；缺物料时会从 baseURL 找 `MVI_6989*.mp4` 自动分析。
# CONTEXT：relaxASMR（压缩）

> 后续会话恢复用。只保留决策、路径、坑与「下一步」；细节以代码为准。

## 产品结构（GUI 顶部 Tab）

| Tab | 内容 |
|---|---|
| 工作流 | 导入 → 音效 → Reaper → 导出 → 上传 |
| 数据分析 | 子 Tab：我的数据 / 爆款分析 |
| 素材库 | 视频 + 各音频库 |
| AIGC | 参考图/主体 → 三档提示词 → 抽卡 → 后验（无子 Tab） |

入口：`python -m gui`。`cli/` 经 `ensure_cli_path()` 进 `sys.path`。

---

## Gemini 调用（硬规则）

**凡是 Gemini，统一走 agy**（`cli/agy/`）。AIGC 提示词生成与后验 VLM（`prompt_gen.py` / `posterior.py`）遵守此条；勿用 `GEMINI_*` env key 直连。

---

## jimeng_web（本会话已打通）

| 项 | 值 |
|---|---|
| 入口 | `home?type=video`（非旧 assets-canvas） |
| 模型 | `Seedance 2.0 Fast VIP`（AIGC 默认；`JIMENG_VIDEO_MODEL` 可改） |
| 参考 | 默认 **首尾帧**（同图×2）；`JIMENG_REF_MODE` 可改全能参考 |
| 画幅/时长 | 16:9 720P · **6s**（AIGC 顶栏可改） |
| 登录判定 | 侧栏无「登录」；`status` 勿信正文模糊匹配 |
| 进度 | 读结果卡「`N%造梦中`」→ AIGC：**生成按钮** `造梦进度：N%` |
| 落盘 | `<video>` 直链 / **blob:** / 下载图标；校验 ffprobe 或体积极下限；**检测到新结果时日志打印全部 video 链接** |
| 已有结果 | 提交前若页面已有同 prompt +「再次生成」→ **直接下载，跳过提交** |
| 手动入库 | ``attach_run_video(run_id, mp4)`` → ``runs/<id>/video.mp4`` |
| 落盘 | 忽略历史 `<video>` → 等新片 → `context.request` 直链 |
| Profile | `cli/jimeng_web/.profile/` + **`.profile.lock`**（防额度面板抢 Chromium） |
| 共享基座 | `cli/shared/browser.py`（agy / jimeng / elevenlabs 共用；`PYTHONPATH=cli`） |

```bash
PYTHONPATH=cli:. python -m jimeng_web login
PYTHONPATH=cli:. python -m jimeng_web generate \
  --image …/ref.jpg --prompt "…" --out …/out.mp4 --duration 5
```

生成中勿点额度面板 Jimeng 刷新。失败截图：`cli/jimeng_web/debug/`。

**文生（AIGC Tab）**：`generate_t2v(prompt, …)` · 默认 **6s**（顶栏 1–15 + 每档张数 1–10，写 `params.json`）/ 16:9 / 720p / **Seedance 2.0 Fast VIP**。参考图只当主体/材质锚点。

```bash
PYTHONPATH=cli:. python -m jimeng_web generate-t2v --prompt "…" --out …/runs/xxx/video.mp4
```

---

## AIGC 抽卡（2026-08-19）

**产品**：雨 ASMR（含木屋/小船等人造物）。**无子 Tab、无六槽**。参考图只当题材/材质锚点，一律文生视频。

**流程**：主体关键词或参考图 → Gemini 一次产出三档四段 prompt（画面 / 光影 / 动态 / 约束）→ 每档抽卡（Fast VIP · 16:9 · 720p · **6s**）→ 后验。

| 雨档 id（沿用，勿改） | 显示 |
|---|---|
| `light_mod` | 小雨 drizzle |
| `heavy` | 中雨 moderate |
| `storm` | 暴雨 downpour |

后验三层（`posterior.py`）：运动量/闪烁/硬切闸门 → 断言 VLM 核对 → 人工采用/废弃。动态段可写绿植约 3 秒小幅平滑摆动、首尾帧吻合；禁止剧烈/舞蹈式晃动。循环成片仍可由外部 loop 工具再处理。Jimeng Agent 手册仅作参考，不自动问答。

| 路径 | 说明 |
|---|---|
| `gui/aigc_flow_tab.py` | 单页主流程 |
| `gui/aigc_preview_panel.py` | 右侧预览（视频 + prompt；有参考图则左图右文） |
| `scripts/aigc_lab/prompt_gen.py` | 三档 prompt + 断言 |
| `scripts/aigc_lab/posterior.py` | 后验 |
| `scripts/aigc_lab/rain_modes.py` · `subject_pool.py` | 雨档 / 常用主体 |
| `scripts/aigc_lab/agent_store.py` | runs：`prompt.txt` · `meta.json` · `posterior.json` · `video.mp4` |
| `cli/jimeng_web/agentic.py` | Agent 页（技能挂载仍可用） |

落盘：`aigc/agent_t2v_lab/runs/`。会话：`flow_session.json`（主体/参考图/三档草稿）。

---


## 架构决策（累计）

| 变更 | 原因 |
|---|---|
| 删 `cli/dreamina/` | 官方 CLI 体验差 |
| GUI 重 I/O 放后台 | 启动卡死、步骤 4 ffprobe/NAS 阻塞主线程 |
| `find_export_wav_for_scene` | legacy `_3h.wav` 与 `_180min.wav` 双格式 |
| GUI 合成 `--no-video-fade-in` | 去掉成片视频片头 5s 淡入 |
| AIGC 预览隔离 | 独立 `AigcPreviewPanel` + 分 mode sash；勿与工作流 cover/video 共用 |
| AIGC 默认模型 | Fast VIP（`params.json` / `client.py` `DEFAULT_VIDEO_MODEL`） |
| 图生技能启用 | 新建/选用后必须点「去使用」才挂到对话 |
| 成片默认 90min | `DEFAULT_DURATION_MINUTES`（原 100）；GUI 无配置时兜底 90 |
| WSL 大 WAV 试听 | 勿走 ffplay/Pulse；一律 Windows SoundPlayer + `booms_16bit` |
| impact 宫格 | `sounds/` + `booms/`；boom 试听同 rain/random/wildlife |
| `elevenlabs_web`→`elevenlabs_http`；新建 Playwright 双包 | HTTP 挂时 UI 兜底 |
| `shared` 在 `cli/shared/` | 入口须 `ensure_cli_path()` 或 `PYTHONPATH=cli` |
| jimeng 默认 VIP+首尾帧+5s | loop 硬约束 + 产品档位 |
| profile 文件锁 | `available()`/额度轮询与 generate 抢同一 profile 会关浏览器 |

EL Web：`https://elevenlabs.io/app/image-video?modality=video`  
Profile：`cli/elevenlabs_web/.profile/`（与 http 独立）

---

## 包路径

| 包 | 位置 | 说明 |
|---|---|---|
| `agy` | `cli/agy/` | Gemini 文本/出图 |
| `jimeng_web` | `cli/jimeng_web/` | 即梦 Playwright（主通道） |
| `elevenlabs_http` | `cli/elevenlabs_http/` | HTTP+token；**勿名 `elevenlabs`** |
| `elevenlabs_web` | `cli/elevenlabs_web/` | EL 页 Playwright |
| `shared.*` | `cli/shared/` | browser 基座 + llm_log（cli 包共用） |

---

## ElevenLabs 鉴权（坑）

- API Key 常 403；HTTP 用 Firebase Bearer + `model_parameters`；常需 hcaptcha
- Bearer ~1h；`refresh_token.md` 续期
- 上传会话曾缺 `name`/`file_size`/`content_type` → 422

```bash
pip install playwright && playwright install chromium
PYTHONPATH=cli:. python -m elevenlabs_http login
PYTHONPATH=cli:. python -m elevenlabs_web login
```

---

## 工作流 · 成片时长（2026-08-05）

**单位已改为分钟**；旧「小时」配置仍可读（自动 ×60）。

| 项 | 值 |
|---|---|
| GUI 标签 | `成片时长(分钟)`（步骤 3） |
| 默认 | **90** 分钟 |
| 配置键 | `duration_minutes`（`gui/user_config.json`）；保存时删旧 `duration_hours` |
| 兼容读取 | `duration_hours` / 旧 `target_duration`（小时字符串）→ UI 显示分钟 |
| 导出后缀 | `100min`（非旧 `3h`），如 `MVI_1002_100min.wav` / `_100min_fhd.mp4` |
| 核心 API | `scripts/config/paths.py`：`cfg_duration_minutes()`、`duration_render_suffix(minutes)` |
| 校验 | `gui/export_wav.py`：`wav_matches_target_minutes()`（±30s） |

**涉及模块**：`gui/app.py` · `gui/reaper_launch.py` · `Reaper/scripts/{generate_subproject,rain_subproject_lib,create_rain_subproject,asmr_config_parser}.py` · `asmr_loop_track.lua`（默认 90）

**坑**
- 旧 `_3h` 成品与新 `_100min` 命名不互通；仍用 3h 成片请在 GUI 填 **180** 分钟
- **WAV 混音**曾只认 `{scene}_180min.wav`，不认 legacy `{scene}_3h.wav` → 步骤 4 显示「待开始」；已修：`find_export_wav_for_scene()`（与 MP4 对称）
- 场景 JSON 字段：`duration_minutes`（旧 JSON 含 `duration_hours` 时 `cfg_duration_minutes` 仍可读）
- `gui/youtube_material.py` 打分：保留 `_3h`，另认 stem 含 `min`
- **合成视频片头 fade-in**：GUI 主流程已传 `--no-video-fade-in`（`export_mp4.sh` 默认仍 5s）；Reaper Group 音频 fade 不受影响

**测试**：`scripts/tests/test_export_wav.py` · `test_rpp_render_range.py` · `test_build_scene_config_from_gui.py`

---

## GUI · 线程原则（2026-08-06，硬规则）

**除刷新界面外，其它操作一律放后台**；主线程只做 Tk 控件读写与布局。

| 允许主线程 | 必须后台（`threading` + `schedule_on_main` 回写 UI） |
|---|---|
| 建控件、改 Label/Button 状态、布局 sash | NAS/`ffprobe`、路径 `is_file` 批量探测 |
| `_repaint_tag_borders` / 就地改边框色 | 工作流恢复、步骤 4 混音/成片存在性校验 |
| 用户点击后的即时视觉反馈（无 I/O） | 音库选中恢复、`_finish_set_video_heavy` 分析缓存读取 |
| | 即梦/EL 登录与生成、后验 VLM、export_mp4/render |

**启动（曾卡死 ~30s）**：窗口 `_reveal_when_layout_ready` **同步先显现**；`_restore_workflow_state` / `_restore_audio_library_selections` 改 `after(50)`；`_refresh_step4_outputs(..., background=True)` 与 `_apply_finish_set_video_heavy` 探测在子线程。

**模块**：`gui/tk_thread.py`（`schedule_on_main` / `ensure_ui_pump`）· `gui/app.py` · `gui/aigc_flow_tab.py`

---

## GUI · WSL 剪贴板（Tk Text 只能复制一次）

**现象**：WSLg / VcXsrv 下 `tk.Text` 默认走 X11 `CLIPBOARD`；第一次 Ctrl+C 后 X 连接易坏
（`X connection to :0 broken`），后续复制/粘贴失败。AIGC Prompt、日志区等均可复现。

**方案**（同 `economist/gui/widgets.py`，本仓库 `gui/clipboard.py`）：

| 函数 | 用途 |
|---|---|
| `setup_editable_text_copy` | 可编辑 Text：拦截 `<<Copy>>` / Ctrl+C，写 **Windows 宿主剪贴板**（PowerShell `Set-Clipboard`） |
| `setup_copyable_readonly_text` | 只读 Text：可选中/复制/右键菜单；**勿用** `state=DISABLED`（禁用态收不到复制事件） |
| `setup_global_clipboard_safety` | 全局安全粘贴（`<<Paste>>` / Ctrl+V），读 Windows 剪贴板，避免大 payload 走 X11 |

**要点**
- WSL 复制成功时 **不再** `clipboard_append` 到 Tk/X11（大段中文 prompt 会炸 DISPLAY）
- 进程内保留 `root._relaxasmr_clipboard_hold` 供同 app 内粘贴兜底
- CJK 须走 PowerShell UTF-16 stdin / 临时文件；**勿**用 `clip.exe` 传中文（CP936 乱码）

**已接入**
- `gui/app.py`：启动时 `setup_global_clipboard_safety`；日志区 `setup_copyable_readonly_text`
- `gui/aigc_flow_tab.py`：详情区与三档 prompt `setup_copyable_readonly_text`
- `gui/aigc_preview_panel.py`：预览区视频 + `gui/audio_playback.py` ffplay 循环音

**新增 Text 控件时**：可编辑走 `setup_editable_text_copy`；只读走 `setup_copyable_readonly_text`，程序写内容直接 `delete`/`insert`，不要 toggling `DISABLED`。

---

## GUI · 输入法

- 已删 `gui/ime_bootstrap.py` 及 `ui_theme.make_ime_entry` / `style_ime_entry`
- 启动日志**无** WSL 输入法提示；走系统默认 IME

---

## 其他 Tab

- 数据分析：YouTube API + agy；黑马 `views_per_day`；WSL 开 URL 用 Chrome profile
- agy 换号失败：额度/模型容量；`[WARN]` 后有 API 详情

---

## 素材库 · raw 视频

- 宫格字段：码率（ffprobe `format.bit_rate`）、ISO 四舍五入取整；单击封面放大 + 右侧参数；双击无动作。
- 缓存：`material_dir/.raw_video_meta/*.json`（内存+磁盘）；首次占位再填。
- Sony a7m4：XAVC 参数在 `rtmd`，需 `exiftool -ExtractEmbedded`。
- 根层 JPG 同样展 ISO/光圈/快门/色温/焦距；帧率/码率不显示。
- UI：深色滚动区；视频/照片分组；滚动条仅内容超出时出现。

---

## Canon R50 视频 ISO（2026-08-13）

录像元数据两套数，**差正好 3 档（×8）**，全目录一致：REI/EXIF:ISO `100/200` ↔ BaseISO/Composite:ISO `800/1600`。

| 用途 | 看哪个 |
|---|---|
| **视频颗粒 / 实际增益** | **`BaseISO` 或 `exiftool -ISO`（Composite）** |
| 照片 | 各字段一致，随便看 |
| `RecommendedExposureIndex` / `EXIF:ISO` | R50 **录像不可信**（系统性写低 3 档） |
| `AutoISO` | 内部乘数，几乎总是 100；**不是**「是否自动 ISO」 |
| P 档 + ISO Auto | **不写实际 ISO**（`CameraISO=Auto`、REI=0、无 BaseISO） |

查询：`exiftool -BaseISO -ISO -CanonExposureMode -FNumber -ExposureTime 文件.MP4`

公式（照片准）：`实际 ISO = BaseISO × AutoISO / 100`。R50 视频颗粒跟 BaseISO 走，跟 REI 不走。

---

## 素材库 · 音频试听 / impact（2026-08-14 ~ 08-15）

**WSL 大 WAV 没声**：`_PREVIEW_CLIP_MIN_BYTES`≈33MB。超过则曾走 ffplay/Pulse → Windows 扬声器无声。例：`QP03 0300` 56MB/3:24 没声；旁边 17–20MB 走 SoundPlayer 有声。宫格**红框=双击常驻循环**，不是损坏。

已修：`gui/audio_playback.py` `_launch_wav` — **WSL 一律 SoundPlayer**（24bit 先转 `booms_16bit`）。原生 Linux 大文件仍 ffmpeg→ffplay 管道。

**impact 子 Tab**：声源 = `2_impact/sounds/`（8 条，已 16bit）**追加** `2_impact/booms/`（~125 条 24bit）。试听与 rain/random/wildlife 相同：`parent==booms` → `booms_16bit/`。宫格标题 `sounds/…` · `booms/…`。`resolve_boom_dirs` / `list_boom_wavs`（`gui/audio_library_tab.py`）。`ensure_base_url_dirs` 现为四层都建 `booms/`。

---

## 下一步

1. **AIGC 跑通闭环**：场景 → LLM生成基线 → 预检 → 生成 → 自动 VLM 红框 → LLM替换/合格入池
3. 三系列 `frame_motion` 上界出片后回调
4. **elevenlabs_web** / **elevenlabs_http** 422
5. 即梦额度 scraping（AIGC Tab 已有 `JimengQuotaPanel`，系列顶栏同类）
6. AIGC 金标准 → 固化规范（`aigc/plan.md`）
7. 新增 GUI 重操作时：**默认后台 + `schedule_on_main` 刷新 UI**，勿在主线程 ffprobe/NAS/子进程
8. AIGC **I2V 预览**子模式接线（`AigcPreviewPanel.show_i2v` 已预留）
9. impact `booms/` 可 `python3 -m scripts.audio.booms_16bit` 预热，避免首次悬停转码等待

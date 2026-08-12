# CONTEXT：relaxASMR（压缩）

> 后续会话恢复用。只保留决策、路径、坑与「下一步」；细节以代码为准。

## 产品结构（GUI 顶部 Tab）

| Tab | 内容 |
|---|---|
| 工作流 | 导入 → 音效 → Reaper → 导出 → 上传 |
| 数据分析 | 子 Tab：我的数据 / 爆款分析 |
| 素材库 | 视频 + 各音频库 |
| 系列视频 | 种子图 → 系列图（agy）→ 5s loop 视频（外部 provider） |
| AIGC | 子 Tab：图生视频 / 文生视频 / 旧（Jimeng Agent × Gemini + 原实验台） |

入口：`python -m gui`。`cli/` 经 `ensure_cli_path()` 进 `sys.path`。

---

## 系列视频（当前形态）

### 三个子系列（`instructions/rain_asmr_series.md`）

| id | 系列 | 雨量 | frame_motion |
|---|---|---|---|
| `storm_sleep` | 暴雨助眠 | torrential / heavy | 12–60 |
| `steady_focus` | 中雨专注（默认） | steady moderate | 5–16 |
| `drizzle_meditation` | 轻雨冥想 | light drizzle | 2–7 |

一个批次只属于一个系列，**种子图定稿那一刻锁死**（`BatchMeta.series_id`），系列图和视频全部继承。
系列定义（主体库/光线/雨量措辞/rubric/运动量区间）全在 markdown 里，代码不写死。

### 工作流（每步两道闸门）

1. 选批次 → 选子系列 → 文生/导入**种子图** → Gemini 看图判它属于哪个系列（判不出=reject）→ 定稿锁定
2. **图生图**生成 N 张系列图（主体/光线取自该系列）→ 每张出图后 Gemini 评审是否守住意图
3. **单击**系列图 → **出片前静帧闸**（拦高速摄影静帧，不合格不提交即梦）→ 生成 **video prompt** → 生成视频
4. 视频落盘后**验收**：先 ffmpeg 测运动量（免费，拦慢镜头），过了再让 Gemini 看 4 帧

闸门 = 程序校验（硬，`prompt_rules` / `video_probe`）+ Gemini 评审（硬，agy 失败即停；产物不合格只标记）。

生图走 agy；生视频**不走 Gemini**（无视频模型）。

### Gemini 调用（硬规则）

**凡是 Gemini，统一走 agy**（`cli/agy/` → `generate_text_via_agy_accounts` / `generate_image_via_agy_accounts`）。

| 要 | 不要 |
|---|---|
| `agy/credentials.json` 三账号轮换（429/403/配额 → 本进程标记耗尽换下一账号） | `GEMINI_*` env key 直连（`shared/gemini_client` 仅历史兼容，**新代码禁止**） |
| 裸 `gemini-3.6-flash` 无后缀时按场景选 effort（VLM 审图常用 medium） | 为「兜底」再写一套 google-genai / env key 路径 |
| agy 全失败 → 明确报错或降级模板（如 prompt 自愈） | 静默回退到非 agy 通道 |

系列视频评审（`scripts/series_video/review.py`）、AIGC VLM（`scripts/aigc_lab/agent_loop.py`）、AIGC 实验台 VLM（`gemini-3.6-flash` via agy）均遵守此条。

### 目录与命名（仓库内 ``aigc/<批次>/``）

| 路径 | 说明 |
|---|---|
| `seed_image/seed_001.*` | 定稿种子（`batch.json` 里带 `series_id`） |
| `seed_image/seed_001_raw_001.*` | 文生待选候选 |
| `series_image/series_001.*` | 系列图 |
| `series_video/series_001.mp4` | 对应 5s 视频 |
| `batch.json` | 系列图条目（事实来源） |
| `seed.json` | 种子 prompt 元数据 |
| `video_series_001.json` | 各系列图 video prompt |

仅读取/写入仓库内 ``aigc/``；外盘旧路径不再扫描。

逻辑：`scripts/series_video/`

| 模块 | 职责 |
|---|---|
| `series` | 读 `rain_asmr_series.md`，三系列定义的唯一来源 |
| `prompt_rules` | 机器校验；**基础规则 ⊕ 系列覆盖层**（`with_overlay`） |
| `prompts` | 按系列派生图/视频提示词 |
| `review` | Gemini 评审：种子图分类 / prompt / 图 / 视频抽帧 |
| `video_probe` | 客观测量：ffmpeg 抽帧 + 运动量（不认识业务对象） |
| `acceptance` | 编排 probe + review，结论写回 `BatchMeta` |
| `store` / `image_gen` / `video_prompt_gen` / `video_gen` | 数据 / 出图 / 出词 / 出片 |

实测批次：`20260803_115200`；`series_001.mp4` 已由 jimeng_web 落盘（1280×720 / ~5s）。

### GUI（`gui/series_video_tab.py`）

- 顶栏：生图额度 | 生视频额度 | 操作区
- 左三列：① 种子 ② 系列图 ③ 视频；②③ 滚动联动
- 系列图单选后生成视频；第三列生成中显示 **`N% 造梦中`**（读即梦页进度）
- 登录按钮：即梦 / ElevenLabs 网页；HTTP token 走 `elevenlabs_http login`
- 错误分离：`image_error` / `video_error`

### 提示词与 loop

- 规范：`instructions/rain_asmr_*.md`；发模型前 `prompt_rules.py` 校验
- **Loop = prompt 软约束 + 即梦「首尾帧」硬约束**（同图作首+尾）；prompt 含 `Loop seamlessly`、固定镜头、周期雨滴
- 档位：即梦 720p/5s；EL 480p/5s
- **自然速度（踩过的坑）**：不写速度 → Seedance 默认出慢镜头。规则 `rain_asmr_video_v2`
  新增三条必填维度：实时速度（`real-time` / `natural gravity`）、雨的强度（**按系列**）、
  雨丝拖影（`motion-blurred streaks`）；`slow` / `slowly` / `dreamy` / `frozen` 变禁词，
  Constraints 段须含 `avoid slow motion`
- **高速静帧 → 慢镜头（更大的坑）**：Gemini 爱出 `crisp frozen droplets` / 定格水冠；
  同图作即梦首尾帧几乎必慢放。图侧 `rain_asmr_image_v2` 改为表面挂珠+轻雾并禁
  frozen/high-speed；系列图评审 + `gate_still_for_video` 出片前硬拦
- prompt 自愈：存过的 video prompt 每次都按当前规则复校，不合规就重新生成；
  Gemini 三稿不过退回 `build_video_prompt()` 模板

### 运动量标定（真实素材实测，别乱改 `_MOTION_SCALE=5.0`）

无雨空镜 0.5–1.3 ｜ 轻雨 2.7–5.1 ｜ 小雨 4.8–9.1 ｜ 中雨 8–12 ｜ 大雨 16.8–19.1

对照：2026-08-03 那条**慢镜头** AI 视频 = **3.83**（中雨场景却只有轻雨的运动量）。
两个已知限制：分数受主体占画面比例影响，只做粗筛；细雨系列的慢镜头和真实细雨重叠，
这层拦不住，得靠 Gemini 看抽帧里雨滴**有没有拖影**。

### 规范自洽（踩过的坑）

`review_rubric` 和 `time_variants` 是同一套意图的两种写法，写歪了会「按规范生成的图被规范
自己判死」。首次接通评审就撞上：`steady_focus` 的光线候选有 `golden hour warm rim light`，
rubric 却要求「阴天柔和均匀光」。**改候选词库和 rubric 必须一起改。**

### Provider 回退（`video_gen.py`，写死）

1. **`jimeng_web`** — 即梦 Playwright · **已通** · VIP / 首尾帧 / 16:9 720P / 5s
2. `elevenlabs_http` — Firebase Bearer HTTP · 480p/5s（上传会话曾 422）
3. `elevenlabs_web` — EL 页 Playwright · 480p/5s（选择器未联调通）

`SERIES_VIDEO_EXTRA_PROVIDERS=1` 才注册 Ark / ffmpeg。视频写 `.part` 再 `os.replace`。

---

## jimeng_web（本会话已打通）

| 项 | 值 |
|---|---|
| 入口 | `home?type=video`（非旧 assets-canvas） |
| 模型 | `Seedance 2.0 Fast VIP`（AIGC 默认；`JIMENG_VIDEO_MODEL` 可改；系列仍 VIP+首尾帧） |
| 参考 | 默认 **首尾帧**（同图×2）；`JIMENG_REF_MODE` 可改全能参考 |
| 画幅/时长 | 16:9 720P · **5s**（时长面板数字框 + Enter） |
| 登录判定 | 侧栏无「登录」；`status` 勿信正文模糊匹配 |
| 进度 | 读结果卡「`N%造梦中`」→ AIGC：**生成按钮** `造梦进度：N%`；系列视频：第三列 |
| 落盘 | `<video>` 直链 / **blob:** / 下载图标；校验 ffprobe 或体积极下限；**检测到新结果时日志打印全部 video 链接** |
| 已有结果 | 提交前若页面已有同 prompt +「再次生成」→ **直接下载，跳过提交** |
| 手动入库 | ``attach_run_video(run_id, mp4)`` → ``runs/<id>/video.mp4`` |
| 落盘 | 忽略历史 `<video>` → 等新片 → `context.request` 直链 |
| Profile | `cli/jimeng_web/.profile/` + **`.profile.lock`**（防额度面板抢 Chromium） |
| 共享基座 | 仓库根 `shared/browser.py`（**勿**再放 `cli/shared/`，与根 `shared` 撞名） |

```bash
PYTHONPATH=cli:. python -m jimeng_web login
PYTHONPATH=cli:. python -m jimeng_web generate \
  --image …/series_001.jpg --prompt "…" --out …/series_video/series_001.mp4 --duration 5
```

生成中勿点额度面板 Jimeng 刷新。失败截图：`cli/jimeng_web/debug/`。

**文生（AIGC Tab）**：`generate_t2v(prompt, …)` · 默认 **5s**（顶栏 Spinbox 1–15 + **生成数量** 1–10，写 `params.json`）/ 16:9 / 720p / **Seedance 2.0 Fast VIP**（无参考图）。

```bash
PYTHONPATH=cli:. python -m jimeng_web generate-t2v --prompt "…" --out …/runs/xxx/video.mp4
```

---

## AIGC 文生视频实验台（2026-08-06 ~ 08-07）

**产品**：油管纯自然雨 ASMR · 场景默认**原始热带雨林**（GUI 可扩展） · 雨势 **暴雨 > 大雨 > 小/中雨**。  
**方法**：`aigc/plan.md` — 原子断言 → 测评 → 消融 → 固化。

### AIGC 三子 Tab（2026-08-07 ~ 08-08）

左侧 Notebook 仅一个父 Tab **AIGC**；内部：图生 / 文生 / 旧。

| 子 Tab | 说明 |
|---|---|
| **图生视频** | 参考图 → Jimeng 六槽 → Gemini VLM **只审 Jimeng**（≤3 轮修订）→ **仅 agreed 可生成** → 全能参考成片；油管黑马评分代码保留、默认关 |
| **文生视频** | 场景+雨型 → Jimeng 草稿 × Gemini 审（≤3 轮） |
| **旧** | `gui/aigc_tab.py` · `aigc/t2v_lab/` |

**图生协议（现行）**：
- 事实源：[`rain_asmr_agent_i2v.md`](instructions/rain_asmr_agent_i2v.md) 文末 `<!-- agent:rules -->` **压缩块**（~800 字）
- **Jimeng**：技能「雨ASMR图生」（[`jimeng_skills/雨ASMR图生.md`](instructions/jimeng_skills/雨ASMR图生.md)）承载规则；自动化「使用技能→搜索/新建→**去使用**」；对话只发短指令（~180 字），禁止整段粘规则
- **Gemini**：审核 system 注入同一压缩块；疑问可问 Jimeng 并写入 [`aigc/Seedance2.0手册.md`](aigc/Seedance2.0手册.md)
- **会话**：`JimengAgentSession` 整段审核复用同一浏览器页（不每轮开关）；发送后确认清空+等新回复（baseline/心跳）
- **雨档**：按图；无雨默认 `heavy`；GUI 不覆盖。映射 `storm→助眠` / `heavy→专注` / `light_mod→冥想`
- **公式**：保留（图）+ 调整（字）；camera 正向构图；action 前景雨+周期往复；禁靠 constraints 写 loop
- **顶栏**：模型 Fast VIP（默认）/ 2.0 VIP / 2.5 · 固定 16:9 · 720p/1080p（Fast 仅 720）· 5s · 生成数量 · 额度条 · 登录即梦；写 `agent_i2v_lab/params.json`
- **GUI 会话**：`gui_session.json` 存最后编辑六槽/审核态；重启**不**自动选中实验记录（点列表才灌该 run 标签）；额度在顶栏
- 与系列视频首尾帧规范（`rain_asmr_video_prompt.md`）分开

| 路径 | 说明 |
|---|---|
| `gui/aigc_shell.py` · `agent_lab_base.py` · `agent_*_tab.py` | 父壳 + 图/文生 UI |
| `gui/agent_atoms_ui.py` | 六槽芯片（增删/标红） |
| `cli/jimeng_web/agentic.py` | Agent 页 · Session · 技能挂载 · 短对话 |
| `scripts/aigc_lab/agent_loop.py` | Jimeng→Gemini 审；共用 Session |
| `scripts/aigc_lab/agent_i2v_rules.py` | 压缩规则 + 技能三字段 |
| `scripts/aigc_lab/agent_store.py` | runs / `I2V_JIMENG_PARAMS` / 模型分辨率门控 |
| `scripts/aigc_lab/youtube_*.py` | 爆款池·基准·黑马分（默认不自动跑） |

落盘：`meta.json` · `prompt.txt` · `review.json` · `video.mp4`（可选 `viral_score.json`）。Agent 与造梦共 Jimeng profile 锁。

| 路径 | 说明 |
|---|---|
| `scripts/aigc_lab/` | `prompt_atoms.py` · `store.py` · `score.py` · `tag_pools.py` · `session.py` |
| `aigc/t2v_lab/` | `params.json` · `gui_session.json` · `learned_pools.json` · `scene_pool.json` · `runs/`（**仅「旧」子 Tab**） |
| `gui/aigc_tab.py` | 「旧」：场景总约束 · 六槽原子表 · 实验记录 · VLM/LLM · 标签拖拽 |
| `gui/aigc_preview_panel.py` | AIGC 专用右侧预览（与工作流封面/视频预览**完全隔离**） |
| `gui/video_quota_panel.py` | `JimengQuotaPanel`（AIGC 实验台下即梦额度条） |
| `gui/audio_playback.py` | `start_media_audio_loop`（OpenCV 无声 → ffplay 循环音频） |

### 顶栏实验台

- 模型 / 画幅 / 720p / 时长 **1–15s** / **生成数量 1–10**（原「重复 N 次」已移至此，写 `params.json` `generate_count`）
- 默认模型 **Seedance 2.0 Fast VIP**
- 实验台下 **即梦额度**（`dreamina user_credit` / 6160）；切到 AIGC Tab 时刷新；生成中勿抢 profile

### 右侧预览（与工作流独立）

- `gui/app.py`：`_right_panel_mode` 分 **default / aigc**；各自 sash 独立保存恢复
- AIGC 用 `AigcPreviewPanel`（非工作流 cover + video 双栏）：**T2V** 上视频下 prompt 表；**I2V** 上视频、左图右槽 prompt（`kind=` 文生/图生子 Tab 已用）
- 视频循环播放时同步 **ffplay** 音频 loop

### 布局与按钮（「旧」子 Tab）

- **场景**（表外 LabelFrame）：总约束，指导 LLM 基线/替换，**不进送模**；标签 + 池选/`+`；**拖动改序**；`scene_pool.json`
- **Prompt 原子表**：六槽标签芯片（×删；**拖动改序**；槽位标签短按标可疑红框；行末池选/`+`）；送模=各槽逗号拼接
- **LLM生成基线**：按场景+雨档调 agy 生成开放三槽；闭集槽固定（见下）
- **LLM替换可疑标签**：只替换红框项；**保真压缩**（信息不丢的最短电报式，如「中景排列着五株…」→「中景五株交错野芭蕉树」）
- **VLM标记可疑标签**：L1 **主体/环境** + L2 **动作**（`gemini-3.6-flash` via agy）；**镜头/风格/约束不参与 VLM**；只红框，不弹窗、不入池
- **合格标签入池**：**唯一入池入口**（排除红框 → 人工确认）；`learned_pools.json`
- **生成视频**：提交前 **LLM 预检**（见下）→ 落 `runs/<run_id>/` → 自动选中 → 自动 VLM 红框
- 左侧 **Canvas 垂直滚动**（滚动条常显，防宽度抖动递归）

### 生成前 LLM 预检（`check_tag_conflicts`）

- 检查六槽：**互相矛盾**（标红）+ **重复描述**（只提示）
- 弹窗：**继续造梦 / 返回修改**；继续用 `skip_preflight=True` + 预检快照提交
- 冲突标签保留已有红框；重复不标红

### 实验记录 vs session（已确认，勿改语义）

| 来源 | 存什么 |
|---|---|
| **run**（实验记录） | 点「生成视频」瞬间的 `slots` + 之后 VLM 的 `scores`（红框依据） |
| **session**（`gui_session.json`） | 当前界面人工编辑（标签/红框/雨档/选中 run）；**重启 GUI 恢复** |

点**另一条**实验记录 → `_apply_run_slots` + `_apply_score_fails_from_run`，覆盖人工编辑。  
**同一条**已选中再点 → early return（防闪烁）；要强制回到生成快照 → 切别的再切回。  
启动 `load_session(..., load_slots=False)` 只恢复编辑态，不覆盖 run 快照逻辑。

### 标签拖拽换序（`gui/aigc_tab.py`）

- 场景 + 六槽均支持；阈值 **~6px** 区分短按（槽位标红）与拖动
- 拖动中：**半透明幽灵**（蓝框 `#1976d2`）跟鼠标；原标签也蓝框
- **松手才 `_reorder_tags` + reflow**（拖动中实时 reflow 会导致全表闪烁）
- 幽灵存 **`self._tag_drag_ghost`**（勿绑在 `_tag_drag` dict 上，否则 `_end_tag_drag` 清 dict 后泄漏 → 蓝框停在外围）

### 六槽规则

| 槽 | 规则 |
|---|---|
| 场景 | GUI only，不进送模 |
| 主体/动作/环境 | 开放；LLM 只写这三槽 |
| 镜头/风格/约束 | 闭集；LLM 基线固定：`固定镜头+平视` · `documentary+moody+desaturated+overcast`+雨档 ASMR · 核心+常选约束 |

**语义原子化**（LLM 基线/替换强制；`prompt_atoms._atomic_open_atoms` 兜底）：  
- **subject**：一项=一个可见对象；禁「A与B/和/、」并列；禁「高大/巨大」等不可核验形容词  
- **action/environment**：一项=一个语义断言；顿号/逗号可补同一结果/条件  
- **保真压缩**：删「排列着/分布的/正在/画面中」等填充，不丢数量/空间关系/动作  
- 默认 subject 示例：`香蕉树` `宽大蕉叶` `热带乔木` `浓密灌木` `粗壮树干` `湿润地面`

闭集池见 `atom_pools.md`；预览/生成**不钳制**，以当前标签表为准。

### 无限 loop 视频建议（产品 Q&A）

- **动作槽**：叶片/灌木**小幅往复摆动**、雨水沿树干流淌、暴雨连续、地面积水溅起；**树干本身不摆**
- **首尾帧**：T2V 无首尾帧；I2V 同图首尾易慢镜头；实用路径 = 5s 文生 + 后期 loop/交叉淡化
- **时长**：优先 **5s**（4s 循环感强，8–10s 首尾难闭合）

### 工作流

1. 设场景 → **LLM生成基线**（或手调标签）→ 预览送模正文 → **生成视频**（预检可弹窗）
2. 完成后自动：**选中最新实验记录** → 刷新预览/详情 → **自动 VLM 红框**
3. 可疑 → **LLM替换可疑标签**；满意 → **合格标签入池**
4. 雨档切换：只同步闭集槽（如 ASMR 音频句），开放三槽不动

### GUI 踩坑

| 项 | 要点 |
|---|---|
| 实验记录点击 | 须点中**行条目**才加载；空白/重复点同条不刷新 |
| 红框恢复 | `_preload_fail_marks` **先于** `_write_slots`，否则重启全灰 |
| 滚动 | 滚动条勿 `grid_remove`（会触 reflow→Configure 递归）；`_reflow_tags` 勿尾递归 |
| 会话 | `gui_session.json`：场景 + 六槽 + fail_tags + selected_run_id；debounce 300ms |
| 预览区耦合 | AIGC 勿复用工作流 cover/video pane；用 `AigcPreviewPanel` + 分 mode sash |
| 标签拖动 | 拖动中勿 reflow；幽灵窗口独立字段，松手 destroy |
| VLM 槽位 | `_L1_SLOTS=subject,environment` · `_L2_SLOTS=action`；`failed_tags_from_scores` 忽略 locked 槽 |

生成/评分/即梦登录走 `_run_bg`；顶栏时长 + 生成数量写 `params.json`。

---

## 架构决策（累计）

| 变更 | 原因 |
|---|---|
| 删 `cli/dreamina/` | 官方 CLI 体验差 |
| GUI 重 I/O 放后台 | 启动卡死、步骤 4 ffprobe/NAS 阻塞主线程 |
| `find_export_wav_for_scene` | legacy `_3h.wav` 与 `_180min.wav` 双格式 |
| GUI 合成 `--no-video-fade-in` | 去掉成片视频片头 5s 淡入 |
| AIGC 红框恢复顺序 | 先 fail_tags 内存再建 widget；`_sync_fail_borders` |
| AIGC 滚动条显隐 | 勿 `grid_remove` 滚动条（宽度抖动→Configure 递归）；滚动条常显 |
| AIGC `_reflow_tags` | 函数末尾勿误调自身（曾致 RecursionError） |
| AIGC 预览隔离 | 独立 `AigcPreviewPanel` + 分 mode sash；勿与工作流 cover/video 共用 |
| AIGC 标签拖动 | 拖动中勿 reflow（全表闪）；幽灵 `Toplevel` 用 `_tag_drag_ghost` 独立销毁 |
| AIGC VLM 槽位 | 只验 subject/environment/action；camera/style/constraints 固定项不入 VLM |
| AIGC 生成前预检 | `check_tag_conflicts`：矛盾标红 + 重复提示；用户可选继续造梦 |
| AIGC 默认模型 | Fast VIP（`params.json` / `client.py` `DEFAULT_VIDEO_MODEL`） |
| 图生 Agent 会话 | `JimengAgentSession` 复用同页；禁每轮开关浏览器 |
| 图生规则投递 | Jimeng 用技能+短指令；Gemini 注入压缩块；禁整段粘规则 |
| 图生技能启用 | 新建/选用后必须点「去使用」才挂到对话 |
| 图生 GUI 恢复 | 恢复最后编辑六槽；勿自动选中 run 覆盖标签 |
| 图生生成门控 | 仅 Gemini `agreed` 可点「生成视频」 |
| `elevenlabs_web`→`elevenlabs_http`；新建 Playwright 双包 | HTTP 挂时 UI 兜底 |
| `shared/browser.py` 在仓库根 | cwd 优先会盖掉 `cli/shared` |
| jimeng 默认 VIP+首尾帧+5s | loop 硬约束 + 产品档位 |
| profile 文件锁 | `available()`/额度轮询与 generate 抢同一 profile 会关浏览器 |

EL Web：`https://elevenlabs.io/app/image-video?modality=video`  
Profile：`cli/elevenlabs_web/.profile/`（与 http 独立）

---

## 包路径

| 包 | 位置 | 说明 |
|---|---|---|
| `agy` | `cli/agy/` | 出图 |
| `jimeng_web` | `cli/jimeng_web/` | 即梦 Playwright（主通道） |
| `elevenlabs_http` | `cli/elevenlabs_http/` | HTTP+token；**勿名 `elevenlabs`** |
| `elevenlabs_web` | `cli/elevenlabs_web/` | EL 页 Playwright |
| `shared.*` | 仓库根 `shared/` | browser 基座 + llm_log |

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
| 默认 | **100** 分钟 |
| 配置键 | `duration_minutes`（`gui/user_config.json`）；保存时删旧 `duration_hours` |
| 兼容读取 | `duration_hours` / 旧 `target_duration`（小时字符串）→ UI 显示分钟 |
| 导出后缀 | `100min`（非旧 `3h`），如 `MVI_1002_100min.wav` / `_100min_fhd.mp4` |
| 核心 API | `scripts/config/paths.py`：`cfg_duration_minutes()`、`duration_render_suffix(minutes)` |
| 校验 | `gui/export_wav.py`：`wav_matches_target_minutes()`（±30s） |

**涉及模块**：`gui/app.py` · `gui/reaper_launch.py` · `Reaper/scripts/{generate_subproject,rain_subproject_lib,create_rain_subproject,asmr_config_parser}.py` · `asmr_loop_track.lua`（默认 100）

**坑**
- 旧 `_3h` 成品与新 `_100min` 命名不互通；仍用 3h 成片请在 GUI 填 **180** 分钟
- **WAV 混音**曾只认 `{scene}_180min.wav`，不认 legacy `{scene}_3h.wav` → 步骤 4 显示「待开始」；已修：`find_export_wav_for_scene()`（与 MP4 对称）
- 场景 JSON 字段：`duration_minutes`（旧 JSON 含 `duration_hours` 时 `cfg_duration_minutes` 仍可读）
- `gui/youtube_material.py` 打分：保留 `_3h`，另认 stem 含 `min`
- **合成视频片头 fade-in**：GUI 主流程已传 `--no-video-fade-in`（`export_mp4.sh` 默认仍 5s）；Reaper Group 音频 fade 不受影响

**测试**：`scripts/tests/test_export_wav.py` · `test_tag_pools.py` · `test_rpp_render_range.py` · `test_build_scene_config_from_gui.py`

---

## GUI · 线程原则（2026-08-06，硬规则）

**除刷新界面外，其它操作一律放后台**；主线程只做 Tk 控件读写与布局。

| 允许主线程 | 必须后台（`threading` + `schedule_on_main` 回写 UI） |
|---|---|
| 建控件、改 Label/Button 状态、布局 sash | NAS/`ffprobe`、路径 `is_file` 批量探测 |
| `_repaint_tag_borders` / 就地改边框色 | 工作流恢复、步骤 4 混音/成片存在性校验 |
| 用户点击后的即时视觉反馈（无 I/O） | 音库选中恢复、`_finish_set_video_heavy` 分析缓存读取 |
| | 即梦/EL 登录与生成、L1+L2 评分、export_mp4/render |

**启动（曾卡死 ~30s）**：窗口 `_reveal_when_layout_ready` **同步先显现**；`_restore_workflow_state` / `_restore_audio_library_selections` 改 `after(50)`；`_refresh_step4_outputs(..., background=True)` 与 `_apply_finish_set_video_heavy` 探测在子线程。

**模块**：`gui/tk_thread.py`（`schedule_on_main` / `ensure_ui_pump`）· `gui/app.py` · `gui/aigc_tab.py`

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
- `gui/aigc_tab.py`：详情区 `setup_copyable_readonly_text`（Prompt 为六槽标签芯片，非大 Text）
- `gui/aigc_preview_panel.py`：预览区视频 + `gui/audio_playback.py` ffplay 循环音

**新增 Text 控件时**：可编辑走 `setup_editable_text_copy`；只读走 `setup_copyable_readonly_text`，程序写内容直接 `delete`/`insert`，不要 toggling `DISABLED`。

---

## GUI · 输入法

- 已删 `gui/ime_bootstrap.py` 及 `ui_theme.make_ime_entry` / `style_ime_entry`；系列视频灵感词等用默认 `ttk.Entry`
- 启动日志**无** WSL 输入法提示；走系统默认 IME

---

## 其他 Tab

- 数据分析：YouTube API + agy；黑马 `views_per_day`；WSL 开 URL 用 Chrome profile
- agy 换号失败：额度/模型容量；`[WARN]` 后有 API 详情

---

## 本次对话新增（raw 视频 Tab，GUI）
- `raw 视频` 宫格新增字段：**码率**（ffprobe `format.bit_rate`）、**ISO 小数取整**（四舍五入成整数）。
- 交互：目录选择后立即刷新路径与**`共 N 个`**；宫格**单击**做封面放大预览 + 右侧显示：标题、分辨率、帧率、码率、ISO、光圈、快门、色温、焦距；双击不再触发任何动作。
- 性能：对 raw 元数据加**磁盘+内存缓存**（`material_dir/.raw_video_meta/*.json`），避免每次 ffprobe/exiftool 实时解析；首次会先渲染占位再逐步填充（封面后参数）。
- Sony a7m4 坑点：XAVC 的拍摄参数在 `rtmd` 嵌入轨，需 `exiftool -ExtractEmbedded`；并通过 rtmd 额外扫描补齐（焦距/色温）等缺失项。
- 扩展：宫格支持根层 **JPG/JPEG**，同样解析 EXIF 并展示 `ISO/光圈/快门/色温/焦距`，帧率/码率不显示。
- UI 修复：raw 子 Tab
  - 深色模式下滚动区/背景适配；
  - 宫格按 **视频/照片 分组**显示；
  - 滚动条仅在内容超出视口时出现（避免“复用 loop 视频”的假滚动/常显滚动条）。

---

## 下一步

1. **AIGC 跑通闭环**：场景 → LLM生成基线 → 预检 → 生成 → 自动 VLM 红框 → LLM替换/合格入池
2. **跑通一整批**（系列视频）：暴雨助眠 → 系列图 → 视频验收
3. 三系列 `frame_motion` 上界出片后回调
4. **elevenlabs_web** / **elevenlabs_http** 422
5. 即梦额度 scraping（AIGC Tab 已有 `JimengQuotaPanel`，系列顶栏同类）
6. AIGC 金标准 → 固化规范（`aigc/plan.md`）
7. 新增 GUI 重操作时：**默认后台 + `schedule_on_main` 刷新 UI**，勿在主线程 ffprobe/NAS/子进程
8. AIGC **I2V 预览**子模式接线（`AigcPreviewPanel.show_i2v` 已预留）

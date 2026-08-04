# CONTEXT：relaxASMR（压缩）

> 后续会话恢复用。只保留决策、路径、坑与「下一步」；细节以代码为准。

## 产品结构（GUI 顶部 Tab）

| Tab | 内容 |
|---|---|
| 工作流 | 导入 → 音效 → Reaper → 导出 → 上传 |
| 数据分析 | 子 Tab：我的数据 / 爆款分析 |
| 素材库 | 视频 + 各音频库 |
| 系列视频 | 种子图 → 系列图（agy）→ 5s loop 视频（外部 provider） |

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
| 模型 | `Seedance 2.0 VIP`（排除 mini / Fast VIP / 2.5） |
| 参考 | 默认 **首尾帧**（同图×2）；`JIMENG_REF_MODE` 可改全能参考 |
| 画幅/时长 | 16:9 720P · **5s**（时长面板数字框 + Enter） |
| 登录判定 | 侧栏无「登录」；`status` 勿信正文模糊匹配 |
| 进度 | 读结果卡「`N%造梦中`」→ 日志 + GUI 第三列 |
| 落盘 | 忽略历史 `<video>` → 等新片 → `context.request` 直链 |
| Profile | `cli/jimeng_web/.profile/` + **`.profile.lock`**（防额度面板抢 Chromium） |
| 共享基座 | 仓库根 `shared/browser.py`（**勿**再放 `cli/shared/`，与根 `shared` 撞名） |

```bash
PYTHONPATH=cli:. python -m jimeng_web login
PYTHONPATH=cli:. python -m jimeng_web generate \
  --image …/series_001.jpg --prompt "…" --out …/series_video/series_001.mp4 --duration 5
```

生成中勿点额度面板 Jimeng 刷新。失败截图：`cli/jimeng_web/debug/`。

---

## 架构决策（累计）

| 变更 | 原因 |
|---|---|
| 删 `cli/dreamina/` | 官方 CLI 体验差 |
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

## 其他 Tab

- 数据分析：YouTube API + agy；黑马 `views_per_day`；WSL 开 URL 用 Chrome profile
- agy 换号失败：额度/模型容量；`[WARN]` 后有 API 详情

---

## 下一步

1. **跑通一整批**：选暴雨助眠 → 出候选 → 看分类准不准 → 定稿 → 出系列图 → 出视频看验收拦不拦得住
2. 三系列的 `frame_motion` 上界（60/16/7）只有下界是实测的，出片后按实际分布回调
3. **elevenlabs_web** 有头联调：upload → generate → download（固化选择器）
4. **elevenlabs_http** 修上传会话 422；captcha 时更新 `hcaptcha_token.md`
5. 即梦额度 scraping（可选）补进额度面板
6. GUI：生成完成后自动刷新批次预览（若仍显旧失败态，重载批次即可）

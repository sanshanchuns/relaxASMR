# 雨 + ASMR 图生视频 · 提示词最佳实践

适用范围：`系列视频` Tab 里「系列图 → 5s 固定镜头 loop」这一步，默认走 **Jimeng 网页 · 720p**；回退 ElevenLabs HTTP / Web（480p）。

本文件是**生成前的强制参考**：`scripts/series_video/prompt_rules.py` 会在运行时读取本文末尾的
校验规则块，任何一条不通过就拒绝提交任务（视频一次调用就要花钱，提交前必须先拦住）。

依据：Seedance 2.0 官方提示词指南
（[6 步公式 + 8 类镜头运动 + 避坑清单](https://help.apiyi.com/seedance-2-0-prompt-guide-video-generation-camera-style-tips.html)）。

---

## 一、6 步公式：主体 → 动作 → 环境 → 镜头 → 风格 → 约束

官方标准结构是 `[主体], [动作], in [环境], camera [镜头], style [风格], avoid [约束]`，
推荐长度 **60–100 词**。本项目把它写成六个带标签的槽位，方便逐项覆写和校验：

```
Animate the provided image. Subject: <主体>.
Motion: <播放速度> + <雨的强度> + <撞击事件>.
Environment: <环境>.
Camera: <镜头>.
Style: <风格>.
Loop seamlessly: last frame matches the first.
Constraints: <约束>.
```

| 步 | 槽位 | 本项目的填法 | 为什么 |
| --- | --- | --- | --- |
| 1 | 主体 | 直接复用这张系列图的 subject 段，或留空让模型看图 | 图生视频不需要重描外观，图里已经有了 |
| 2 | 动作 | **先写速度和雨量，再写撞击事件**；只有雨和水在动，主体留在原地 | 不写速度就是慢镜头（见第三节）；主体一动 loop 就废了 |
| 3 | 环境 | `unchanged from the provided image` | 强调 preserve，防止模型自己改景 |
| 4 | 镜头 | `locked-off tripod, fixed framing, no pan no zoom` | 官方 8 类镜头里的「固定（fixed / locked-off）」 |
| 5 | 风格 | `cinematic macro realism, cool desaturated film tone, real-time motion` | `cinematic` 单用是官方点名的危险词，必须带限定 |
| 6 | 约束 | 至少排除：**慢镜头**、镜头运动、抖动、时间闪烁、形变、转场、人、字幕 | 官方「必加负面提示词」清单 + 本项目的慢镜头补充 |

---

## 二、图生视频 ≠ 文生视频

官方明确区分了两者。本项目全部是图生视频，所以：

- **不要重复描述主体外观**。图里有的东西再写一遍，只会和图打架。
- **重点写运动和变化**，这是提示词唯一真正起作用的部分。
- **必须强调保持构图和色彩**（`preserve composition and colors` / `unchanged from the provided image`），
  否则模型会把画面重新构一遍。
- **镜头运动要和图的构图一致**。本项目固定镜头，天然一致。
- **首帧若是高速摄影静帧，视频几乎必出慢镜头**。图侧规范已改成「表面挂珠 + 轻雾」、
  禁 `frozen` / 定格水冠；出片前还有一道看图闸。即便如此，Motion 段仍必须正面写
  实时速度 + 雨丝拖影——文字要压住首帧里残余的高速线索。

---

## 三、自然速度：别让它出慢镜头

**这是本项目踩过的最大的坑。** 不写播放速度，Seedance 对「雨 + 微距 + cinematic」的默认理解
就是高速摄影慢放——因为训练集里这类素材几乎全是慢镜头。光靠「不要慢镜头」这一句负面提示不够，
必须**正面写出实时速度**，再用负面提示补刀。

三件事一起做，缺一个都会漂回慢动作：

1. **正面锚定速度**：Motion 段开头就写 `at real-time speed`（或 `real-time playback`、
   `natural gravity`）。这是必填维度。
2. **写出雨的强度**：`heavy rain` / `steady downpour` / `light drizzle` 任选，但**必须写**。
   不写强度，模型只给几滴稀疏的水珠慢慢飘，看着就是慢放。要大雨就写
   `heavy rain pours continuously`。
3. **给出实时快门的视觉证据**：真实速度下的雨滴是**带拖影的雨丝**，不是悬停的小球。
   写 `raindrops leave short motion-blurred streaks` / `rain streaks fall through the frame`。
   这一条比前两条更有效——它描述的是画面证据，模型照着画就必然是实时速度。

对应的负面提示（写进 Constraints 段）：

```
avoid slow motion, high-speed camera look, frozen droplets, time-lapse, speed ramp
```

注意 `fast` 仍然是禁词（官方点名，会引起抖动）。想表达「正常速度」永远用
`real-time` / `natural gravity`，不要用 `fast` / `rapid` / `quick`。
同理 `slow` / `slowly` / `dreamy` 现在也是禁词——它们就是慢镜头的开关。

---

## 四、把「ASMR 感」写进 Motion 段

ASMR 的听感来自画面上能看见的**离散撞击事件**。Motion 段要写出这些事件，而不是笼统的「下雨」：

- 雨点持续以稳定节奏打上去：`rain keeps striking it in a continuous rhythm`
- 水珠炸开成小水冠：`droplets burst into small splash crowns`
- 涟漪扩散再消失：`ripples spread and fade`
- 细雾飘动：`fine mist drifts`
- 主体保持原位：`the subject stays in place`

注意用**节奏词**（steady / continuous / rhythmic）而不是摄影参数，官方指南说得很清楚：
模型理解人类节奏感，不理解 `f/2.8`、`ISO 800`。但**节奏词不等于速度词**：`steady` 说的是
「节拍均匀」，`real-time` 说的是「不快放不慢放」，两个都要写。

Seedance 2.0 会同时生成音频。本项目要的就是雨声，所以保持 `generate_audio` 打开时，Motion 段里
这些撞击描述同时也在指挥声音，不需要另写一段音频提示。实时速度还有个附带好处：慢镜头的雨声
会被拉成沉闷的低频，实时速度才有清脆的打击颗粒。

---

## 五、做 loop 的额外纪律

官方公式里没有 loop，这是本项目自己加的第七件事：

1. **首尾对齐**：`Loop seamlessly: last frame matches the first.`
2. **只允许周期性运动**。雨、涟漪、雾都是周期性的；叶子被压弯、水位上涨这类**单向变化**不能要。
3. **不要出现会「用完」的东西**：比如一滴水从叶尖滑落到地面，滑完了就接不回去。
4. **时长压到 5s**。越长越容易漂移，也越贵。

实时速度反而让 loop 更好接：雨越密、周期越短，5s 里就跑完了足够多个周期，首尾差异被平均掉。

---

## 六、避坑（官方清单 + 本项目补充）

| 别写 | 后果 | 改成 |
| --- | --- | --- |
| 不写速度 | **默认慢镜头**，本项目踩过的最大的坑 | `at real-time speed` + 雨的强度 + 雨丝拖影 |
| `slow` / `slowly` / `dreamy` | 直接触发慢动作 | `steady` / `continuous` / `rhythmic` |
| `fast` | 官方点名的头号危险词，必然抖 | `real-time` / `natural gravity` |
| `frozen droplets`（写进视频） | 悬停的水珠 = 高速摄影 = 慢放 | `motion-blurred streaks` |
| `cinematic` 单用 | 太模糊，没有指导性 | `cinematic macro realism, cool desaturated film tone` |
| `epic` / `amazing` / `beautiful` | 形容词无指导力 | 删掉，换具体描述 |
| `camera push-in, then pan left` | 多个镜头指令 = 抖动和不连贯 | 只写一个：`locked-off, fixed framing` |
| `spinning camera around the leaf` | 镜头运动和主体运动混写 | 拆成两句：主体怎么动、镜头怎么拍 |
| `lots of movement` | 运动过多导致抖 | 只写具体的那几个水的动作 |
| 忘记负面提示 | 十有八九出抖动或转场 | `Constraints:` 段是必填项 |
| 提示词超过 120 词 | 指令互相矛盾，质量下降 | 砍掉重复形容词 |

---

## 七、发布前自检清单

- [ ] 六个槽位齐了吗
- [ ] 词数在 60–120 之间吗
- [ ] **Motion 段开头写了实时速度吗**
- [ ] **写了雨的强度（heavy / steady / drizzle）吗**
- [ ] **写了雨丝拖影（motion-blurred streaks）吗**
- [ ] 只有一个镜头指令，而且是固定镜头吗
- [ ] 主体运动和镜头运动分开写了吗
- [ ] 有没有出现 `fast`、`slow`、或单独的 `cinematic`
- [ ] 约束段包含慢镜头、抖动、时间闪烁、镜头运动了吗
- [ ] 描述的运动是周期性的、能接成 loop 吗

---

## 八、校验规则（机器可读）

下面这个 JSON 由 `prompt_rules.py` 在每次提交视频任务前解析并执行。字段含义与图片规则一致，
`allow_negated=true` 表示被 `no / without / avoid` 否定的用法放行 —— 这条对本项目特别重要，
因为约束段里正好要写 `avoid camera movement`、`avoid slow motion`，不能把它当成「要求慢镜头」。

<!-- validator:rules -->
```json
{
  "id": "rain_asmr_video_v2",
  "word_count": { "min": 60, "max": 120 },
  "required_sections": ["Subject:", "Motion:", "Environment:", "Camera:", "Style:", "Constraints:"],
  "required_all": [
    {
      "name": "雨 / 水的撞击（题眼）",
      "terms": ["rain", "raindrop", "raindrops", "droplet", "droplets", "splash"]
    },
    {
      "name": "ASMR 事件（水冠 / 涟漪 / 雾）",
      "terms": ["crown", "crowns", "ripple", "ripples", "mist", "spray", "burst"]
    },
    {
      "name": "实时速度锚点（不写就出慢镜头）",
      "terms": ["real-time", "real time", "realtime", "natural speed", "normal speed", "natural gravity", "true-to-life speed", "1x speed"]
    },
    {
      "name": "雨的强度必须写明",
      "terms": ["heavy", "downpour", "pouring", "pours", "dense", "drizzle", "shower", "moderate", "steady rain", "constant rain", "sheets of rain"]
    },
    {
      "name": "实时快门的视觉证据（雨丝拖影）",
      "terms": ["streak", "streaks", "motion-blurred", "motion blur", "blurred trails", "trails"]
    },
    {
      "name": "节奏词而非摄影参数",
      "terms": ["steady", "continuous", "rhythmic", "constant", "even rhythm", "smooth", "stable"]
    },
    {
      "name": "固定镜头",
      "terms": ["locked-off", "locked off", "fixed framing", "static camera", "tripod"]
    },
    {
      "name": "保持原图构图",
      "terms": ["unchanged", "preserve", "keep the", "stays in place", "same composition"]
    },
    {
      "name": "无缝 loop",
      "terms": ["loop", "seamless", "seamlessly"]
    },
    {
      "name": "负面约束段",
      "terms": ["avoid", "no ", "without"]
    }
  ],
  "forbidden": [
    {
      "name": "慢镜头开关（本项目要自然速度）",
      "terms": ["slow motion", "slow-motion", "slo-mo", "slomo", "slow", "slowly", "sluggish", "languid", "dreamy", "high-speed camera", "high speed camera", "phantom camera", "time-lapse", "timelapse", "time lapse", "speed ramp", "frozen", "suspended in mid-air", "hovering droplets"],
      "allow_negated": true
    },
    {
      "name": "官方头号危险词 fast",
      "terms": ["fast", "rapid", "swift", "quick"],
      "allow_negated": false
    },
    {
      "name": "无指导力形容词",
      "terms": ["epic", "amazing", "beautiful", "stunning", "gorgeous", "lots of movement"],
      "allow_negated": false
    },
    {
      "name": "镜头运动（本项目固定镜头）",
      "terms": ["push-in", "push in", "pull-out", "pull out", "dolly", "orbit", "tracking shot", "aerial", "drone", "handheld", "zoom", "pan"],
      "allow_negated": true
    },
    {
      "name": "会破坏 loop 的单向变化 / 转场",
      "terms": ["cut to", "transition", "scene change", "falls to the ground", "walks", "runs"],
      "allow_negated": true
    },
    {
      "name": "画面里不能有人",
      "terms": ["person", "people", "human", "man", "woman", "face"],
      "allow_negated": true
    }
  ],
  "require_qualified": [
    {
      "name": "cinematic 不能单用",
      "term": "cinematic",
      "must_be_followed_by": ["macro", "realism", "film tone", "35mm", "contrast"]
    }
  ]
}
```

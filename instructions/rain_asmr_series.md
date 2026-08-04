# 雨 ASMR · 三个子系列的意图与约束

频道只做一件事：雨打在东西上的 ASMR。但**用户的使用场景有三种**，画面和声音要求完全不同，
所以拆成三个子系列。一个批次（batch）只属于一个子系列，从种子图开始就定死，
系列图和视频全部继承。

| id | 系列 | 用户在干什么 | 画面要给什么 |
| --- | --- | --- | --- |
| `storm_sleep` | 暴雨助眠 | 躺下要睡着 | 厚重、包裹、看不清远处；密集雨帘持续冲刷 |
| `steady_focus` | 中雨专注 | 工作 / 学习背景音 | 稳定、可预测、不抢注意力；单滴撞击清晰可辨 |
| `drizzle_meditation` | 轻雨冥想 | 冥想 / 呼吸练习 | 稀薄、留白、慢呼吸；细雾与偶发涟漪 |

本文件是**三条链路的共同上游**：种子图 → 系列图 → 视频，三步的提示词和产物都按这里的
意图校验。`scripts/series_video/series.py` 解析文末的 JSON，
`prompt_rules.py` 把它作为**覆盖层**叠在基础规范之上。

---

## 一、为什么要覆盖层，而不是三份独立规范

基础规范（`rain_asmr_image_prompt.md` / `rain_asmr_video_prompt.md`）里有几条是照着「中雨」
调的，暴雨系列会被自己的校验器拦下来：

- 图片规范禁 `storm`（理由是"混乱场面会让后面视频抖"）—— 但暴雨系列的题眼就是大雨；
- 图片规范要求静帧「视频友好」（表面挂珠，禁高速冻滴）—— 但暴雨系列需要中景
  雨帘拉成线，这恰恰是实时快门的证据（见视频规范第三节），由暴雨覆盖层保留；
- 图片规范的避坑表写着 `heavy storm → steady moderate rain`。

所以系列规范能对基础规则做三件事：**追加必填维度**（`required_all`）、
**追加禁用组**（`forbidden`）、**摘掉某个基础禁用组**（`drop_forbidden`，按组名）。
共性仍然只写一遍，差异集中在这里，不会出现三份规范互相漂移。

---

## 二、三个系列的意图

### storm_sleep · 暴雨助眠

**听感目标**：连续、无间隙的宽频白噪音，低频厚实。声音要能盖住环境杂音，
用户听的是"被大雨罩住"的安全感。

**画面翻译**：雨量要大到画面上**没有安静的地方**——主体在被持续冲刷，
水面像烧开一样不停炸开，中景是能看见的雨帘。光要暗、要阴沉，蓝调时刻或夜里，
对比度低，看不清远处。主体选能承受大水量的表面：宽叶、水面、屋檐、石头。

**最容易做砸的地方**：做成"暴风雨"。风、树枝乱摆、闪电都不要——那是灾难片，不是助眠。
雨要垂直、稳定、无止境，狂暴的是**雨量**，不是天气。

### steady_focus · 中雨专注

**听感目标**：节拍均匀、可预测。大脑一旦预测到下一声，就不再分配注意力，这才能当背景音。
需要清脆的单点打击颗粒，不要糊成一片。

**画面翻译**：能数得清的雨滴，每一滴都看得见撞击 → 水冠 → 涟漪的完整过程。
阴天柔和均匀光，灰调，主体清楚、背景暗而虚。这是三个系列里最"标准"的一个，
基础规范的默认值就是照它调的。

**最容易做砸的地方**：雨量飘。忽大忽小会让人不断重新注意到声音，专注就断了。

### drizzle_meditation · 轻雨冥想

**听感目标**：稀疏、有间隙。间隙本身是内容——留白让呼吸有地方放。

**画面翻译**：细雨、雾气重、大量负空间。水珠**挂在**主体上而不是砸上去，
涟漪是偶发的、一圈一圈慢慢摊开。主体选精细的：细叶、花瓣、蕨类、蛛网、苔藓。
光柔、偏亮、可以有一点暖，不要压抑。

**最容易做砸的地方**：稀到没有 ASMR 事件。冥想不等于没声音，仍然要有可辨的撞击点，
只是密度低、间隙长。

---

## 三、规范自己必须先自洽

评审用的 `review_rubric` 和出图用的 `time_variants` / `subject_variants` 是**同一套意图的
两种写法**，写歪了就会出现「按规范生成的图被规范自己判死」。首次接通评审时就撞上过一次：
`steady_focus` 的光线候选里有 `golden hour ... warm rim light`，而它的 rubric 写着
「阴天柔和均匀光、不抢注意力」—— 强逆光必然被判不合格，等于这个系列有四分之一的候选
生下来就是废的。

所以改这个文件时，**候选词库和 rubric 要一起改**。加一条光线候选前先问：
按这条光线出的图，能过自己写的 rubric 吗？

---

## 四、三步都要过的闸门

每一步都是**程序校验 + Gemini 评审**两道，程序先跑（免费、确定性），过了才花钱送评审。

| 步 | 程序校验 | Gemini 评审 |
| --- | --- | --- |
| 种子图 | 基础图片规则 + 系列覆盖 | 看图判断属于哪个系列（可判"都不适合"，附理由） |
| 系列图 | 同上 | 看图判断是否守住意图；**并拦高速摄影静帧**（空中悬珠/定格水冠 → 即梦必出慢镜头） |
| 出视频前 | — | 再看一眼参考图是否视频友好；不合格**不提交**即梦（省一次花钱） |
| 视频 | 基础视频规则 + 系列覆盖 | 抽帧看是否守住意图；另有 ffmpeg 客观测运动量，拦慢镜头 |

Gemini 评审返回 `pass` / `revise` / `reject`：`revise` 会带上改好的 prompt 自动重试，
`reject` 需要重新生成。评审用的 rubric 就是下面 JSON 里每个系列的 `review_rubric`。

---

## 五、系列定义（机器可读）

`series.py` 解析这一块。字段说明：

- `image` / `video`：生成提示词时往槽位里填的英文串（雨量、光线、主体、场景、风格增补）
- `prompt_overlay`：叠在基础规则上的覆盖层，`drop_forbidden` 按**组名**摘掉基础规则里的组
- `review_rubric`：喂给 Gemini 的评审标准，中文写给模型看没问题，但要点要具体到画面证据
- `frame_motion`：视频抽帧后的客观运动量区间（0–100），拦慢镜头和死画面

### frame_motion 的标定依据

区间不是拍脑袋定的，是拿 `/mnt/e/自然之声/to_youtube/` 下**真实拍摄**的素材量出来的
（`video_probe.measure_motion`，相邻帧灰度平均绝对差 ×5）：

| 素材标注 | 样本数 | 区间 | 中位 |
| --- | --- | --- | --- |
| 无雨空镜 | 10 | 0.5 – 1.3 | 0.7 |
| 01 轻雨 | 5 | 2.7 – 5.1 | 3.3 |
| 02 小雨 | 11 | 4.8 – 9.1 | 6.2 |
| 03 中雨 | 6 | 8.2 – 12.0 | 10.2 |
| 04 大雨 | 2 | 16.8 – 19.1 | 19.1 |

作为对照，2026-08-03 那条**慢镜头** AI 视频量到 **3.83** —— 它是中雨场景，却只有真实轻雨
的运动量，这就是"看着像慢放"的客观证据。

两个已知限制，别把这个分数当精确判据：

1. 分数受**主体占画面比例**影响，同样的雨，特写比远景高；区间只做粗筛。
2. 对细雨系列，慢镜头和真实细雨的总运动量本来就重叠，这一层拦不住 ——
   得靠 Gemini 看抽帧里雨滴**有没有拖影**（悬停的小球 = 高速快门 = 慢放）。

<!-- validator:rules -->
```json
{
  "id": "rain_asmr_series_v1",
  "default_series": "steady_focus",
  "series": [
    {
      "id": "storm_sleep",
      "label": "暴雨助眠",
      "intent": "连续无间隙的厚重白噪音，画面上没有安静的地方；狂暴的是雨量而不是天气",
      "image": {
        "rain_phrase": "torrential rain hammers down in dense curtains",
        "style_extra": "visible rain curtains streaking through the mid-ground, wet sheen on the subject, soft mist, low contrast murky background",
        "time_variants": [
          "deep twilight during a downpour, dim cool ambient light",
          "overcast blue hour, heavy cloud cover, cold flat light",
          "night lit only by weak ambient glow, rain catching the light",
          "midday behind thick storm clouds, dark and heavily diffused light"
        ],
        "subject_variants": [
          "a broad green lotus leaf hammered by torrential rain, water sheeting off its rim",
          "a dark still water surface boiling with dense raindrop impacts",
          "a mossy stone slab under pounding rain, water running off every edge",
          "a fresh banana leaf drumming under a downpour, ribs channelling water",
          "a stone basin overflowing as heavy rain fills it",
          "a thick cluster of wet camellia leaves bending under the weight of water"
        ],
        "scene_variants": [
          "flooded pond edge, rain curtains dissolving the background into grey",
          "temple courtyard stone, soaked greenery reduced to dark blur behind",
          "riverbank shallows churning, far bank lost in rain haze",
          "dense tropical undergrowth streaming with runoff, near-black negative space"
        ]
      },
      "video": {
        "rain_intensity": "heavy",
        "motion_extra": "sheets of water run off the surface"
      },
      "prompt_overlay": {
        "image": {
          "required_all": [
            {
              "name": "暴雨的雨量",
              "terms": ["torrential", "downpour", "heavy rain", "pounding", "pouring", "dense curtains", "sheeting"]
            }
          ],
          "forbidden": [
            {
              "name": "暴雨系列不要小雨",
              "terms": ["drizzle", "light rain", "sparse", "gentle rain", "misty rain"],
              "allow_negated": true
            },
            {
              "name": "狂暴的是雨量不是天气",
              "terms": ["hurricane", "typhoon", "chaos", "chaotic", "lightning", "thunder", "gale", "wind-whipped", "swaying branches"],
              "allow_negated": true
            }
          ],
          "drop_forbidden": ["会破坏 loop 的剧烈天气"]
        },
        "video": {
          "required_all": [
            {
              "name": "暴雨的雨量",
              "terms": ["torrential", "downpour", "heavy", "pounding", "pours", "sheets of rain"]
            }
          ],
          "forbidden": [
            {
              "name": "暴雨系列不要小雨",
              "terms": ["drizzle", "light rain", "sparse", "gentle"],
              "allow_negated": true
            },
            {
              "name": "狂暴的是雨量不是天气",
              "terms": ["hurricane", "typhoon", "lightning", "thunder", "gale", "wind", "swaying"],
              "allow_negated": true
            }
          ]
        }
      },
      "review_rubric": "暴雨助眠：画面必须密到没有安静的区域——主体被持续冲刷、水面不停炸开、中景能看见雨帘。光要暗、阴沉、低对比，远处应当被雨糊掉。不合格的典型：雨太稀能数出单滴、画面明亮通透、出现风吹枝条/闪电/浪花等灾难片元素、主体干燥。",
      "frame_motion": { "min": 12, "max": 60 }
    },
    {
      "id": "steady_focus",
      "label": "中雨专注",
      "intent": "节拍均匀可预测的背景音，单点打击清脆可辨，不抢注意力",
      "image": {
        "rain_phrase": "steady moderate rain falls at an even pace",
        "style_extra": "wet surface beads on the subject, soft airborne mist, calm grey background",
        "time_variants": [
          "grey rainy morning, soft even overcast light",
          "overcast blue hour just before dusk, cool diffused light",
          "late afternoon under low rain clouds, soft neutral light",
          "midday summer rain, bright but heavily diffused light"
        ],
        "subject_variants": [
          "a broad green lotus leaf taking steady raindrops, water beading and rolling off",
          "a single fallen maple leaf floating on a puddle, struck by falling drops",
          "a cluster of glossy camellia leaves nodding under rain impact",
          "a still dark water surface, raindrops punching crowns and concentric rings",
          "a mossy stone in a stream, rain splashing off its wet top",
          "a purple petal resting on a lily pad, rain bouncing around it"
        ],
        "scene_variants": [
          "shallow pond edge, blurred reeds and dark water bokeh behind",
          "quiet forest floor, out-of-focus wet foliage receding into shadow",
          "temple garden stone basin, muted background of soaked greenery",
          "still lake surface, low horizon dissolving into rain haze"
        ]
      },
      "video": {
        "rain_intensity": "steady",
        "motion_extra": ""
      },
      "prompt_overlay": {
        "image": {
          "required_all": [
            {
              "name": "中雨的雨量",
              "terms": ["steady", "moderate", "consistent", "even pace", "regular"]
            }
          ],
          "forbidden": [
            {
              "name": "中雨系列不要走极端",
              "terms": ["torrential", "downpour", "pounding", "drizzle", "misty rain", "sparse"],
              "allow_negated": true
            }
          ]
        },
        "video": {
          "required_all": [
            {
              "name": "中雨的雨量",
              "terms": ["steady", "moderate", "consistent", "even"]
            }
          ],
          "forbidden": [
            {
              "name": "中雨系列不要走极端",
              "terms": ["torrential", "downpour", "pounding", "drizzle", "sparse"],
              "allow_negated": true
            }
          ]
        }
      },
      "review_rubric": "中雨专注：雨滴要能数得清，湿表面挂珠清楚，节奏均匀不忽大忽小。光是阴天柔和均匀光，灰调，主体清楚、背景暗而虚。不合格的典型：雨密到糊成一片、雨稀到画面几乎静止、明暗对比强烈抢注意力、主体被水淹没看不清、空中大片悬停水珠或完整定格水冠（高速摄影静帧，后续视频必出慢镜头）。",
      "frame_motion": { "min": 5, "max": 16 }
    },
    {
      "id": "drizzle_meditation",
      "label": "轻雨冥想",
      "intent": "稀疏有间隙，留白即内容；仍要有可辨的 ASMR 撞击点，只是密度低",
      "image": {
        "rain_phrase": "a light drizzle drifts down with long gaps between drops",
        "style_extra": "fine droplets clinging to the subject, thick soft mist, generous negative space",
        "time_variants": [
          "dawn in light drizzle, pale silver light",
          "misty morning after rain, soft warm-neutral light",
          "grey afternoon drizzle, gentle even light",
          "early twilight mist, pale cool light"
        ],
        "subject_variants": [
          "a wet fern frond holding tiny clinging droplets",
          "a spider web strung with fine water beads",
          "a single flower petal with a few drops resting on it",
          "a mossy branch furred with condensation and rare falling drops",
          "a thin blade of grass bowing under one hanging droplet",
          "a shallow puddle showing rare single ripples"
        ],
        "scene_variants": [
          "misty forest floor, pale fog swallowing the background",
          "quiet garden corner, soft grey negative space behind",
          "still shallow water, low horizon lost in fine mist",
          "damp mossy rocks, muted out-of-focus green behind"
        ]
      },
      "video": {
        "rain_intensity": "drizzle",
        "motion_extra": "fine mist drifts across the negative space"
      },
      "prompt_overlay": {
        "image": {
          "required_all": [
            {
              "name": "细雨的雨量",
              "terms": ["drizzle", "light rain", "fine rain", "misty rain", "sparse drops"]
            },
            {
              "name": "雾气 / 留白",
              "terms": ["mist", "fog", "haze", "negative space"]
            }
          ],
          "forbidden": [
            {
              "name": "细雨系列不要大雨",
              "terms": ["torrential", "downpour", "heavy rain", "pounding", "sheeting", "dense curtains"],
              "allow_negated": true
            }
          ]
        },
        "video": {
          "required_all": [
            {
              "name": "细雨的雨量",
              "terms": ["drizzle", "light rain", "fine rain", "misty"]
            }
          ],
          "forbidden": [
            {
              "name": "细雨系列不要大雨",
              "terms": ["torrential", "downpour", "heavy", "pounding", "sheets of rain"],
              "allow_negated": true
            }
          ]
        }
      },
      "review_rubric": "轻雨冥想：雨稀疏、间隙明显，水珠主要是挂在主体上而不是砸上去，雾气重、负空间大、影调柔和偏亮。仍必须存在可辨认的撞击点（哪怕只有一两处涟漪）。不合格的典型：雨密集连成片、画面被水填满没有留白、影调压抑阴沉、完全看不到任何水的运动。注意这个系列的运动量和慢镜头重叠，必须额外确认雨滴带拖影（悬停不动的小球说明是慢放）。",
      "frame_motion": { "min": 2, "max": 7 }
    }
  ]
}
```

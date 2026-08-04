# 雨 + ASMR 系列图 · 提示词最佳实践

适用范围：`系列视频` Tab 里所有出图环节 —— **文生图**（用 prompt 生成待选种子图）和
**图生图**（从种子图生成同系列图）。两者共用同一套四段式公式，只有「与参考图的关系」这一句不同。

本文件是**生成前的强制参考**：`scripts/series_video/prompt_rules.py` 会在运行时读取本文末尾的
校验规则块，任何一条不通过就拒绝调用模型。改规则请改这个文件，不要改代码。

---

## 一、四段式公式：时间 + 主体 + 场景 + 风格

来自 https://public.ysjf.com/stormcourse/courseware/prompt.jpg 的图片提示词脑图。原图把提示词
拆成四个一级分支，每个分支下还有二级维度。下表是四个分支在**本项目（雨 + 打击物 + ASMR 感）**
下的收敛用法 —— 原图里与人物相关的维度（性别/年龄/职业/服装/表情…）在本项目全部弃用，因为画面里
不允许出现人。

| 段位     | 原图的二级维度                                        | 本项目怎么填                                                    |
| ------ | ---------------------------------------------- | --------------------------------------------------------- |
| **时间** | 年代 / 季节 / 时刻                                   | 只用「季节 + 时刻 + 天气光线」。这是全篇杠杆最高的一段，直接决定画面质感                    |
| **主体** | 人物 / 生物 / 物品（类型·形状·大小·颜色·材质·表面细节·风格）           | 用「物品」这一支：被雨打击的**物体** + 材质 + **表面细节（水渍/水膜/挂珠）**            |
| **场景** | 自然（环境·植被）/ 建筑 / 天气                             | 「自然 + 天气」：主体所在的环境、背景虚化里有什么、雨的强度                            |
| **风格** | 画面风格 / 氛围 / 参考 / 色调 / 光源 / 景别 / 角度 / 构图 / 摄影机  | 全系列固定成一个锚点串，保证同一批图看起来是同一组镜头                                |

### 每段的写法要求

**1. 时间 —— 写光，不写钟点**

只写「几点」是浪费。要写这个时刻带来的**光的性质**：方向、色温、软硬。

- 好：`grey rainy morning, soft even overcast light`
- 好：`late afternoon golden hour breaking through rain clouds, warm rim light`
- 差：`morning`（没有光信息）
- 差：`8:30 AM`（模型不理解钟点，只理解光）

**2. 主体 —— 写材质和表面细节，不写名词**

ASMR 的「打击感」来自观众能想象出的**触感**，触感来自材质描述。照搬原图「物品」分支的
`材质` 与 `表面细节（磨损程度/水渍/灰尘）`两个维度：

- 好：`a broad green lotus leaf, waxy hydrophobic surface, water beading into mercury-like droplets`
- 差：`a leaf in the rain`（没有材质，没有表面细节）

必须能看出**雨打在什么上**。这是整个频道的题眼，主体选错了后面视频再好也没用。

**3. 场景 —— 写背景景深和雨的强度**

主体是清楚的，背景必须是**脏而暗**的，这样水珠才能跳出来。写清背景里有什么、如何虚化：

- 好：`shallow pond edge, blurred reeds and dark water bokeh behind, steady moderate rain`
- 差：`in a garden`

**4. 风格 —— 全系列共用同一串，不要每张改**

这一段的作用是「让 8 张图看起来是同一组」，所以它必须是常量。本项目锚定：

```
cinematic macro photography, 100mm lens, very shallow depth of field,
wet surface beads on the subject, soft airborne mist,
desaturated cool film tone, high dynamic range, soft diffused natural light,
no text, no watermark, no people, 16:9 horizontal composition
```

对应原图的 `画面风格=写实/纪录片`、`色调=冷`、`光源=自然光·柔光`、`景别=特写/超大特写`、
`摄影机=100mm 长焦 + 浅景深`、`构图=主体居中`。

**不要写** `crisp frozen droplets` / 定格水冠英雄瞬间：Gemini 很爱出高速摄影静帧，
同图一旦做即梦首尾帧，Seedance 几乎必出慢镜头。水冠留给**视频 Motion 段**去动。

---

## 二、文生图（生成待选种子图）与图生图（系列图）的区别

只有一句话的差别，其余四段完全一样。

| | 文生图（种子图） | 图生图（系列图） |
| --- | --- | --- |
| 参考图 | 无 | 有，走 `inlineData` |
| 额外那句 | `Create a single photographic still frame.` | `Create a NEW image in the same series as the reference image.` + `keep the reference's grading and lens feel, but make subject and framing clearly different` |
| 目的 | 定义整个系列的视觉基调 | 在基调内做变化 |
| 变化幅度 | 一个 prompt 出 N 张候选，靠模型随机性拉开差距 | 主体不重复，时间/场景轮换 |

种子图是整批的基准，值得多生成几张候选再挑。挑选标准：

1. 主体表面的**挂珠 / 水膜是不是清楚**（后面视频的动效锚在湿表面上）
2. 背景是不是够暗够虚（水珠才有对比）
3. 构图有没有留白（留白处后面可以让雾气飘）
4. **不是高速摄影**：空中没有大片悬停水珠，也没有完整定格水冠当主角
5. 有没有出现人、文字、水印

---

## 三、为「后面要变成 5s 固定镜头 loop」而拍

出图时就要考虑下一步。每张图都必须满足：

- **画面是静的**：没有正在跑/飞/倒塌的东西，只有雨和水可以动
- **主体不贴边**：给水花溅开留出空间
- **视频友好静帧（关键）**：同图会做即梦首尾帧。要主体表面挂珠、湿润反光、轻雾；
  **不要**满屏悬空颗粒、hero 级定格水冠、high-speed / phantom 观感——那些对静帧好看，
  对 Seedance 就是慢镜头开关
- **不要整幅长曝光雨丝糊成灰雾**（暴雨系列允许中景雨帘拉线，见系列覆盖层）
- **16:9 横构图**：竖构图后面转视频会被裁

---

## 四、避坑

| 别写                            | 为什么                          | 改成                                        |
| ----------------------------- | ---------------------------- | ----------------------------------------- |
| `crisp frozen droplets` / 定格水冠英雄瞬间 | Gemini 出高速静帧 → 即梦首尾帧锁死慢镜头 | `wet surface beads` / `soft airborne mist` |
| `beautiful` / `amazing` / `epic` / `stunning` | 形容词没有指导力，只占词数        | 具体的光线和材质描述                                |
| `a person holding a leaf`     | 频道题材不含人；出现人还会触发平台的人脸限制 | 去掉人，只留物                                   |
| `4k, 8k, hdr, masterpiece`     | 老式 SD 咒语，对 Gemini 无效，反而稀释指令  | `high dynamic range` 一次就够                 |
| `heavy storm, chaos, wind`    | 混乱场面会让后面视频抖                  | `steady moderate rain`                    |
| 每张图换一套风格串                     | 系列图会散                        | 风格段全批锁死                                   |

---

## 五、可直接套用的模板

```
Create a NEW image in the same series as the reference image.
Theme: rain ASMR macro cinematography: raindrops striking a wet surface,
       visible moisture on the subject and fine water mist.
Time:    <季节 + 时刻 + 光的方向/色温/软硬>
Subject: <被雨打击的物体 + 材质 + 表面细节（挂珠/水膜/纹理）>
Scene:   <环境 + 背景虚化内容 + 雨的强度>
Style:   <全系列共用的风格锚点串>
Keep the reference image's grading and lens feel so the images look like frames from
one series, but make the subject and framing clearly different from the reference.
Leave the frame calm enough that it can be animated later as a static-camera loop.
```

---

## 六、校验规则（机器可读）

下面这个 JSON 由 `prompt_rules.py` 在每次出图前解析并执行。字段含义：

- `word_count`：提示词词数区间
- `required_sections`：必须出现的段落标签（对应四段式）
- `required_all`：每一组至少命中一个词，否则视为缺少该维度
- `forbidden`：命中即失败；`allow_negated=true` 时，被 `no / without / avoid` 否定的用法放行
  （例如 `no people` 合法，`a person` 非法）

<!-- validator:rules -->
```json
{
  "id": "rain_asmr_image_v2",
  "word_count": { "min": 55, "max": 220 },
  "required_sections": ["Theme:", "Time:", "Subject:", "Scene:", "Style:"],
  "required_all": [
    {
      "name": "雨（题眼）",
      "terms": ["rain", "raindrop", "raindrops", "drizzle", "downpour", "rainfall"]
    },
    {
      "name": "ASMR 打击感 / 水的形态",
      "terms": ["splash", "impact", "droplet", "droplets", "ripple", "ripples", "mist", "spray", "beading", "beads", "sheen", "moisture"]
    },
    {
      "name": "视频友好静帧（表面挂珠/湿感，而非空中定格）",
      "terms": ["beading", "beads", "clinging", "wet surface", "wet sheen", "surface beads", "sheen", "mist", "sheeting"]
    },
    {
      "name": "光线（时间段的落点）",
      "terms": ["light", "lighting", "golden hour", "overcast", "backlit", "rim light", "twilight", "diffused"]
    },
    {
      "name": "微距 / 景深（镜头语言）",
      "terms": ["macro", "close-up", "mm lens", "depth of field", "bokeh", "shallow focus"]
    },
    {
      "name": "色调 / 影调",
      "terms": ["tone", "grade", "grading", "desaturated", "cool", "warm", "dynamic range"]
    },
    {
      "name": "材质 / 表面细节",
      "terms": ["surface", "texture", "wet", "glossy", "waxy", "mossy", "smooth", "material"]
    }
  ],
  "forbidden": [
    {
      "name": "高速摄影线索（首尾帧会把即梦带进慢镜头）",
      "terms": ["frozen", "high-speed", "high speed", "phantom", "bullet time", "suspended in mid-air", "hovering droplets", "crisp frozen", "clean splash crowns", "frozen splash", "frozen crown"],
      "allow_negated": true
    },
    {
      "name": "无指导力形容词",
      "terms": ["beautiful", "amazing", "epic", "stunning", "gorgeous", "masterpiece", "best quality"],
      "allow_negated": false
    },
    {
      "name": "画面里不能有人",
      "terms": ["person", "people", "human", "man", "woman", "girl", "boy", "face", "portrait"],
      "allow_negated": true
    },
    {
      "name": "文字 / 水印",
      "terms": ["text", "watermark", "logo", "caption", "subtitle"],
      "allow_negated": true
    },
    {
      "name": "老式画质咒语",
      "terms": ["8k", "uhd", "hyperrealistic", "ultra detailed", "trending on artstation"],
      "allow_negated": false
    },
    {
      "name": "会破坏 loop 的剧烈天气",
      "terms": ["storm", "hurricane", "typhoon", "chaos", "chaotic"],
      "allow_negated": true
    }
  ]
}
```

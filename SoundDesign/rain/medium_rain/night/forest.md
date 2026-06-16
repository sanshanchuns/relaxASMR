# 森林中雨 · 夜晚 · 树下坐听雨

> 树下 **坐着** 撑伞固定听点，恒定中雨，8 h。**L1 主声**（远雨 + 伞面）为同一听音场景的一体声场；**L2 环境**含附近小水坑 **雨落水面**；L3 / L4 仍按单声源分轨。

---

## 场景设定

- **天气**：恒定中雨（medium rain），无雷
- **地点**：温带森林，大树下
- **听音位置**：坐在树下撑伞，**附近**地面有小水坑
- **目标时长**：8 h

**L1 主声（逻辑一体）**——**远雨 + 伞面** 同场、同听点、同一条主轨：

| 层次 | 听感 | 空间 |
|------|------|------|
| 远雨·沙沙 | 林内连续雨幕，浑厚偏暖 | 中远 |
| 雨伞·波波 | 雨滴打在伞面，近、有节奏 | 近 · 头顶 |

**L2 环境 · 水坑**——附近小水坑 **中雨雨滴击打** 的 patter，单独一层 loop（坐态听点，比远雨近、比伞面远）：

| 层次 | 听感 | 空间 |
|------|------|------|
| 水坑·雨落 | 森林地面 **小水坑**，中雨 **雨滴击打** 浅水坑，轻哒哒 patter；**不是溪流、不是流水** | 近 · 地面 · 坐态 |

> **原则说明**：L1 **逻辑优先**——坐在树下撑伞，远雨与伞面是一体主声场。水坑属 **周围环境**，放 L2 独立轨，便于控音量与异长相位。若 L1 层次糊，再 **optional** 拆远雨 / 伞面补层。

---

## 混音比例

| 层级 | 占比 |
|------|------|
| L1 中雨 | 84% |
| L2 环境 | 13% |
| L3 随机 | 2.5% |
| L4 生物 | 0.5% |

---

## Reaper 轨道

| Track | 素材 | 音量 | 触发 |
|-------|------|------|------|
| 01 | L1 树下坐听雨·中雨（一体主声） | -4 dB | 5–8 min · **恒定** |
| 02 | L2 水坑·雨落 | -16 dB | 5–8 min · 异长 |
| 03 | L2 微风·树梢 | -20 dB | 8 min · 异长 |
| 04 | L2 湿叶·摩擦 | -24 dB | 5:30 · 异长 |
| 05 | L2 溪流·远 | -22 dB | 可选 · 10 min |
| 06 | L3 伞沿·落水 | -20 dB | 8–18 min jitter |
| 07 | L3 细枝·断裂 | -22 dB | 18–35 min jitter |
| 08 | L3 细枝·落地 | -22 dB | jitter |
| 09 | L4 夜虫 | -25 dB | 25–45 min jitter |
| 10 | L4 蛙 | -27 dB | 可选 · 45–65 min jitter |

---

## L1 · 中雨 · 树下坐听雨（一体主声）

**听感**：**坐在** 树下撑伞——**远雨沙沙 + 伞面波波** 同时存在；整体 **浑厚、偏暖**，低频饱满，不刺不亮，可长时循环。水坑在 L2，不在此轨。

**ElevenLabs：**

```
Sitting under a tree with umbrella at night, medium rainfall, distant soft shushing rain through forest trees, steady pitter-patter on nylon umbrella canopy overhead, warm mellow tone, rich low-mid body, muffled smooth texture, not sharp not bright, organic irregular rhythm, seamless loop, no thunder no wind no footsteps no voices no movement no puddle no water surface
```

**H4e（推荐）**：树下 **坐着** 撑伞录 **一条 L1 主轨**（远雨 + 伞面）；附近小水坑 **雨滴击打** 可 **另录一条 L2**（麦克风低、近积水处，收 patter 勿对准溪流）。

**后期**：若仍偏尖，RX / Reaper 低通 **10–12 kHz** 缓降 3–6 dB。

### Optional · AI 补层（仅 L1 层次糊或某层缺失时）

| 补层 | Prompt |
|------|--------|
| 远雨 bed | `Medium rainfall in forest at night, distant soft shushing rain through trees, seamless loop, no umbrella no puddle` |
| 伞面 | `Medium rain on nylon umbrella canopy at night, steady pitter-patter, close, seamless loop, no forest ambience no puddle` |

补层音量 **-12 ~ -18 dB**，只填缺，不替代一体主轨。

---

## L2 · 环境

**Track 02 · 水坑·雨落：**

**听感**：森林中雨，附近 **小水坑** 被雨滴击打——连续轻哒哒 patter；**不是** 溅起大 plop，**更不是** 溪流 / 流水 / babbling。坐态听点，不抢 L1 伞面。

**ElevenLabs：**

> 避免 `water surface`、`still water`、`flowing`——易生成流水声；用 **raindrops hitting puddle on forest floor**，与帐顶 `rain on fabric` 同结构。

```
Medium rainfall in forest at night, raindrops hitting small shallow puddles on wet forest ground, soft rhythmic patter on puddle, close ground level nearby, warm mellow tone, muffled smooth, not sharp not bright, no stream no river no flowing water no babbling no creek no umbrella no thunder no wind
```

**Track 03 · 微风：**

```
Gentle breeze through forest treetops at night, soft air movement, no gusts, no rain sound
```

**Track 04 · 湿叶摩擦：**

```
Subtle wet leaf rustle at night, quiet sh-sh, minimal movement, no rain drops
```

**Track 05 · 远处溪流：**

```
Distant quiet forest stream at night, muffled babbling, far away, no rain in sample
```

---

## L3 · 随机

**Track 06 · 伞沿落水：**

```
Single water droplet running off umbrella edge, soft plop below, 1 second, isolated
```

**Track 07 · 细枝断裂：**

```
Single small twig snap in forest at night, soft crack, 0.5 seconds, isolated, no fall sound
```

**Track 08 · 细枝落地：**

```
Single small twig landing on wet forest floor, muffled thud, 0.5 seconds, isolated, no snap sound
```

---

## L4 · 生物

**Track 09 · 夜虫：**

```
Single distant cricket chirp at night, one brief call, 1 second, isolated, no chorus
```

**Track 10 · 蛙：**

```
Single quiet frog croak at night, distant, one call, 1 second, isolated, no chorus
```

---

## 母带

高通 40 Hz · 低通 12 kHz · LUFS -18 ~ -16

---

## 检查清单

- [ ] L1 **一体主声** · 坐态 · 远雨 + 伞面（**不含**水坑）
- [ ] L2 **水坑·雨落** · 雨滴击打水坑 · **非流水** · 异长 loop · -16 dB 起
- [ ] H4e L1 / L2 可分录 **或** ElevenLabs 分 Prompt
- [ ] L3 / L4 单声源 · 无雷 · jitter
- [ ] 8 h 跳听

# 森林细雨 · 夜晚 【P1-①】

> 制作优先级 **第 1 条**。林内固定听点，恒定细雨，8 h 睡眠向。  
> **单一音效**：每轨一种声源；下列 Prompt 各生成独立素材，Reaper 并行叠。

---

## 场景设定

- **时间**：入夜至凌晨
- **天气**：恒定细雨（light drizzle），无雷
- **地点**：温带森林，地面潮湿，落叶层
- **听音位置**：坐在/躺在林内一点，不移动
- **目标时长**：8 h

---

## 混音比例

| 层级 | 占比 | 说明 |
|------|------|------|
| L1 细雨 | 86% | 树叶主轨 + 可选树冠轨，各单声源 |
| L2 环境 | 12% | 风、叶摩擦、溪流各独立轨 |
| L3 随机 | 1.5% | 大滴、枝断、枝落各 one-shot |
| L4 生物 | 0.5% | 夜虫 / 蛙各独立轨 |

---

## Reaper 轨道

| Track | 素材（单声源） | 音量 | 触发 |
|-------|----------------|------|------|
| 01 | L1 细雨·树叶 | -5 dB | 5–8 min loop · **恒定** |
| 02 | L1 细雨·树冠 | -9 dB | 可选 · 5–8 min · **恒定** |
| 03 | L2 微风·树梢 | -22 dB | 8 min · 异长 · **恒定** |
| 04 | L2 湿叶·摩擦 | -26 dB | 5:30 · 异长 · **恒定** |
| 05 | L2 溪流·远 | -24 dB | 可选 · 10 min · **恒定** |
| 06 | L3 树冠·积水滴 | -22 dB | 10–25 min jitter |
| 07 | L3 细枝·断裂 | -24 dB | 25–45 min jitter |
| 08 | L3 细枝·落地 | -24 dB | 紧接 07 或独立 jitter |
| 09 | L4 夜虫 | -26 dB | 30–50 min jitter |
| 10 | L4 蛙 | -28 dB | 可选 · 50–70 min jitter |

---

## L1 · 细雨

### Track 01 · 树叶

**听感**：稀疏沙沙，滴与滴之间有明显间隙。

**ElevenLabs：**

```
Light drizzle on broad forest tree leaves at night, sparse soft droplets, gentle irregular sh-sh texture, very quiet, long pauses between hits, seamless loop, no thunder no wind
```

**H4e**：林内固定机位；一条混合实拍可替代 01+02，AI 补层仍按单声源生成。

### Track 02 · 树冠（可选）

**ElevenLabs：**

```
Light drizzle on forest tree canopy at night, sparse droplets on upper branches, very quiet minimal patter, seamless loop, no thunder no wind
```

---

## L2 · 环境（各轨单声源）

**Track 03 · 微风 · ElevenLabs：**

```
Very faint breeze through forest treetops at night, barely audible soft air movement, no gusts, no rain sound,  sleep volume
```

**Track 04 · 湿叶摩擦 · ElevenLabs：**

```
Very subtle wet leaf rustle at night, extremely quiet sh-sh, minimal movement, no rain drops
```

**Track 05 · 远处溪流 · ElevenLabs：**

```
Very distant quiet forest stream at night, muffled babbling, far away, no rain in sample,  barely audible
```

---

## L3 · 随机（各 one-shot 单动作）

**Track 06 · 树冠滴 · ElevenLabs：**

```
Single soft water droplet falling from a forest leaf, quiet plop, 1 second, isolated, no other sounds
```

**Track 07 · 细枝断裂 · ElevenLabs：**

```
Single small twig snap in forest at night, soft crack, 0.5 seconds, isolated, no fall sound
```

**Track 08 · 细枝落地 · ElevenLabs：**

```
Single small twig landing on wet forest floor at night, muffled thud, 0.5 seconds, isolated, no snap sound
```

---

## L4 · 生物（各轨单物种）

**Track 09 · 夜虫 · ElevenLabs：**

```
Single distant cricket chirp at night, one brief quiet call, 1 second, isolated, no chorus
```

**Track 10 · 蛙 · ElevenLabs：**

```
Single quiet frog croak at night, distant, one ribbit, 1 second, isolated, no chorus
```

---

## 母带

- 高通 40 Hz · 低通 12 kHz
- LUFS 约 -18 ~ -16

---

## 检查清单

- [ ] 每轨仅一种声源；Prompt 无 and / with 复合
- [ ] L1 全程恒定，无 automation
- [ ] 无雷、无鸟
- [ ] L3/L4 jitter 非固定间隔
- [ ] 8 h 跳听无循环感

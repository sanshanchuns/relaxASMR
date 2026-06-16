# 溪流细雨 · 夜晚 【P1-④】

> 制作优先级 **第 4 条**。溪边固定听点，8 h 睡眠向。  
> **单一音效**：L1 岸植细雨、L2 溪流 **分轨**；禁止一句 Prompt 写「雨 + 溪」。

---

## 场景设定

- **时间**：入夜至凌晨
- **天气**：恒定细雨，无雷
- **地点**：浅溪 / 山涧旁
- **听音位置**：溪边固定一点
- **目标时长**：8 h

---

## 混音比例

| 层级 | 占比 | 说明 |
|------|------|------|
| L1 岸植细雨 | 72% | 仅 ferns / 岸草，不含水声 |
| L2 溪流 | 16% | 仅流水，不含雨声 |
| L3 随机 | 1.5% | 入水 plop、岸石滴 |
| L4 生物 | 0.5% | 蛙、虫各独立轨 |

---

## Reaper 轨道

| Track | 素材（单声源） | 音量 | 触发 |
|-------|----------------|------|------|
| 01 | L1 细雨·岸植 | -6 dB | 5–8 min loop · **恒定** |
| 02 | L2 溪流·babbling | -16 dB | 6–10 min · 异长 · **恒定** |
| 03 | L2 夜风 | -24 dB | 可选 · 8 min |
| 04 | L3 叶上滴·入水 | -22 dB | 12–28 min jitter |
| 05 | L3 岸石·滴水 | -24 dB | 20–40 min jitter |
| 06 | L4 蛙 | -26 dB | 35–55 min jitter · 可选 |
| 07 | L4 夜虫 | -26 dB | 35–55 min jitter · 可选 |

L1 与 L2 **全程并行**，异长错相位。

---

## L1 · Track 01 · 岸植细雨

**ElevenLabs：**

```
Light drizzle on streamside ferns at night, sparse soft droplets, very quiet sh-sh, seamless loop, no water flow no thunder
```

**H4e**：麦指向岸侧植被，避免把溪流录进 L1。

---

## L2 · Track 02 · 溪流

**ElevenLabs：**

```
Small forest stream babbling at night, gentle continuous water flow, soft brook, no rain in sample
```

---

## L2 · Track 03 · 夜风（可选）

**ElevenLabs：**

```
Very faint breeze at night, barely audible air movement, no rain no water
```

---

## L3 · 随机

**Track 04 · 入水 plop · ElevenLabs：**

```
Single water drop falling into quiet stream, soft plop, 1 second, isolated
```

**Track 05 · 岸石滴 · ElevenLabs：**

```
Single water drip from wet rock, soft tap, 1 second, isolated
```

---

## L4 · 生物

**Track 06 · 蛙 · ElevenLabs：**

```
Single quiet frog croak at night, distant, one call, 1 second, isolated, no chorus
```

**Track 07 · 夜虫 · ElevenLabs：**

```
Single distant cricket chirp at night, one brief call, 1 second, isolated, no chorus
```

---

## 母带

- 高通 40 Hz · 低通 12 kHz
- L1 / L2 分轨生成，勿用「雨溪合一」素材

---

## 检查清单

- [ ] L1 无溪水 · L2 无雨声
- [ ] 两轨并行 · 异长 · L1 恒定
- [ ] 8 h 跳听

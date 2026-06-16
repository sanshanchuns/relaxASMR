# 木屋细雨 · 夜晚 【P1-③】

> 制作优先级 **第 3 条**。室内听音，木屋顶细雨，8 h 睡眠向。  
> **单一音效**：每轨一种声源；窗沿 / 玻璃属 L3 one-shot，不与屋顶混写 Prompt。

---

## 场景设定

- **时间**：入夜至凌晨
- **天气**：恒定细雨，无雷
- **地点**：森林 / 山地小木屋室内
- **听音位置**：室内床 / 沙发
- **目标时长**：8 h

---

## 混音比例

| 层级 | 占比 | 说明 |
|------|------|------|
| L1 木屋顶 | 85% | 仅屋顶木板细雨 |
| L2 环境 | 12% | 窗外 muffled 雨，单声源 |
| L3 随机 | 2% | 檐滴、玻璃滑水、地板滴，各独立 |
| L4 生物 | 关闭 | — |

---

## Reaper 轨道

| Track | 素材（单声源） | 音量 | 触发 |
|-------|----------------|------|------|
| 01 | L1 细雨·木屋顶 | -5 dB | 5–8 min loop · **恒定** |
| 02 | L2 窗外·muffled 雨 | -24 dB | 8 min · 异长 · **恒定** |
| 03 | L3 屋檐·滴水 | -20 dB | 10–22 min jitter |
| 04 | L3 玻璃·滑水 | -22 dB | 15–35 min jitter |
| 05 | L3 木地板·远滴 | -24 dB | 可选 · 25–45 min jitter |

---

## L1 · Track 01 · 木屋顶

**ElevenLabs：**

```
Light rain on wooden cabin roof planks at night, soft sparse patter, warm wood resonance, seamless loop, no thunder no creaking no voices
```

**H4e**：木屋内录制；室外录屋顶时需另轨，不与室内混一句 Prompt。

---

## L2 · Track 02 · 窗外雨

**ElevenLabs：**

```
Muffled light rain outside cabin window at night, very distant through glass, no indoor roof sound,  barely audible
```

---

## L3 · 随机

**Track 03 · 屋檐滴 · ElevenLabs：**

```
Single water drop dripping from wooden eaves, soft plop, 1 second, isolated
```

**Track 04 · 玻璃滑水 · ElevenLabs：**

```
Single water droplet sliding down window glass, soft squeak, 2 seconds, isolated
```

**Track 05 · 地板远滴 · ElevenLabs：**

```
Single water drip landing on wooden floor, soft tap, 1 second, isolated
```

---

## 母带

- 高通 45 Hz · 低通 11 kHz

---

## 检查清单

- [ ] L1 仅屋顶；窗 / 檐 / 地板各为独立 L3
- [ ] 无定时 wood creak
- [ ] L1 恒定 · 8 h 跳听

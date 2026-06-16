# 大雨专辑 · 共用规范

**heavy rain（大雨）**：密集、饱满、低频更丰富，仍 **非暴雨 / 非雷暴**。与 [细雨](../drizzle/README.md) · [中雨](../medium_rain/README.md) 共享：主轨恒定、固定听点、单一音效、反循环。

---

## 大雨定义

| 项目 | 大雨 | 对比中雨 |
|------|------|----------|
| 密度 | 密集连续 patter，间隙极短 | 连续均匀 |
| 听感 | 沙沙声墙 / 强哒哒 / 重啪嗒 | 中等 |
| 低频 | 明显 richer low-mid | 适中 |
| 主轨 | **恒定** loop，整片不变 | 同 |
| 时长 | 夜晚 **3–8 h**（能量更高，可短于细雨 8 h）；其余时段 3–8 h | 夜 8 h |

**默认无雷**；雷暴另开专辑。不做大雨↔中雨 crossfade。

---

## 四场景 · L1 主声签名

| 场景 | 听感 | L1（单声源分轨） |
|------|------|------------------|
| **森林** | 密集沙沙 | 树叶大雨（主）· 树冠 optional |
| **帐篷** | 强哒哒 | rainfly 大雨 |
| **木屋** | 重啪嗒 | 木屋顶大雨 |
| **溪流** | 暴雨感 + 水声 | L1 岸植 · L2 溪流（分轨） |

---

## 四时段 · 差异总表

| 项目 | 夜晚 P1 | 黎明 P2 | 黄昏 P3 | 白天 P4 |
|------|---------|---------|---------|---------|
| 主层 EQ | 低通 ~11 kHz | ~13 kHz | ~14 kHz | ~15 kHz |
| 高通 | ~45 Hz | ~38 Hz | ~35 Hz | ~30 Hz |
| L2 风 | 轻–中 | 轻 | 轻–中 | 中 |
| L3 远雷 | **关闭** | **关闭** | **关闭** | 可选 · ≥35 min · -22 dB |
| L4 生物 | 通常关闭 / 极 sparse | 晨鸟 sparse | 远虫 + 偶鸟 | 极 sparse 鸟 |
| L3 事件 | 略密于中雨 | 同 | 同 | 同 |

---

## ElevenLabs · 大雨快速 Prompt（单声源）

| 场景 | 轨 | Prompt |
|------|-----|--------|
| 森林 | L1 树叶 | `Heavy rainfall on broad forest tree leaves, dense continuous shushing patter, seamless loop, no thunder no wind` |
| 森林 | L1 树冠 optional | `Heavy rainfall on forest tree canopy, dense continuous patter on upper branches, seamless loop, no thunder no wind` |
| 帐篷 | L1 rainfly | `Heavy rain on nylon tent rainfly, dense steady pitter-patter, continuous heavy pitter-patter on fabric, seamless loop, no thunder no flapping` |
| 木屋 | L1 屋顶 | `Heavy rain on wooden cabin roof planks, dense steady patter, continuous heavy patter on wood, seamless loop, no thunder` |
| 溪流 | L1 岸植 | `Heavy rainfall on streamside ferns, dense continuous sh-sh patter on leaves, heavy sh-sh, seamless loop, no water flow no thunder` |
| 溪流 | L2 溪水 | `Forest stream flowing strongly, steady babbling, continuous water flow, no rain in sample` |

---

## 子方案索引

|  | 森林 | 帐篷 | 木屋 | 溪流 |
|--|------|------|------|------|
| **夜晚** | [night/forest.md](./night/forest.md) | [night/tent.md](./night/tent.md) | [night/cabin.md](./night/cabin.md) | [night/stream.md](./night/stream.md) |
| **黎明** | [dawn/forest.md](./dawn/forest.md) | [dawn/tent.md](./dawn/tent.md) | [dawn/cabin.md](./dawn/cabin.md) | [dawn/stream.md](./dawn/stream.md) |
| **黄昏** | [dusk/forest.md](./dusk/forest.md) | [dusk/tent.md](./dusk/tent.md) | [dusk/cabin.md](./dusk/cabin.md) | [dusk/stream.md](./dusk/stream.md) |
| **白天** | [day/forest.md](./day/forest.md) | [day/tent.md](./day/tent.md) | [day/cabin.md](./day/cabin.md) | [day/stream.md](./day/stream.md) |

时段顺序：夜晚 → 黎明 → 黄昏 → 白天 · 场景：森林 → 帐篷 → 木屋 → 溪流

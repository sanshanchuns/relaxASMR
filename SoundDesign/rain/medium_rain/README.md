# 中雨专辑 · 共用规范

**medium rain（中雨）**：连续、均匀、沙沙 / 哒哒 / 啪嗒，密度高于细雨，仍非暴雨。与 [细雨专辑](../drizzle/README.md) 共享制作原则，雨势更满、低频略多。

---

## 中雨定义

| 项目 | 中雨 | 对比细雨 |
|------|------|----------|
| 密度 | 连续 patter，滴落密集、间隙短 | 稀疏、颗粒可见 |
| 听感 | 沙沙沙沙 / 哒哒 / 啪嗒 | 几乎 whisper |
| 主轨 | 一条（或多轨单声源并行）**恒定** loop | 同 |
| 时长 | 夜晚 **8 h**；黎明 / 黄昏 / 白天 **3–8 h** | 同 |

---

## 共用原则（与细雨一致）

- **主轨恒定**：整片不做雨势 automation，不做中→大→小切换  
- **固定听点**：循环轨并行，不按时间换场景  
- **单一音效**：一轨一声源、一 Prompt 一动作 → 见 [细雨 · 单一音效原则](../drizzle/README.md#单一音效原则)  
- **反循环**：仅 L3/L4 jitter + L2 异长相位差  
- **AI**：仅 ElevenLabs；H4e 实拍优先  

**中雨专辑默认无雷**（雷暴另开专辑）。

---

## 四场景 · L1 主声签名

| 场景 | 听感 | L1 主声（单声源分轨） | 听音位置 |
|------|------|------------------------|----------|
| **森林** | 沙沙沙沙 | 树叶中雨（主）；树冠 optional | 林内 |
| **帐篷** | 哒哒哒哒 | rainfly 中雨 | 帐内 |
| **木屋** | 啪嗒啪嗒 | 木屋顶中雨 | 室内 |
| **溪流** | 沙沙 + 哗哗 | L1 岸植中雨 · L2 溪流（分轨） | 溪边 |

---

## 四时段 · 差异总表

| 项目 | 夜晚 P1 | 黎明 P2 | 黄昏 P3 | 白天 P4 |
|------|---------|---------|---------|---------|
| 主层 EQ | 低通 ~12 kHz，略暖 | 低通 ~13 kHz | 低通 ~14 kHz | 中性 ~16 kHz |
| 高通 | ~40 Hz | ~38 Hz | ~35 Hz | ~30 Hz |
| L2 风 | 轻 | 轻 | 轻 | 轻–中 |
| L3 远雷 | **关闭** | **关闭** | **关闭** | 可选 · ≥40 min jitter · -24 dB |
| L4 生物 | 夜虫、蛙 | 晨鸟 + 远虫渐弱 | 远虫 + 极偶鸟 | 极 sparse 鸟鸣 |
| L3 事件 | 比细雨略密 | 同 | 同 | 同 |

---

## 五层架构（中雨版）

| 层级 | 占比 | 角色 |
|------|------|------|
| L1 | 80–88% | 中雨主轨，恒定 |
| L2 | 10–16% | 风、叶摩擦、溪流，各单轨恒定 |
| L3 | 2–4% | 随机 one-shot（略多于细雨） |
| L4 | ≤1% | 生物 |
| L5 | 贯穿 | 空间 EQ / 混响 |

---

## ElevenLabs · 中雨快速 Prompt（单声源）

| 场景 | 轨 | Prompt |
|------|-----|--------|
| 森林 | L1 树叶 | `Medium rainfall on broad forest tree leaves, continuous soft shushing patter, warm mellow tone, rich low-mid body, muffled smooth, not sharp not bright, seamless loop, no thunder no wind` |
| 森林 | L1 树冠 optional | `Medium rainfall on forest tree canopy, continuous patter on upper branches, seamless loop, no thunder no wind` |
| 帐篷 | L1 rainfly | `Medium rain on nylon tent rainfly, steady pitter-patter on fabric, seamless loop, no thunder no flapping` |
| 木屋 | L1 屋顶 | `Medium rain on wooden cabin roof planks, steady soft patter on wood, seamless loop, no thunder` |
| 溪流 | L1 岸植 | `Medium rainfall on streamside ferns, continuous soft droplets, steady sh-sh, seamless loop, no water flow no thunder` |
| 溪流 | L2 溪水 | `Forest stream flowing, steady gentle babbling, continuous water flow, no rain in sample` |

---

## 子方案索引

|  | 森林 | 帐篷 | 木屋 | 溪流 |
|--|------|------|------|------|
| **夜晚** | [night/forest.md](./night/forest.md) | [night/tent.md](./night/tent.md) | [night/cabin.md](./night/cabin.md) | [night/stream.md](./night/stream.md) |
| **黎明** | [dawn/forest.md](./dawn/forest.md) | [dawn/tent.md](./dawn/tent.md) | [dawn/cabin.md](./dawn/cabin.md) | [dawn/stream.md](./dawn/stream.md) |
| **黄昏** | [dusk/forest.md](./dusk/forest.md) | [dusk/tent.md](./dusk/tent.md) | [dusk/cabin.md](./dusk/cabin.md) | [dusk/stream.md](./dusk/stream.md) |
| **白天** | [day/forest.md](./day/forest.md) | [day/tent.md](./day/tent.md) | [day/cabin.md](./day/cabin.md) | [day/stream.md](./day/stream.md) |

**制作顺序**（每个时段内）：森林 → 帐篷 → 木屋 → 溪流。时段优先级：夜晚 → 黎明 → 黄昏 → 白天。

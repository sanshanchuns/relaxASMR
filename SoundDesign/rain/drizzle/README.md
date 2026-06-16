# 细雨专辑 · 共用规范

当前专辑统一为 **light drizzle（细雨）**：稀疏、轻、睡眠安全，非中雨 / 大雨。

---

## 细雨定义

| 项目 | 细雨 |
|------|------|
| 密度 | 稀疏 droplets，颗粒感可见，非连续「墙」 |
| 音量 | 整体偏低，长时聆听不疲劳 |
| 主轨 | 一条恒定 loop，整片不变 |
| 时长 | 夜晚目标 **8 h**；黎明 / 黄昏 / 白天 **3–8 h** |

---

## 单一音效原则

- **一条 Reaper 轨道 = 一种声音**；一个 ElevenLabs Prompt 只描述**一种声源、一种动作**
- 听感上的「复合」（如树叶 + 树冠、雨 + 溪流、断裂 + 落地）→ **拆成多条轨道、多个 Prompt**，后期并行叠加
- H4e 实拍可录到混合声场，当作一条主轨；**ElevenLabs 补层必须按单声源拆分生成**

| ❌ 一句 Prompt 写多种 | ✅ 拆开 |
|----------------------|--------|
| rain on leaves **and** canopy | Track A: leaves · Track B: canopy |
| roof **and** window sill | Track A: roof · Track B: window sill |
| drizzle **with** stream nearby | Track A: drizzle · Track B: stream |
| twig **crack and** thud | Track A: snap · Track B: thud |
| rain **and** forest ambience | Track A: rain · Track B: wind / birds… |
| **shushing patter + droplet impacts**（同一句） | L1 只写 **一种纹理**；离散大滴 → L3 one-shot |

**Prompt 措辞**：`pitter-patter` / `sh-sh patter` 是**一种**表面纹理词，可以保留。不要在同一句里再叠 `steady droplet impacts` / `droplets on X` 与 patter 并列——AI 易生成双层瞬态（波形毛刺），离散滴落应走 L3。

**`seamless loop`**：仅 **L1 主轨** Prompt 使用（Reaper 长时循环）。**L2 / L3 / L4** 为短素材或 one-shot，Prompt **不要**写 seamless loop；L3/L4 用 `Single … isolated` 等描述即可。

---

## 四场景 · L1 主声签名

| 场景 | 听感 | L1 主声（每轨单一声源） | 听音位置 |
|------|------|-------------------------|----------|
| **森林** | 沙沙 | 树叶细雨（主）；树冠 / 地面可另轨 optional | 林内 |
| **帐篷** | 哒哒 | 帐顶 rainfly 细雨（主） | 帐内 |
| **木屋** | 啪嗒 | 木屋顶细雨（主）；窗沿可 L3 one-shot | 室内 |
| **溪流** | 沙沙 + 哗哗 | L1 岸侧植被细雨 · L2 溪流（**分轨**，非一句 Prompt） | 溪边 |

H4e 建议：**在最终听音位置录制**；一条混合实拍可作主轨，AI 补层仍按上表拆分。

---

## 四时段 · 差异总表

| 项目 | 夜晚 P1 | 黎明 P2 | 黄昏 P3 | 白天 P4 |
|------|---------|---------|---------|---------|
| 主层 EQ | 低通 ~12 kHz，略暖 | 低通 ~13 kHz，微亮 | 低通 ~14 kHz，暖 | 中性，可略亮 |
| 高通 | ~40 Hz | ~38 Hz | ~35 Hz | ~30 Hz |
| L2 风 | 极轻 | 极轻 | 轻 | 轻–中 |
| L3 远雷 | **关闭** | **关闭** | **关闭** | 可选 · 极稀疏 |
| L4 生物 | 夜虫、蛙 | **晨鸟** sparse + 远虫渐弱 | 远虫 + 极偶归巢鸟 | 极 sparse 鸟鸣 |
| 目标 | 睡眠 | gentle wake、晨冥想 | 放松、过渡 | 专注、背景 |

**细雨专辑默认无雷**；L3 以 fabric drip / 木檐滴 / 树冠大滴 / 叶落等低音量事件为主。

---

## 五层架构（细雨版）

| 层级 | 占比 | 角色 |
|------|------|------|
| L1 | 78–88% | 细雨主轨，**恒定** |
| L2 | 10–18% | 环境底（风、叶、溪流…），恒定 loop，可异长 |
| L3 | 1–3% | 随机 one-shot，**唯一变化源之一** |
| L4 | ≤1% | 生物，极 sparse |
| L5 | 贯穿 | 近/中/远 EQ + 混响 |

---

## 反循环 · 主轨恒定

要点：

1. L1 **无 automation**，同一条细雨 loop 跑满全片  
2. L3/L4 **random jitter** 触发，禁止固定间隔  
3. 不做中→大→小 crossfade  
4. L2 可选异长 loop + 起播错开  
5. 各循环轨自身亦遵守**单一音效**，异长相位差靠**多轨单声源**组合实现  

---

## Reaper 模板（细雨 · 通用）

```
Track 01  L1_Drizzle_Main              [循环 · 恒定]
Track 02  L2_Ambient_A                 [循环 · 可选 · 异长 · 恒定]
Track 03  L2_Ambient_B                 [循环 · 可选 · 恒定]
Track 04  L3_Random_01                 [one-shot · jitter]
Track 05  L3_Random_02                 [one-shot · jitter]
Track 06  L4_Bio                       [one-shot · 极 sparse]
```

各场景 / 时段文档中填写具体素材名、音量、**单声源** Prompt。

---

## ElevenLabs · 细雨快速 Prompt（单声源 · 拆分）

| 场景 | 轨 | Prompt |
|------|-----|--------|
| 森林 | L1 树叶 | `Light drizzle on broad forest tree leaves, sparse soft droplets, gentle sh-sh, very quiet, seamless loop, no thunder` |
| 森林 | L1 树冠 optional | `Light drizzle on forest tree canopy, sparse droplets on upper branches, very quiet, seamless loop, no thunder` |
| 帐篷 | L1 rainfly | `Light rain on nylon tent rainfly, soft pitter-patter, sparse droplets, seamless loop, no thunder` |
| 木屋 | L1 屋顶 | `Light rain on wooden cabin roof planks, soft sparse patter, seamless loop, no thunder` |
| 溪流 | L1 岸植 | `Light drizzle on streamside ferns, sparse droplets, very quiet sh-sh, seamless loop, no thunder` |
| 溪流 | L2 溪水 | `Small forest stream babbling, gentle continuous water flow, soft brook, no rain in sample` |

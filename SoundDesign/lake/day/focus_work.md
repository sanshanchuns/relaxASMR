# 湖泊 · 白天 · 静心工作

> 固定听点：湖岸 / 稍远视角望湖面；主轨舒缓钢琴，副轨划船纹理 + 高低频稀疏鸟鸣。目标 **3 h**（可扩 8 h）。

---

## 场景设定

- **天气**：白天、微云或晴，无风雨无雷  
- **地点**：亚热带 / 温带开阔湖面（可配西湖、千岛湖类视觉）  
- **画面参考**：[千岛湖 · 黄昏](../../VisualDesign/lake/qiandao/dusk.md) · CN-118 梅峰岛  
- **听音位置**：岸上固定一点，远处有零星手划船，近处偶发鸟叫  
- **用途**：专注工作、阅读、轻度冥想（**非睡眠**）  
- **目标时长**：3 h（工作 session）；循环规则同 [StreamHeal](../../Reaper/Projects/StreamHeal/) 工程  

---

## 听感目标

| 维度 | 要求 |
|------|------|
| 钢琴 | 舒缓、简单和声、无炫技、无强烈情绪起伏 |
| 划船 | 远、慢、像背景节奏而非「正在旁边划」 |
| 鸟 · 高频 | 清亮、短促、单声，不连鸣 |
| 鸟 · 低频 | 低鸣、咕咕、水鸟，间隔更长 |
| 整体 | 清晰可听钢琴旋律线，环境只填空间不抢戏 |

---

## 混音比例

| 层级 | 内容 | 占比 | 角色 |
|------|------|------|------|
| **L1** | 舒缓钢琴 | **68–72%** | 主轨 · 恒定 loop |
| **L2a** | 湖面细浪 / 拍岸 | **8–10%** | 空间底 · 恒定 |
| **L2b** | 远处划船 | **10–12%** | 节奏纹理 · 恒定 loop |
| **L3h** | 鸟鸣 · 高频 | **≤2%** | 随机 one-shot |
| **L3l** | 鸟鸣 · 低频 | **≤1.5%** | 随机 one-shot |

L1 / L2a / L2b **全程并行**，loop 长度互质（见下）。

---

## Reaper 轨道

| Track | 名称 | 素材 | 推子参考 | 触发 |
|-------|------|------|----------|------|
| **01** | `piano_main` | 钢琴 seamless loop（4–6 min） | **0 dB**（基准） | 恒定 · loop |
| **02** | `lake_lap` | 极轻湖面拍岸 / 细浪 | **-14 dB** | 5–7 min · 恒定 |
| **03** | `rowing_distant` | 远处划船 · 入水 + 划水 | **-12 dB** | 2:40–3:20 · 异长 · 恒定 |
| **04** | `bird_high` | 小型鸣禽 · 单声 | **-22 dB** | **≥12 min** jitter |
| **05** | `bird_low` | 低鸣 / 水鸟 · 单声 | **-24 dB** | **≥25 min** jitter |
| **06** | `video` | 背景视频 loop | — | 同 StreamHeal |

**异长建议**：01 = 5:00 · 02 = 6:30 · 03 = 2:50 → 约 **87 min** 才回到同相位。

主轨 FX（Track 01 可选）：极轻 plate reverb（decay 1.2 s，mix 8–12%），增加「湖岸空间」但不糊。

---

## L1 · 钢琴主轨

**来源（择一）**

1. **自编 MIDI** → 钢琴 VST（如 Soft Piano、Keyscape Gentle）→ 导出 loop  
2. **免版税库**：Artlist / Epidemic「calm piano lake / focus piano」类，剪 4–6 min 无缝 loop  
3. **禁止**：带歌词、强动态古典、每 30 s 换调性、明显的「副歌—桥段」结构  

**编曲约束**

| 项 | 建议 |
|----|------|
| 速度 | 60–72 BPM |
| 调性 | 单调或简单 I–IV–vi–V，整 loop 不换调 |
| 力度 | 弱–中弱（mp），无 ff 砸键 |
| 频段 | 能量集中在 **200 Hz–4 kHz**，避免轰头低频 |
| 循环点 | 在整小节边界剪接，交叉淡化 50–100 ms |

**RX / 预处理**

- 去齿音 / 键噪（若 VST 过亮）  
- 高通 **80 Hz**（12 dB/oct）  
- 若源动态过大：轻压缩 ratio 2:1，GR ≤ 3 dB  

---

## L2a · 湖面细浪

**ElevenLabs：**

```
Gentle lake water lapping on shore, very soft continuous ripple, calm daytime, seamless loop, no boat no birds no wind gusts
```

**H4e（可选实拍）**：麦距岸 1 m，录 30 s–2 min 恒定细浪，RX 去明显异音后 loop。

---

## L2b · 远处划船

**听感**：100 m 以外手划船，能感到 **划—停—划** 的慢节奏，但不清晰到听见对话或溅水打脸。

**ElevenLabs · 入水（可叠 2 轨错相位）：**

```
Single distant rowing oar dipping into calm lake water, soft splash, one stroke, 1.5 seconds, isolated, no voice no motor
```

**ElevenLabs · 划水拖尾（loop 底）：**

```
Distant rowboat oars rowing on calm lake, slow gentle rhythm, soft water swish, far away, continuous loop, no motor no voices
```

**处理**

- 低通 **6 kHz**，营造距离  
- 左右 **±15–25** 缓慢 pan automation（周期 3–5 min）  
- 与钢琴 **错开强拍**：划船峰值避开钢琴每小节第一拍（手动偏移 200–400 ms 或异长 loop 自然错开）  

---

## L3h · 鸟鸣 · 高频

**物种参考**：柳莺、绣眼、远处山雀类——**短、亮、高**。

**ElevenLabs：**

```
Single small songbird chirp near lakeshore, one bright short call, high pitch, 1 second, isolated, no flock no chorus
```

| 参数 | 值 |
|------|-----|
| 间隔 jitter | **12–22 min** |
| 电平 | **-22 ~ -20 dB**（相对 piano 0 dB 轨） |
| 声像 | 交替 L **30%** / R **70%**，勿居中连发 |

---

## L3l · 鸟鸣 · 低频

**物种参考**：斑鸠咕咕、远处野鸭低鸣、水鸟振翅低频——**低、短、闷**。

**ElevenLabs：**

```
Single low-pitched dove coo near calm lake, one soft mournful call, low frequency, 1.5 seconds, isolated, no flock
```

| 参数 | 值 |
|------|-----|
| 间隔 jitter | **25–45 min** |
| 电平 | **-24 ~ -22 dB** |
| EQ | 高通 **150 Hz**，低通 **2.5 kHz**，与高频鸟分频段 |

**高低频鸟不得同分钟出现**；Reaper 脚本 jitter 窗口错开 ≥3 min。

---

## 空间与 EQ（母带前）

| 轨 | 高通 | 低通 | 备注 |
|----|------|------|------|
| piano_main | 80 Hz | 14 kHz | 主清晰度 |
| lake_lap | 100 Hz | 8 kHz | 勿抢 piano 中频 |
| rowing_distant | 120 Hz | 6 kHz | 远景 |
| bird_high | 1 kHz | 16 kHz | 留 air |
| bird_low | 150 Hz | 2.5 kHz | 与 high 分离 |

**主轨总线**

- ReaLimit ceiling **-1.5 dBTP**  
- Loudness Meter 目标：**Integrated -16 ~ -14 LUFS**（专注向，略高于纯 ASMR 雨声）  
- 可选：极轻 stereo width 仅用于 L2（105–110%），钢琴保持 mono-compatible 中心  

---

## 与画面的关系

| 视觉 | 音频 |
|------|------|
| 开阔湖面、慢镜头 | L2a 细浪 + L2b 远划船 |
| 近景树叶（若用） | 不加叶声，避免抢钢琴 |
| 无雨 | **禁止** 雨层 |
| 60 fps 慢水 | 划船节奏宜 **慢**，勿快划竞技感 |

VisualDesign 机位示例：CN-128 西湖俯瞰、千岛湖类 **清晰湖景** 封面 / loop。

---

## 检查清单

- [ ] 钢琴 loop 5 min+ 无缝，3 h 跳听无断点感  
- [ ] 划船远、慢，不盖过旋律  
- [ ] 高频鸟 ≥12 min 才一声；低频鸟 ≥25 min  
- [ ] 高低频鸟不同分钟  
- [ ] LUFS-I **-16 ~ -14**，TP ≤ **-1.5 dB**  
- [ ] 无雷、无雨、无 motorboat、无人声  
- [ ] 1 h 连续听不烦、不催眠（与 sleep 雨声区分）  

---

## 导出

```bash
# Reaper → output/lake_focus_bgm.wav（3 h）
# 若有视频：
./scripts/export_mp4.sh \
  -v "Audio Files/lake_loop_video.mp4" \
  -a output/lake_focus_bgm.wav \
  -o output/lake_focus_3h_4k.mp4 \
  --encoder nvenc
```

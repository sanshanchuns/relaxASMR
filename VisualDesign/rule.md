# Visual Design · 共用规范

---

## 视频循环

| 项目 | 规范 |
|------|------|
| 循环长度 | **5 s** 或 **10 s**，全片统一 |
| 长片 | Loop 至 **3 h** 或 **8 h**，与音频等长 |
| 机位 | 固定 · 禁 pan/zoom · **优先高处俯瞰**；中国选点 → [机位主表](./forest/china_mountain_ranges_viewpoints.md) |
| **封面 / 缩略图** | 真实机位构图 + **亮雨治愈光色** → [reference_workflow §2.1](./forest/reference_workflow.md#21-asmr-封面--缩略图光色与视频-loop-区分) |
| 运动 | 雨丝、叶动、雾飘等微动，周期 ≤ loop 长度 |

---

## Reaper 合成（Reaper 7）

1. **Project settings → Advanced**：Limit project length = `3:00:00` 或 `8:00:00`
2. 视频 item → **F2 → Loop source** → 拖至工程全长
3. 音频轨按 SoundDesign 叠层，同样 Loop
4. **File → Render**，Bounds = Full project，勾选 Video

详见 SoundDesign 音频流程：[SoundDesign/README.md](../SoundDesign/README.md)。

---

## 文字选景三要素

选 [forest/regions/](./forest/regions/) 中条目时，确认：

1. **地区** — 生物群系与树种是否正确  
2. **季节** — 叶态、色彩、地面（雪 / 落叶 / 常绿）  
3. **时段** — 夜 / 黎明 / 黄昏 / 白天（光照与 SoundDesign 四时段一致）  
4. **机位** — 中国场景 **优先可俯瞰**；**先对攻略实景再出变体** → [reference_workflow.md](./forest/reference_workflow.md)

---

## 检查清单

- [ ] 地区 + 季节与文档条目一致  
- [ ] 机位为 **固定俯瞰**（或注明林下听点仅用于声场）  
- [ ] 5 s / 10 s 无缝 loop  
- [ ] 与对应 SoundDesign 雨势 / 时段匹配  
- [ ] Reaper 音视频同长渲染

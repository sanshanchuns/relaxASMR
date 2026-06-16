# ForestRainNight · Reaper 工程

```
ForestRainNight/
├── ForestRainNight.rpp
├── scripts/
│   ├── asmr_config.lua          # 轨号、时长、循环/随机规则
│   ├── asmr_setup_project.lua   # 一键：8h 循环 + L3/L4 随机
│   └── random_scatter_items.lua # 单轨手动随机（可选）
├── Audio Files/                 # 工程媒体（Reaper 生成）
└── README.md
```

Portable 路径示例：`E:\ReaperPortable\Reaper Saves\ForestRainNight\`

---

## 轨道分层

| 轨号 | 层级 | 内容 | 脚本 |
|------|------|------|------|
| 1 | — | Tracker Folder | 跳过 |
| **2–4** | **L1/L2** | 远雨、伞面、水坑 | **循环 8 h** |
| **5–7** | **L3/L4** | 闷雷、湿叶、蛙 | **随机 jitter** |

间隔见 `scripts/asmr_config.lua`。

**随机轨（5–7）**：每条轨上需先拖入 **一个** 有效 WAV sample（脚本会读取它的路径再随机复制）。若轨上只剩竖线占位、无波形，请先 **Ctrl+Z** 撤销或重新拖入素材后再跑脚本。

---

## 使用

1. 打开 `ForestRainNight.rpp`
2. **Actions → ReaScript: Load** →  
   `ForestRainNight/scripts/asmr_setup_project.lua`
3. 选 **是**（循环 + 随机）→ **Ctrl+S** → Render

脚本自动读取 **同目录** 的 `asmr_config.lua`。

详细日志同时输出到 **View → Reaper console**（`~` 键），便于排查某轨失败原因。

---

## 相关

- [SoundDesign · medium_rain/night/forest.md](../../SoundDesign/medium_rain/night/forest.md)
- [Reaper手册.md](../../Reaper手册.md)

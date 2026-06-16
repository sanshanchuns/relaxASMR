# StreamHeal · Reaper 工程

```
StreamHeal/
├── StreamHeal.rpp
├── scripts/
│   ├── asmr_config.lua          # 轨号、时长、循环规则
│   └── asmr_setup_project.lua   # 一键：3 h 循环
├── Audio Files/                 # 工程媒体（Reaper 生成）
└── README.md
```

---

## 轨道

| 轨号 | 名称 | 内容 | 脚本 |
|------|------|------|------|
| **1** | **bgm_main** | 主 BGM | **循环 3 h** |
| **2** | **video** | 背景视频 | **循环 3 h** |

无随机层、无额外轨。

### 响度（油管 ASMR 溪流）

| 项 | 设置 |
|----|------|
| `bgm_main` 推子 | **+21 dB**（`VOLPAN ≈ 11.22`） |
| 主轨 FX | **ReaLimit** ceiling **-1.5 dB** + **Loudness Meter** |
| 目标 | Integrated **-18 ~ -16 LUFS**，True Peak **≤ -1.5 dBTP** |

导出后可用 ffmpeg 验证：

```bash
ffmpeg -hide_banner -i output/stream_bgm.wav \
  -af loudnorm=I=-16:TP=-1.5:print_format=json -f null - 2>&1 \
  | grep -E "input_i|input_tp"
```

底噪偏大时，将 `bgm_main` 推子从 +21 dB 微降到 **+19 ~ +20 dB**。

---

## 使用

工程内 item 已预设 **LOOP 1 + LENGTH 10800 s（3 h）**，打开后应直接看到两条轨铺满 3 小时。

若更换素材或片段变短，再跑脚本：

1. 打开 `StreamHeal.rpp`，确认轨 1、轨 2 已拖入素材
2. **Actions → ReaScript: Load** → `StreamHeal/scripts/asmr_setup_project.lua`
3. 点 **确定** → **Ctrl+S** → Render

脚本读取同目录 `asmr_config.lua`。日志：**View → Reaper console**（`~` 键）。

**检查循环是否生效**：选中 item → **F2** → 勾选 **Loop source**；时间轴上 item 右缘应到 **3:00:00**。

---

## 配置

修改 `scripts/asmr_config.lua` 中的 `duration_hours` 可改为 8 h 等其它时长。

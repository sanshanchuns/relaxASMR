# benchmark

## 现状

**RS-PASS 自动打分脚本已移除。** 实测表明，基于 `theory.md` §四 的代理指标（响度、尖锐度、粗糙度等）**无法有效指导混音决策**，与爆款成品的听感差距较大。

本目录仅保留 [`theory.md`](theory.md) 作为**声学背景参考**（色噪声分类、LEV 包裹感、三层声景结构等），不再维护 `score.py` 及 Reaper/导出流水线中的打分集成。

## 后续方向：爆款声纹

混音质量评估将改为 **对标爆款样本的声纹指纹**：

- 从已验证的高播放 Rain/Lake 成品中提取频谱、动态、空间等特征
- 与当前渲染成品做相似度 / 距离对比
- 用「离爆款有多远」指导层能量、EQ、素材替换——而非 RS-PASS 百分制

（实现待建，目录规划：`benchmark/viral_fingerprint/` 或同级模块。）

## 人工评估

配方与成品仍可参考 [`design/rain_series/scoring_rubric.md`](../design/rain_series/scoring_rubric.md) 中的 **包裹感 / 安全感** 人工量表（§一–§四）。

# Rain 声源库工具

**单一性原则**：文件名命中 ≥3 类声源（雨/风/鸟/虫…）或含「混合/mix」等词 → **不入库**。见 `sound_purity.py`。

**填充优先级**：Boom → `before_backup` → Epidemic/Envato（每叶子目录上限 10 条）

```bash
python3 scripts/sound_effect/fill_rain_sound.py --audit-purity
python3 scripts/sound_effect/fill_rain_sound.py --purge-mixed
python3 scripts/sound_effect/fill_rain_sound.py --dedupe
python3 scripts/sound_effect/fill_rain_sound.py --relocate

python3 scripts/sound_effect/fill_rain_sound.py --from-boom
python3 scripts/sound_effect/fill_rain_sound.py --from-backup

# vegetation 各关键词：10 Epidemic + 10 Envato（独立计数，见 .store_sources.json）
python3 scripts/sound_effect/fill_rain_sound.py --vegetation-stores-dry-run
python3 scripts/sound_effect/fill_rain_sound.py --fill-vegetation-stores
python3 scripts/sound_effect/fill_rain_sound.py --from-stores --stores-source epidemic

# 完整重填
python3 scripts/sound_effect/fill_rain_sound.py --refill
```

单独下载脚本：`scripts/envato_audio/download.py` · `scripts/epidemic_audio/download.py`

"""「系列视频」流水线：种子图 → 同系列图片 → 5s loop 视频。

主题固定为：雨 + 打击物（叶片/水面）+ ASMR 感（打击感、水珠飞溅、水气）。

模块划分：

- ``prompts``：图生图（时间+主体+场景+风格）与图生视频（6 步公式）的提示词构造
- ``store``：批次目录与 ``batch.json`` 元数据读写
- ``image_gen``：调 agy Gemini 由种子图生成同系列图
- ``video_gen``：视频生成 provider 注册表（可热插拔：seedance / gemini / ffmpeg 占位）
"""

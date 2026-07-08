import sys
from pathlib import Path
sys.path.insert(0, str(Path(".").resolve()))
from scripts.video_upload.parse_youtube_md import parse_youtube_md

p = Path("/mnt/e/自然之声/待上传youtube/output_audio/MVI_6921_material.md")
print(parse_youtube_md(p))

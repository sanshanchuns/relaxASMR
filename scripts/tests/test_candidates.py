import sys
from pathlib import Path

num = "6921"
rpp_dir = Path("/home/leo/workspace/relaxASMR/Reaper/Projects/Rain")
material_dir = Path("/mnt/e/自然之声/待上传youtube/output_audio")

md_candidates = []
if material_dir.is_dir():
    md_candidates.extend(material_dir.glob(f"*{num}*.md"))
md_candidates.extend(rpp_dir.glob(f"*{num}*.md"))

print("Candidates found:")
for p in md_candidates:
    print(p)

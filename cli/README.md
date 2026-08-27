# cli/

项目专属 CLI 包（如 `elevenlabs_web`）。共享工具已迁至 workspace 根目录的 [`utils/`](../../utils/)：

- `agy` — Gemini 文本 / VLM / 出图
- `jimeng_web` — 即梦生图 / 生视频
- `shared` — Playwright 基座

入口调用 `ensure_utils_path()` / `ensure_cli_path()` / `ensure_project_paths()` 后，`import agy` 等保持不变。

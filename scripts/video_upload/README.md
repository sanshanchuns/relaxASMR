# YouTube 上传

使用 **YouTube Data API v3** 将子工程 `output/material/<mp4名>/` 中的成片与物料自动上传。

## 依赖

```bash
pip install -r scripts/video_upload/requirements.txt
```

## 凭据

支持两个 YouTube 账号（OAuth 客户端 JSON 与 token 分账号存放）：

| 账号 | 邮箱 | 凭据 | Token |
|------|------|------|-------|
| `leo`（默认） | ace.leo.zhu@gmail.com | `config/credentials_leo.json` | `config/token_leo.json` |
| `leo_usa` | ace.leo.zhu.usa@gmail.com | `config/credentials_leo_usa.json` | `config/token_leo_usa.json` |

1. [Google Cloud Console](https://console.cloud.google.com/) 创建项目，启用 **YouTube Data API v3**
2. 每个账号创建 **OAuth 2.0 客户端 ID**（桌面应用），下载 JSON 放到上表路径
3. 首次运行会打开浏览器授权；令牌缓存在对应 `token_*.json`（已 gitignore）

OAuth 测试用户需在 Cloud Console 的「OAuth 同意屏幕」中添加对应 Google 账号。

**WSL**：首次授权用 **Windows 浏览器**打开 Google 登录页（`explorer.exe` 传完整 URL，避免 `cmd start` 截断 `&` 参数）。授权回调走 `localhost`，WSL2 会自动转发。

## CLI

在仓库根目录：

```bash
./scripts/video_upload/upload.sh \
  Reaper/Projects/Rain/subprojects/MVI_6991/output/material/MVI_6991_3h_4k \
  --privacy unlisted --language en --account leo
```

`--account` 可选 `leo`（默认）或 `leo_usa`。

或：

```bash
PYTHONPATH=scripts python3 -m video_upload \
  Reaper/Projects/Rain/subprojects/MVI_6991/output/material/MVI_6991_3h_4k
```

## 读取的物料

| 文件 | 用途 |
|------|------|
| `youtube.md` | 标题、描述、Tags（由 `generate_youtube_material.py` 生成） |
| `thumbnail.jpg` | 上传后设为视频缩略图 |
| 上级 `output/<同名>.mp4` | 视频文件 |

上传成功后写入 `upload_record.json`（含 `video_id`、URL）。

**上传固定元数据**：分类 Travel & Events（19）、语言 English；字幕认证需在 Studio 手动勾选（API 不支持）。

## GUI

见 [`gui/README.md`](../../gui/README.md) 第 6 步「上传到 YouTube」。

文案模版参考：[`../video_export/material_ref/forest_rain.md`](../video_export/material_ref/forest_rain.md)

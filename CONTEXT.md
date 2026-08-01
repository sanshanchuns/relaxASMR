# CONTEXT：relaxASMR GUI — YouTube 数据分析 Tab

> 本文件是给后续会话/协作者快速恢复上下文用的压缩摘要，对应 `gui/app.py` 里
> 「工作流」之后新增的两个 Tab：**我的数据**、**爆款分析**。

## 需求背景

在原有 Tkinter 工作流 GUI（导入视频 → 选音 → 建 Reaper 工程 → 导出合成 → 上传
YouTube）基础上，新增两个数据分析 Tab（插在「工作流」和「视频素材库」之间）：

- **我的数据**：展示自己频道（ace.leo.zhu@gmail.com）的订阅数/总视频数，视频
  按 YouTube 播放列表（系列）分组、组内按播放量降序，宫格展示封面+标题；可对
  单个视频发起 LLM「优劣分析」（同时指出优点和不足，帮助改进）。
- **爆款分析**：关键词默认 `leaf rain`（输入框可自定义，逗号分隔多个），搜索
  同类 rain ASMR 爆款视频，按作者分组、组内按「日均播放量」（归一化，识别黑马）
  排序展示 Top 10；可对单个视频发起 LLM「优点分析」（借鉴同类爆款为什么火）；
  点击作者可查看频道信息（订阅数/注册时间/总观看数）。

两个 Tab 共同点：单击宫格预览、双击（或右侧「播放」按钮）用系统默认浏览器打开
播放（Tkinter 无法内嵌 YouTube 播放器）。

## 新增/修改文件一览

| 文件 | 作用 |
|---|---|
| `agy/client.py`, `agy/generate.py` | 扩展支持多模态图片输入（封面分析用）+ 新增 `log_fn` 回调把 LLM 调用日志转发到 GUI 日志区而不是打印到后台终端 |
| `gui/youtube_api.py` | YouTube Data API v3 封装：频道/播放列表/视频/搜索；`VideoInfo` 上有 `views_per_day()`/`growth_score()`（日均播放量归一化，用来识别黑马）、`relative_age_label()`（"1天前/1月前/1年前"）；`format_relative_time()` 独立工具函数 |
| `gui/youtube_cache.py` | 磁盘 TTL 缓存（API 响应）+ 缩略图下载缓存 |
| `gui/video_insight.py` | 调 `agy` LLM 分析视频：`analyze_video_success`（爆款分析用，只看优点，缓存 key `insight::{id}`）、`analyze_own_video`（我的数据用，优点+不足，缓存 key `own_insight::{id}`），共用 `_run_analysis` 内部实现 |
| `gui/youtube_grid_common.py` | 宫格渲染公共逻辑：`build_grid_cell`（含 `highlighted` 黄色高亮边框参数）、`mark_cell_analyzed`（分析完成后动态描黄边）、`bind_mousewheel_deep`（递归绑定滚轮，解决"必须在滚动条上才能滚"的问题） |
| `gui/youtube_preview_panel.py` | 通用预览区组件：上半区封面缩略图，下半区元数据/LLM 分析结果二选一（点「LLM 分析」立即切到分析结果，「查看元数据/查看分析结果」按钮切换） |
| `gui/my_channel_tab.py` | 「我的数据」Tab：只负责左侧宫格（占满整个左半边），预览面板由 `app.py` 外部传入 |
| `gui/competitor_tab.py` | 「爆款分析」Tab：关键词输入框、宫格+分组删除(✕)+黑马自动补充，预览面板同样外部传入 |
| `gui/app.py` | 接入两个 Tab；预览面板挂载在应用最外层 `right_frame`（而非各 Tab 内部再分栏），随左侧 Tab 切换显示/隐藏 |

## 关键设计 / 踩过的坑

1. **多模态 LLM 调用**：`agy/client.py` 的 `stream_generate`/`chat` 加了
   `images: list[tuple[mime_type, bytes]]` 参数，构造 Gemini 请求时把封面图按
   `inlineData` 加进 `parts`。

2. **LLM 日志要进 GUI 日志区**：`generate_text_via_agy_accounts` 新增
   `log_fn` 参数替换掉内部的 `print`，一路透传：`video_insight.py` →
   `youtube_preview_panel.py`（分析线程里传 `self._log`）。

3. **黑马识别**：YouTube Data API 拿不到"最近 30 天播放量"，用
   `views_per_day = view_count / max(days_since_published, 1)` 做归一化代理，
   `growth_score` 同理加权点赞/评论。「黑马优先级」额外用
   `views_per_day / sqrt(view_count+1)`，压低已经量级很大的老爆款。

4. **宫格滚轮只在滚动条上生效**：Tk 的 `<MouseWheel>` 不会像浏览器一样向上
   冒泡，只在最外层 canvas bind 不够，需要 `bind_mousewheel_deep()` 递归绑定
   宫格渲染出来的整棵子树。

5. **`tk.Label` 空图片时 width/height 是字符/行单位**：预览区缩略图标签必须
   用固定像素尺寸的 `Frame` 包裹 + `pack_propagate(False)` 锁定像素高度，否则
   空标签会被撑到几千像素高，把布局挤爆（一度导致宫格区域看起来是"空白"）。

6. **PanedWindow 分栏不是 1:1**：`ttk.PanedWindow` 的 `weight` 只影响后续
   缩放余量，首帧必须等窗口真正 map 出来后用 `sashpos()` 强制设一次
   （`_equalize_pane_once` / `_equalize_right_pane_once`，`<Configure>` 触发
   一次性校正后立刻 `unbind`，避免用户手动拖动分栏后被反复强制复位）。

7. **【重要坑】`ttk.PanedWindow` 的 pane 必须是它自己的直接子控件**：早期把
   两个 `YoutubePreviewPanel` 的 parent 设成了 `self.right_frame`（`right_pane`
   的父容器），虽然 `right_pane.insert()` 不报错、`panes()` 里也能看到这个
   widget，但**视觉上完全不显示**（右侧一片空白）。修复：把 `right_pane` 的
   创建提前到 `right_frame` 刚建好之后（原来在 `_build_ui` 快结束时才建），
   让两个预览面板能以 `right_pane` 为 parent 正确构造。**以后任何要塞进某个
   PanedWindow 的控件，必须现场检查 parent 是不是这个 PanedWindow 本身。**

8. **右侧预览区布局**：`app.py` 里 `right_pane`（VERTICAL PanedWindow）默认
   三等分「封面预览/视频预览/日志」（工作流用）；切到「我的数据/爆款分析」时，
   `_show_youtube_preview_panel()` 会 `forget()` 掉封面/视频预览两块，
   `insert()` 对应的 `YoutubePreviewPanel` 到位置 0（占上 2/3），日志始终保留
   在最下面（这样做 LLM 分析时依然能看到日志）；切回其它 Tab 时
   `_show_default_right_panels()` 还原。`_equalize_right_pane_once()` 需要
   按当前 pane 数量（2 或 3）分别处理 sash 位置。

9. **分组删除 + 黑马补充**（爆款分析）：抓取时候选池远大于首屏展示数量
   （首屏按 `growth_score` 展示前 10 位作者，其余进入"预备池"并按黑马优先级
   重排序）；每个分组标题栏右上角「✕」删除后，从预备池取下一个追加到底部，
   预备池为空时提示"没有更多预备黑马分组了，可点击刷新重新抓取"。

10. **已分析视频高亮**：`build_grid_cell(..., highlighted=bool(cached_insight(id)))`
    渲染时描黄边；`YoutubePreviewPanel` 新增 `on_analyzed` 回调
    （`set_on_analyzed()` 设置），分析成功后（判定依据：磁盘缓存里查得到，
    因为失败信息不会被缓存）通知宿主 Tab 调 `mark_cell_analyzed()` 实时点亮
    对应宫格，不需要刷新整页。

11. **「我的数据」数据信息本地缓存（加速冷启动）**：之前只有封面缩略图走
    `download_thumbnail` 磁盘缓存，频道概览/播放列表/每个系列的视频 ID/全部
    视频详情这些「数据信息」每次切到该 Tab 都会重新拉一遍 API（`my_channel_tab.py`
    `_load_bg`）。现在补了跟「爆款分析」Tab 同款的 `gui/youtube_cache.py`
    TTL 缓存（key `my_channel_data_v1`，24 小时）：`_fetch_data()` 优先读缓存，
    命中则不发任何 API 请求直接渲染；工具栏也仿照爆款分析拆成「刷新（重新抓取）」
    （`force=True`）和「使用缓存加载」（`force=False`）两个按钮，概览文案里加了
    「本地缓存/刚刚抓取 + N 分钟前抓取」提示。缓存内容：频道 `ChannelInfo` +
    `uploads_playlist_id` + 播放列表列表 + 全部视频详情 + 「播放列表 id → 视频 id
    列表」映射（不直接存 `playlist_video_map`，因为 value 是 `VideoInfo` 对象，
    存 id 列表再用 `all_videos` 重建，避免同一个视频的详情在缓存文件里重复出现
    在多个播放列表下）。

12. **爆款分析关键词持久化**：`gui/app.py` 里 `self._cfg["competitor_keywords"]`
    （复用已有的 `user_config.json` 机制，跟 `audio_library_selection` 等同一套）
    保存最近一次搜索用的关键词文本；构造 `CompetitorTab` 时通过
    `initial_keywords` 传入作为输入框默认值，并传 `on_keywords_changed` 回调
    （在 `refresh()`、输入框失焦 `<FocusOut>`、应用关闭 `_on_closing` 时调用）
    写回配置。因为宫格数据本身走的是 `_POOL_CACHE_KEY_PREFIX + 关键词` 的磁盘
    TTL 缓存（`cache_get`/`cache_set`，见坑 9），只要输入框恢复成上次的关键词，
    `on_tab_selected()` 触发的 `refresh(force=False)` 自然会命中同一份缓存——
    不需要额外的宫格缓存逻辑，只需让关键词本身持久化即可。

13. **爆款分析删除记录持久化**：`_on_delete_group()` 删除分组后仅改了内存状态，
    重启应用 / 重新抓取后 `_render()` 会重新按 `growth_score` 从候选池里选出
    Top 10，被删过的作者会原样再出现。修复：新增 `_DELETED_CACHE_KEY_PREFIX`
    （key 按当前关键词组合 `"|".join(keywords)` 区分，不设 TTL 永久存在），
    `_on_delete_group()` 里把 `channel_id` 加入 `self._deleted_channel_ids`
    并调 `_save_deleted_ids()` 落盘；`_render()` 里先 `_load_deleted_ids()`
    读回，再从排序好的 `order` 列表中把这些 id 过滤掉——这样首屏和预备池都不
    会再选中已删除的作者，除非换一组关键词（作用域天然隔离）或手动清空
    `gui/.cache/youtube/`。

14. **WSL 下浏览器打开 URL 不生效**：先后遇到两层坑，都在
    `scripts/video_upload/youtube_upload.py` 的 `open_browser_url()`：
    1) 最早用 `rundll32.exe url.dll,FileProtocolHandler <url>` 走 Shell 协议
       关联打开默认浏览器，实测"进程启动但没有真正打开新标签页"；改成直接
       调起 `chrome.exe`/`msedge.exe` 本体、把 URL 当命令行参数传入
       （`_find_wsl_browser_exe()` 按系统级安装路径 →
       `/mnt/c/Users/*/AppData/Local/...` 按用户安装路径的顺序探测），
       让浏览器自带的单实例机制去转发。
    2) 改完后发现这台机器上 Chrome 配了多个个人资料（本机三个：Default→
       ace.leo.zhu@gmail.com、Profile 1→...usa@gmail.com、Profile 3→
       ...japan@gmail.com）且开着「在 Chrome 启动时显示」个人资料选择器；
       裸调 `chrome.exe <url>` 冷启动时（当时没有任何可见浏览器窗口，只有
       后台常驻的 chrome.exe 辅助进程）会先卡在「谁在使用 Chrome？」选择页，
       URL 根本没打开，看起来就是"新开一个空 chrome 就没有然后了"。
       修复：新增 `_find_wsl_chrome_profile_dir()`，读 Chrome 的
       `Local State`（`/mnt/c/Users/*/AppData/Local/Google/Chrome/User Data/
       Local State` 里 `profile.info_cache`，按文件 mtime 选最新那份）按登录
       邮箱（`_OWN_CHROME_ACCOUNT_EMAIL = "ace.leo.zhu@gmail.com"`，跟
       `gui/youtube_api.py` 的 `OWN_ACCOUNT_EMAIL` 是同一个账号）反查到本地
       profile 文件夹名（这台机器上是 `"Default"`），调用时额外带上
       `--profile-directory=Default` 跳过选择页——已用真实 `subprocess.Popen`
       调用验证过：同一个已存在的 Chrome 窗口（同 PID）标题栏直接变成了目标
       视频标题，确认是真的复用已有窗口开了新标签页，不是又开一个新窗口。
       找不到 Chrome 的 `Local State` / 邮箱不匹配时 `profile_dir` 为
       `None`，退化成不带 `--profile-directory` 直接调（跟第 1 层修复前一致，
       不会比之前更差）；`_find_wsl_browser_exe()` 完全找不到浏览器可执行
       文件才退回最早的 rundll32 → PowerShell `Start-Process` 链路兜底。
       `gui/youtube_preview_panel.py` 的「在浏览器中播放/打开频道」和
       `gui/competitor_tab.py` 的「查看作者频道」都是通过它统一调用的，一处
       修复两处生效。**注意**：GUI 是长驻进程，改完这个文件后需要重启
       `gui/app.py` 才会用上新逻辑，不会热更新。

## 当前状态

以上功能均已实现；坑 14 已经在 WSL shell 里用真实 `subprocess.Popen` 调用
`open_browser_url()` 验证成功（能看到已存在的 Chrome 窗口标题栏变成目标
视频标题，证明真的复用窗口开了新标签页），但还没有通过重启后的真实 GUI 点击
按钮做端到端验证，理论上应该一致（走的是同一个函数），如果重启 GUI 后还有
问题，需要用户反馈截图/现象再排查。其余功能均做过真实 Tk 实例的集成测试
（构造 `RelaxAsmrApp`、模拟切换 Tab、模拟点击宫格/LLM分析/切换元数据-分析
结果）。

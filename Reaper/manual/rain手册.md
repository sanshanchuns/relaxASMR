# RAIN 中文用户手册（V1.0）
## 第一章 前言
### 1.1 什么是 RAIN？
感谢您选择 **RAIN**！
RAIN 是一款专门用于**生成真实降雨环境声**的音频插件，可帮助您快速创建具有沉浸感的雨声氛围，适用于电影、游戏、音乐、ASMR、环境音设计等各种音频制作项目。
与传统依赖大量录音素材进行叠加（Layer）的方式不同，RAIN 采用了先进的**声音合成（Synthesis）**技术来模拟降雨过程，因此能够突破真实录音所受的各种限制，例如：
* 不受天气条件限制
* 不受录音环境限制
* 不需要维护庞大的雨声素材库
* 可以实时生成各种不同风格的雨声
借助 RAIN，您可以轻松制作各种雨景，例如：
* 毛毛细雨（Drizzle）
* 普通降雨（Rain）
* 暴雨（Heavy Rain）
* 雷暴雨（Storm）
* 各种具有空间层次感的环境雨声
无需翻找和试听大量雨声录音，只需调整几个参数，即可快速得到理想效果。
## 产品特色
### 多层雨声生成（Diverse Rain Layers）
RAIN 将雨声划分为三个独立层次：
* **Distant（远景层）**
  * 模拟远处整体降雨氛围
* **Space（空间层）**
  * 模拟环境反射与空间特性
* **Close（近景层）**
  * 模拟近距离雨滴落在各种材质上的声音
三个层次共同组成完整且具有空间感的雨声场景。
### 丰富的预设与高度可调性
软件提供大量预设雨景（Scenes），可一键切换。
同时，还可以进一步调整：
* Width（宽度）
* Pan（声像）
* Mass（质量感）
* Strength（力度）
* Presence（存在感）
快速创建属于自己的雨声风格。
### 雨量与强度控制
通过二维 XY 控制器，可以同时调整：
* **Density（密度）**
  * 单位时间内雨滴数量
* **Intensity（强度）**
  * 雨滴冲击力度
两项参数共同决定降雨规模与听感。
### 湿度与距离感
另外一个 XY 控制器用于控制：
* Wetness（湿润程度）
* Distance（距离感）
从而改变整个雨景的真实感和空间层次。
# 1.2 系统要求
## Windows
* Windows 8（64 位）或更高版本
* 8 GB 内存
* 较新的 Intel Core i5 或同等级处理器
## macOS
* macOS 10.13 或更高版本
* Apple Silicon（M 系列）或 Intel Core i5
* 8 GB 内存
# 1.3 安装
下载 RAIN 安装程序后：
1. 双击安装程序。
2. 按照安装向导完成安装。
3. 安装结束后即可在支持的 DAW 中使用。
安装完成后，用户手册默认安装到以下位置：
**Windows**
```
C:\Program Files\BOOM Interactive\RAIN
```
**macOS**
```
/Applications/BOOM Interactive/RAIN
```
# 1.4 iLok 授权激活
RAIN 使用 **PACE iLok** 授权系统进行许可管理，因此首次使用前需要完成授权激活。
## 第一步：创建 iLok 账户
如果尚未拥有 iLok 账户，请前往 iLok 官方网站注册。
创建账户是免费的。
## 第二步：安装 iLok License Manager
下载安装 **iLok License Manager**。
该软件用于管理所有授权许可证。
## 第三步：获取激活码
购买完成后，BOOM 会发送：
* 下载链接
* 一组 30 位激活码（Activation Code）
例如：
```
1234-1234-1234-1234-1234-1234-1234-12
```
## 第四步：激活许可证
打开 **iLok License Manager**。
依次选择：
```
License
    ↓
Redeem Activation Code
```
或者点击右上角的 **Redeem Activation Code** 图标。
随后：
1. 粘贴完整激活码。
2. 选择授权位置（Activation Location）：
   * 当前电脑（Machine Authorization），或
   * iLok 2 / iLok 3 硬件加密狗。
3. 确认激活。
激活完成后，即可正常使用 RAIN。
## 常见问题
### 第一次启动会提示登录 iLok
这是正常现象。
首次运行 RAIN 时，需要登录 iLok 账户完成授权绑定。
### 插件没有出现在 DAW 中
如果第一次打开 DAW 时尚未完成授权，某些 DAW 可能会将 RAIN 加入**黑名单（Blacklist）**或**扫描失败列表（Failed to Scan）**。
通常按照以下步骤即可解决：
1. 打开 DAW 的插件黑名单。
2. 将 RAIN 从黑名单中移除。
3. 在 iLok License Manager 中完成授权。
4. 重新扫描插件，或重新启动 DAW。
## 第二章 快速开始（Quick Start）
RAIN 是一款**声音生成器（Sound Generator）**，它能够自行生成雨声，因此**无需 MIDI 输入，也无需任何音频输入**即可工作。只要将插件加载到 DAW 中，便可以立即开始播放雨声。
## 2.1 不同插件格式的使用方式
RAIN 提供多种插件格式，不同宿主软件中的表现略有区别。
### Audio Unit（AU）
在 macOS 上，AU 版本属于 **AU Generator（生成器）** 类型。
这种类型的插件即使没有任何输入信号，也不会停止音频处理，因此特别适合作为环境音发生器使用。
通常可以在宿主软件的 **Generators** 分类中找到。
### AAX（Pro Tools）
AAX 版本主要用于 **Pro Tools**。
在 Pro Tools 中：
* 位于 **Instruments（乐器）** 分类
* 可以插入普通音轨
* 无需输入音频即可产生声音
### VST3
VST3 版本兼容绝大多数 DAW。
虽然它在宿主中表现为**音频效果器（Effect）**，但实际上：
* 可以直接插在一个空音轨上
* 即使音轨没有任何输入
* 插件仍会自动生成雨声
因此，最简单的方法就是：
> 新建一个空白音轨 → 插入 RAIN → 即可开始播放。
## 2.2 开始使用
安装完成后：
1. 新建一个音轨。
2. 插入 **RAIN** 插件。
3. 默认情况下，插件会立即开始生成雨声，无需进行任何额外设置。
## 2.3 界面结构
RAIN 的图形界面共分为四个主要区域：
```
┌────────────────────────────────────────────┐
│                HEADER                      │
├──────────────┬──────────────┬──────────────┤
│              │              │              │
│ENVIRONMENT   │ RAINFALL     │  GLOBAL      │
│              │              │              │
└──────────────┴──────────────┴──────────────┘
```
其中：
### HEADER（顶部）
负责：
* 插件控制
* Scene（场景）管理
* 预设切换
### ENVIRONMENT（环境）
用于搭建整个雨景。
包括：
* Distant（远景）
* Space（空间）
* Close（近景）
决定雨声来自哪里、空间有多大、雨滴落在哪里。
### RAINFALL（降雨）
控制真正的雨。
包括：
* 雨量
* 雨势
* 湿润程度
* 距离
* 音色
### GLOBAL（全局）
负责整个插件最终输出。
包括：
* 高通滤波
* 低通滤波
* 音量
* Smart 模式
* 电平表
## 2.4 推荐工作流程
官方建议按以下顺序设计雨景：
### 第一步：选择 Scene（场景）
先从顶部的 **Scene** 浏览器中选择一个最接近目标效果的预设。
例如：
* 室外暴雨
* 小雨
* 森林
* 城市
### 第二步：调整 Environment
设置：
* Distant
* Space
* Close
决定：
* 雨来自哪里
* 空间大小
* 雨滴打在什么材质上
### 第三步：调整 Rainfall
继续微调：
* Distance（距离）
* Tonality（音色）
塑造雨声细节。
### 第四步：Global
最后调整：
* 输出音量
* High Pass
* Low Pass
使雨声更好地融入整体混音。
# 第三章 界面详解（UI Overview）
RAIN 的界面能够自动适配操作系统的外观主题。
如果系统使用：
* 浅色模式（Light Mode）
RAIN 会自动采用浅色界面。
如果系统使用：
* 深色模式（Dark Mode）
RAIN 也会自动切换为深色主题，无需手动设置。
# 3.1 Header（顶部区域）
Header 位于窗口顶部。
它主要承担以下功能：
* 显示插件信息
* 插件启用/旁路
* Scene 管理
* 预设浏览
## 3.1.1 Logo（标志）
点击左上角 **BOOM Logo** 后，可以查看：
* 当前 RAIN 版本号
* 官方支持联系方式
* 开发人员信息（Credits）
当需要确认版本或联系技术支持时，可从这里查看相关信息。
## 3.1.2 Bypass（旁路）
电源按钮用于控制插件是否启用。
开启（On）：
* RAIN 正常工作并输出雨声。
关闭（Off）：
* 插件停止处理和输出声音，相当于暂时禁用插件，但不会删除当前参数设置。
## 3.1.3 Scene（场景）
Scene 是 RAIN 中最重要的功能之一。
一个 **Scene** 可以理解为：
> 一整套雨景配置（完整预设）。
每个 Scene 都包含了：
* Environment 设置
* Rainfall 设置
* Global 设置
切换 Scene 后，整个雨景都会随之改变。
### 重命名 Scene
点击 Scene 名称旁边的**铅笔图标**，即可为当前场景重新命名，方便管理多个自定义雨景。
### 保存与加载 Scene
在 Scene 名称上**右键单击**，可以：
* 保存当前 Scene 到文件
* 从文件加载 Scene
这样可以方便地：
* 在不同工程之间共享雨景
* 建立自己的 Scene 库
* 备份重要的声音设计成果
* **3.2 Environment（环境层）**
* **3.3 Rainfall（降雨控制）**
* **3.4 Global（全局控制）**
# 3.2 Environment（环境层）
Environment（环境）用于构建整个雨景的空间结构。
RAIN 将完整的雨声拆分为三个层次：
```text
远处雨声（Distant）
        ↓
环境反射（Space）
        ↓
近处雨滴（Close）
```
三者共同组成最终听到的雨景。
## 3.2.1 Distant（远景层）
**Distant** 用于模拟远处的大面积降雨。
它决定了：
* 雨是否来自远方
* 空间是否开阔
* 整个环境是否具有氛围感
可以理解成：
> **整个世界正在下雨。**
这是塑造"天气感"最重要的一层。
RAIN 内置 **20 种远景雨声风格**，例如：
* Airy Breeze（空气感微风）
* Broadband Shower（宽频阵雨）
* Warm Buzz（温暖的背景嗡鸣）
每种风格都代表一种不同的大环境雨声。
### 两种编辑模式
Distant 提供两种调节方式。
### Normal（普通模式）
普通模式仅提供两个参数：
#### Width（宽度）
控制立体声宽度。
数值越大：
* 声场越宽
* 环绕感越强
数值越小：
* 更集中
* 更靠近中间。
#### Pan（声像）
控制左右位置。
例如：
* 左侧树林
* 右侧山谷
* 一侧天空降雨
都可以通过 Pan 调整。
### Advanced（高级模式）
高级模式增加三个参数。
#### Mass（质量感）
控制雨层整体厚重程度。
增加后：
* 更厚
* 更饱满
* 更像大片雨幕
降低后：
* 更轻盈
* 更透明
* 更适合毛毛雨。
#### Strength（力度）
控制远景雨声的能量。
提高后：
* 风暴感增强
* 冲击力更强
降低后：
* 更柔和
* 更平静。
#### Presence（存在感）
控制远景层是否突出。
提高：
远处雨声更明显。
降低：
远景退到背景。
这一参数十分适合控制"天气存在感"。
## 3.2.2 Space（空间层）
Space 层负责模拟：
> 雨声与周围环境发生作用后的声音。
它不是雨滴本身，而是：
* 建筑反射
* 地面反射
* 环境共鸣
* 空间特征
它决定：
> "这是在哪里下雨？"
RAIN 内置 **15 种空间环境**，例如：
* Street Tarmac（柏油马路）
* Metal Tanks（金属容器）
* Wood Deck（木质平台）
不同环境会产生完全不同的听感。
### Width（宽度）
控制空间层立体声宽度。
例如：
树林通常可以较宽。
室内房间则可以较窄。
### Pan（声像）
控制整个环境偏向左侧还是右侧。
### Blend（混合）
这是 Space 层的重要参数。
Blend 用来控制：
**Distant 与 Space 的比例。**
例如：
Blend 偏向 Distant：
```
远景 ↑↑↑
空间 ↑
```
更像：
远处正在下雨。
Blend 偏向 Space：
```
远景 ↑
空间 ↑↑↑
```
更强调：
当前环境的反射。
对于室内、屋檐、街道等环境，通常需要适当提高 Space 的比例。
## 3.2.3 Close（近景层）
Close 层负责模拟：
> **雨滴真正落在物体表面的声音。**
这是整个插件中最具细节的一层。
例如：
* 窗户
* 木板
* 水泥地
* 铁皮屋顶
* 树叶
都属于 Close Layer。
RAIN 提供 **20 种近景材质**，例如：
* Glass Roof（玻璃屋顶）
* Concrete（混凝土）
* Wood Thin（薄木板）
等等。
### Width（宽度）
控制近景雨滴分布范围。
宽：
雨滴覆盖整个画面。
窄：
雨滴集中在中央。
### Pan（声像）
控制雨滴偏向左侧还是右侧。
例如：
窗户左边下雨。
### Drops（雨滴数量）
Drops 用来控制：
> **近距离雨滴数量。**
增加：
```
滴滴滴滴滴滴……
```
更加密集。
减少：
```
滴……
```
更安静、更稀疏。
Drops 不会改变暴雨程度，而是改变近景雨滴出现频率。
## 使用技巧（官方建议）
### 技巧一：多尝试 Distant
官方建议经常点击：
```
← Previous
Next →
```
快速切换不同 Distant 类型。
虽然参数相同，
但不同远景模型会极大改变：
* 深度
* 空间
* 包裹感
找到最适合其它 Layer 的组合。
### 技巧二：尝试不同 Space 环境
例如：
**Soft Foliage Flutter**
能够增加：
* 树叶细节
* 空间层次
* 环境复杂度
对于森林雨景十分有效。
# 3.3 Rainfall（降雨控制）
**Rainfall** 是 RAIN 的核心控制区域。
如果说：
* **Environment** 决定"雨在哪里下"
* 那么 **Rainfall** 就决定"雨下成什么样"
这里主要控制：
* 雨量
* 雨势
* 湿润程度
* 距离感
* 音色
整个区域采用 **XY Matrix（二维矩阵）** 控制方式，可以同时调节两个参数，因此操作速度非常快。
# 3.3.1 Intensity / Density（强度 / 密度）
第一个 XY 控制器用于调整：
```text
        Intensity ↑
                  │
Density ──────────┘
```
## Density（密度）
Density 表示：
> **单位时间内有多少雨滴。**
也就是：
**雨滴数量。**
例如：
### Density 很低
```text
滴……
    滴……
        滴……
```
只有少量雨滴。
适合：
* 毛毛雨
* 零星降雨
* 雨刚开始
### Density 很高
```text
滴滴滴滴滴滴滴滴滴滴滴
```
大量雨滴同时落下。
适合：
* 暴雨
* 雷雨
* 狂风暴雨
## Intensity（强度）
Intensity 表示：
> **每一滴雨的力量。**
它影响：
* 冲击力
* 力度
* 气势
而不是数量。
例如：
同样都是 100 滴雨：
低 Intensity：
```text
轻轻落下
```
高 Intensity：
```text
狠狠砸下
```
所以：
> **Density = 下多少滴雨**
> **Intensity = 每滴雨有多重**
二者组合后，可以产生大量不同风格的降雨。
## 推荐组合
### 毛毛雨
```text
Density   ★★☆☆☆
Intensity ★☆☆☆☆
```
### 普通小雨
```text
Density   ★★★☆☆
Intensity ★★☆☆☆
```
### 中雨
```text
Density   ★★★★☆
Intensity ★★★☆☆
```
### 暴雨
```text
Density   ★★★★★
Intensity ★★★★★
```
### 夏季雷阵雨
```text
Density   ★★★★☆
Intensity ★★★★★
```
这种组合通常比单纯提高 Density 更自然。
# 3.3.2 Wetness / Distance（湿润度 / 距离）
第二个 XY 控制器负责塑造空间感。
```text
       Wetness ↑
                │
Distance────────┘
```
## Wetness（湿润度）
Wetness 表示：
> **整个环境有多湿。**
它影响的是：
* 水分感
* 潮湿感
* 雨后的质感
而不仅仅是音量。
提高 Wetness 后：
你会感觉：
* 地面已经湿透
* 水花更多
* 环境更加潮湿
降低 Wetness：
更像：
* 刚开始下雨
* 地面仍较干燥
### 推荐用途
室内窗边：
建议：
```text
Wetness ★★★☆☆
```
树林：
```text
★★★★☆
```
暴雨：
```text
★★★★★
```
## Distance（距离）
Distance 控制：
> **整个雨景距离听众有多远。**
官方特别说明：
Distance 实际上是一个**混合控制器（Blend）**，用于控制：
* 上方两层（Distant + Space）
* 与下方 Close Layer
之间的比例。
### Distance 较远
更强调：
* Distant
* Space
例如：
```text
远山
树林
城市背景
```
听者像站在远处。
### Distance 较近
Close Layer 更明显。
例如：
```text
窗边
屋檐
雨棚
```
仿佛雨滴就在耳边。
### 与 Blend 的关系
需要注意：
Environment 中的 **Blend**：
控制：
```text
Distant ←→ Space
```
Rainfall 中的 **Distance**：
控制：
```text
(Distant + Space)
        ↓
      Close
```
两者共同决定空间深度。
# 3.3.3 Tonality（音色）
Tonality 用于进一步调整：
雨声的整体音色。
包括三个参数：
* Mass
* Strength
* Presence
它们共同决定：
* 声音厚度
* 清晰度
* 存在感
这些参数在高级模式下也会出现在 Distant Layer 中。
# 官方小技巧
调整 Matrix 参数时：
点击任意：
* Slider（滑块）
* Knob（旋钮）
然后直接使用键盘：
```text
↑
↓
方向键
```
即可进行细微调整。
这样能够获得比鼠标拖动更精确的控制。
# 3.4 Global（全局控制）
Global 区域负责：
> **整个雨景最终输出。**
所有声音最终都会经过这里。
包括：
* High Pass
* Low Pass
* Volume
* Smart
* Level Meter
## 3.4.1 High Pass / Low Pass（高通 / 低通滤波）
这两个滤波器主要用于：
让雨声更容易融入混音。
### High Pass（高通）
去除低频。
效果：
* 更轻
* 更细
* 更通透
适合：
* 毛毛雨
* 细雨
* 背景雨声
### Low Pass（低通）
去除高频。
效果：
* 更柔和
* 更闷
* 更有隔墙感
适合：
* 室内听雨
* 隔窗听雨
* 夜晚雨景
官方建议：
利用 Low Pass 可以快速制作自然的**室内雨景**。
## 3.4.2 Volume（输出音量）
用于控制：
RAIN 的最终输出电平。
插件内部集成了一个**透明限制器（Transparent Limiter）**。
它主要用于限制：
Close Layer 中雨滴瞬态过大的情况，避免突然出现过高的峰值。
因此，即使提高 Close Drops，也能保持整体输出相对稳定。
## 3.4.3 Smart（智能动态）
Smart 默认开启。
它的作用是：
> 自动管理不同雨势之间的动态范围。
例如：
毛毛雨：
```
-25 dB
```
暴雨：
```
-2 dB
```
如果关闭 Smart：
两者之间可能会出现非常大的音量差。
开启后：
RAIN 会自动压缩这种差异，使不同强度的雨声都保持较为稳定的输出，更方便直接用于混音。
如果你希望保留真实的动态变化，可以关闭 Smart，但需要注意调整输出电平，以避免暴雨场景音量过大。
## 3.4.4 Level Meter（电平表）
界面底部提供一个输出电平表，用于监视最终信号。
刻度范围为：
* **顶部：0 dB**
* **中间：-24 dB**
* **底部：-48 dB**
建议在调节参数时观察电平，尽量避免长时间接近或超过 0 dB，以获得更稳定的输出。
# 第四章 使用案例（Use Cases）
本章介绍如何利用 RAIN 快速搭建不同类型的雨景。官方并未提供固定参数，而是通过几个典型案例说明各参数的组合思路，帮助用户理解如何设计符合不同场景的降雨环境。
# 案例一：远处正在下雨
目标：
> 听众并不站在雨中，而是能够感知远方正在下雨。
例如：
* 远山
* 山谷
* 森林深处
* 城市远景
官方建议：
### Environment
提高：
* **Distant（远景层）**
降低：
* **Close（近景层）**
使远景层成为主体。
### Rainfall
建议：
```text
Distance  ↑↑↑↑
```
让整体雨景离听众更远。
同时：
```text
Wetness ↓
```
避免近距离水花声。
### Global
保持：
* Smart 开启
无需增加过多高频。
这样得到的是：
> **一种"天气正在发生"的感觉。**
而不是：
> **雨滴就在耳边。**
## 推荐用途
适合：
* 游戏开放世界
* 电影环境铺垫
* 城市远景
* 森林环境声
# 案例二：站在屋檐下避雨
目标：
听众位于：
* 屋檐
* 阳台
* 门口
雨滴距离耳朵很近。
官方建议：
### Environment
提高：
* Close
选择：
* 木板
* 金属屋顶
* 玻璃
等材质。
这样可以突出：
雨滴敲击不同表面的声音。
### Rainfall
建议：
```text
Distance ↓
```
让雨滴靠近听众。
适当增加：
```text
Wetness ↑
```
增强潮湿氛围。
### Close
提高：
```text
Drops ↑
```
获得更多近距离细节。
## 推荐用途
适合：
* ASMR
* 第一人称游戏
* 屋檐避雨
* 露营帐篷
* 公交站
* 咖啡馆窗边
# 案例三：营造更真实的空间感
官方特别建议：
不要只修改：
```text
Intensity
```
因为：
现实中的雨景，
不仅仅只有：
> 下得更大。
而是：
* 空间改变
* 地面改变
* 材质改变
* 距离改变
因此建议：
同时尝试：
* 不同 Distant
* 不同 Space
* 不同 Close
三层组合。
很多时候：
更换一种 Environment，
比单纯调节雨量，
更容易得到真实自然的雨景。
# 官方建议
官方建议多使用：
```text
← Previous
Next →
```
浏览所有 Environment 类型。
因为：
同样都是：
```text
Heavy Rain
```
不同环境下可能得到：
树林暴雨
↓
城市暴雨
↓
玻璃屋顶暴雨
↓
铁皮屋顶暴雨
听感完全不同。
# 实际工作流程（推荐）
综合整个手册，可以整理出一套高效的声音设计流程：
```text
① 选择 Scene
        │
        ▼
② 选择 Distant
（天气氛围）
        │
        ▼
③ 选择 Space
（空间环境）
        │
        ▼
④ 选择 Close
（雨滴材质）
        │
        ▼
⑤ 调整 Density
（雨量）
        │
        ▼
⑥ 调整 Intensity
（雨势）
        │
        ▼
⑦ 调整 Distance
（远近）
        │
        ▼
⑧ 调整 Wetness
（潮湿感）
        │
        ▼
⑨ 使用 High/Low Pass
融入整体混音
```
这个流程体现了 RAIN 的设计理念：**先构建环境，再塑造降雨，最后进行整体混音。**
# RAIN 参数速查表
| 模块           | 参数        | 作用            |
| ------------ | --------- | ------------- |
| **Distant**  | Width     | 调整远景声场宽度      |
|              | Pan       | 调整远景左右位置      |
|              | Mass      | 调整雨幕厚重感       |
|              | Strength  | 调整雨势能量        |
|              | Presence  | 调整远景存在感       |
| **Space**    | Width     | 调整空间宽度        |
|              | Pan       | 调整空间左右位置      |
|              | Blend     | 平衡远景与环境反射     |
| **Close**    | Width     | 调整近景覆盖范围      |
|              | Pan       | 调整近景位置        |
|              | Drops     | 调整近距离雨滴数量     |
| **Rainfall** | Density   | 雨滴密度（数量）      |
|              | Intensity | 雨滴强度（冲击力）     |
|              | Wetness   | 环境湿润程度        |
|              | Distance  | 调整整体远近感       |
|              | Tonality  | 调整整体音色        |
| **Global**   | High Pass | 去除低频          |
|              | Low Pass  | 去除高频          |
|              | Volume    | 最终输出音量        |
|              | Smart     | 自动平衡不同雨势的动态范围 |
|              | Meter     | 输出电平监视        |


----


【场景】
Init                    初始化

01.Big Leafy Symphony      大树叶雨声        13 + 06 + 05
02.Deluge On Metal Shelter 金属雨棚暴雨      
03.Downpour At Downspout   落水管暴雨
04.Downpour On Car Port    车棚暴雨
05.Dreamy Flora            梦幻花园          13 + 06 + 05
06.Drenched Lakeside Jetty 湖畔码头          07 + 06 + 18
07.Drips And Puddles       滴水水洼
08.Drop Ballet On The Porch 门廊滴雨
09.Drops On Plastic Shield 塑料雨棚
10.Gentle Avenue Drizzle   林荫细雨          09 + 06 + 02
11.Gentle Drops Of Autumn  秋日细雨          15 + 06 + 02
12.Glassy Shelter          玻璃雨棚
13.Humming Busstation      雨中公交站
14.Interior Car Shower     车内听雨
15.Leafy Rhythm Forest     森林叶雨          13 + 06 + 04
16.Metallic Canopy Madness 金属棚暴雨
17.Mild Urban Drizzle      城市小雨
18.Narrow Alleyway Dripping 小巷滴雨
19.Softest Urban Drizzle   极轻细雨          16 + 13 + 03
20.Soothing Flora Tickles  花草轻雨          02 + 06 + 04
21.Stirring Water Whirls   水面涟漪          15 + 06 + 17
22.Storming Balcony Patter 阳台暴雨
23.Urban Midnight Rain     午夜都市雨
24.Vibrant Wetland Flora   湿地雨林          13 + 06 + 04
25.Whispering Jungle Shower 雨林低语         07 + 05 + 04

----

【Distant】远景

01.Airy Breeze         空灵微风
02.Airy Flow           空灵气流
03.Balanced Flow       均衡气流
04.Balanced Sizzle     均衡沙沙
05.Breezy Hiss         微风嘶响
06.Broadband Shower    宽频阵雨
07.Cold Stream         寒流雨声
08.Dense Stream        密集雨流
09.Distant Veil        远方雨幕
10.Echo River          河谷回声
11.Expansive Shower    辽阔阵雨
12.Flowing Rumble      流动轰鸣
13.Forest Whisper      森林低语
14.Gentle Swish        轻柔沙响
15.Immersive Fuzz      沉浸雨幕
16.Slow Waterfall      缓瀑雨声
17.Spooky Whisper      幽暗低语
18.Strong Hiss         强烈嘶响
19.Thick Shower        浓密阵雨
20.Warm Buzz           温暖嗡鸣

【Space】空间

01.Building Canopy     楼宇雨棚
02.Building Gutter     建筑排水槽
03.Building Overflow   建筑溢水
04.Building Rooftops   楼顶雨声
05.Foliage Canopy      树冠
06.Foliage Dense       茂密树林
07.Inner Yard          庭院
08.Metal Tanks         金属储罐
09.Street Dense        密集街区
10.Street Drain        街道排水沟
11.Street Tarmac       柏油路面
12.Urban Alley         城市小巷
13.Walls Concrete      混凝土墙
14.Wood Deck           木平台
15.Workshop Yard       工坊院落

【Close】近景

01.Brick Diffuse      砖墙（漫反射）
02.Concrete           混凝土
03.Concrete Diffuse   混凝土（漫反射）
04.Foliage Lush       茂密植被
05.Foliage Yielding   稀疏植被
06.Glass Roof         玻璃屋顶
07.Glass Thin         薄玻璃
08.Glass Tonal        共振玻璃
09.Stone Echoing      回声石墙
10.Metal Diffuse      金属（漫反射）
11.Metal Roof         金属屋顶
12.Metal Thin         薄金属板
13.Metal Tonal        共振金属
14.Plastic Roof       塑料屋顶
15.Plastic Thin       薄塑料板
16.Plastic Tonal      共振塑料
17.Water              水面
18.Wood Roof          木屋顶
19.Wood Thin          薄木板
20.Wood Tonal         共振木材
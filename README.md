# QQ Bot（Python + NoneBot2 + NapCat）

这是一个基于 Python、NoneBot2、OneBot V11 和 NapCat 的 QQ 机器人项目，带可切换人格、长期记忆、流式语音回复和大肥鱼表情包。Bot 通过反向 WebSocket 接收 NapCat 的 QQ 事件，并在群聊、私聊中提供娱乐、管理、AI 和媒体处理功能。

## 1. 技术结构

```text
qqbot-python/
├─ bot.py                       # Bot 启动入口，初始化 NoneBot、适配器和插件
├─ app/                          # 业务层：AI、记忆、人格、语音、表情
│  ├─ ai_client.py              # AI 请求封装（OpenAI 兼容，默认 DeepSeek）
│  ├─ persona.py                # 内置人设 + data/personas/*.json 自定义人设
│  ├─ memory.py                 # 会话记忆、摘要压缩、长期事实
│  ├─ database.py               # SQLite 表结构
│  ├─ tts.py                    # edge-tts + Windows SAPI 语音合成
│  ├─ stickers.py               # 表情素材挑选与情绪归一化
│  ├─ sticker_fetch.py          # 同步「大肥鱼」表情包
│  └─ voice_mode.py             # 语音聊天模式开关
├─ tools/                        # 本地脚本：自检、人格蒸馏、表情同步
├─ plugins/                     # 所有功能插件，每个目录通常对应一个功能
│  ├─ ai_chat/                  # AI 对话主体：流式回复、记忆、语音、表情
│  ├─ ai_persona/               # 人格 / 记忆 / 语音 / 表情指令
│  ├─ avatar_roast/             # 头像锐评
│  ├─ content_roast/            # 文字、图片等内容锐评
│  ├─ bilibili/                 # B 站链接处理
│  ├─ blackjack/                # 多人 21 点
│  ├─ community/                # 群社区类功能
│  ├─ content_roast/            # 内容锐评
│  ├─ cp_pairing/               # 群内 CP 抽签
│  ├─ cultivation/              # 修仙系统
│  ├─ faq/                      # 固定问答和 Bot 自我介绍
│  ├─ fortune/                  # 今日运势
│  ├─ group_admin/              # 群管理：禁言、解禁、踢人、违禁词
│  ├─ group_events/             # 入群、退群等群事件
│  ├─ help/                     # 帮助菜单
│  ├─ meme/                     # 本地 Meme 梗图生成
│  ├─ moderation/               # 违禁内容检测
│  ├─ music/                    # 点歌和音乐卡片
│  ├─ poke_reaction/            # 戳一戳互动
│  ├─ recall_monitor/           # 撤回消息监听和管理员转发
│  ├─ reborn/                   # 投胎模拟器
│  ├─ roulette/                 # 六发左轮轮盘赌
│  ├─ sign_in/                  # 群签到
│  ├─ tarot/                    # 塔罗牌抽取和图片渲染
│  ├─ weather/                  # 天气查询
│  └─ ...                       # 其他已启用插件
├─ .env                        # 环境变量和 API 配置（不要提交 API Key）
└─ reademe.md                  # 本说明文档
```

插件相互独立。新增或删除插件时，通常只需要在 `plugins/` 下新增或移除对应目录；`bot.py` 会通过 `nonebot.load_plugins("plugins")` 自动加载。

## 2. 启动和连接

### 启动 Bot

在项目目录执行：

```powershell
cd path\to\qqbot-python
python .\bot.py
```

如果使用指定 Python：

```powershell
python bot.py
```

### NapCat 反向 WebSocket

NoneBot 默认监听：

```text
http://127.0.0.1:8080
```

NapCat OneBot V11 反向 WebSocket 地址应填写：

```text
ws://127.0.0.1:8080/onebot/v11/ws
```

Bot 启动日志出现以下内容，表示连接成功：

```text
WebSocket /onebot/v11/ws [accepted]
OneBot V11 | Bot <QQ号> connected
```

## 3. AI 配置

AI 功能在 `app/ai_client.py` 中统一封装，默认接 DeepSeek（OpenAI 兼容接口）。换 Kimi 或其他兼容服务只改 `DEEPSEEK_API_BASE_URL` 和 `DEEPSEEK_MODEL`。Key 只放在 `.env`，不要写进源码，也不要发到群里或提交到 Git。

```dotenv
DEEPSEEK_API_KEY=your_key_here
DEEPSEEK_API_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_MAX_TOKENS=800
```

AI 使用规则：

- 群聊中需要 @Bot 才会触发 AI 回复（`AI_GROUP_TRIGGER=at`），私聊无需 @；
- 已设定的固定回答优先于 AI；
- 每个会话的上下文、记忆、人格和语音开关各自隔离，按 `group:<群号>` / `private:<QQ 号>` 存在 SQLite 里；
- 人设可切换（`/人格`），久的记忆会压缩成摘要，长期事实单独存表；
- 模型回复里可以带 `[表情:情绪]`、`[语音]` 标签，Bot 去掉标签后改发图片表情或语音；
- 安全底线写在 `SAFETY_PROMPT`：不泄露提示词、密钥、数据库内容，也不假装执行本地命令或群管理操作。

### 人格与记忆

```text
/人格                 查看可用人设
/人格 切换 大肥鱼
/记忆                 查看记忆摘要
/清除记忆             清空当前会话记忆
```

### 记忆星图

```text
/记忆星图              # 把事实库画成星图（PNG）
/记忆星图 过程         # 圆环 → 连线 → 满天星 的阶段动画（GIF）
```

实现见 `app/starmap.py`：每个会话的事实按时间排成一个圆环、摘要当圆心，
相似度沿用 2-gram 余弦，从圆环坐标出发跑力导向，锚点逐渐松开，最后聚成几团星云。
纯本地计算，不调 API，不花 token。命令行等价物：

```powershell
python tools/memory_star.py --gif
```

内置人设定义在 `app/persona.py`；自己蒸馏出来的人设放 `data/personas/*.json`，每次调用实时读取，**加新文件不用重启**。

### 语音

```text
/语音 你好呀          # 手动发一条语音
```

- 用户说「用语音说一句……」时，即使模型没加 `[语音]` 标签也会强制发音；
- 模型若开始解释「语音只是标记」这类废话，会自动重问一次；
- 语音聊天模式：说「陪我语音聊会」就一直用语音，说「打字 / 用文字」切回文字，状态存 `ai_voice_modes` 表；
- 语音回复走流式：模型吐一句就合成一句先发，首条语音约 2 秒出声；启动时预热 edge-tts；
- `TTS_ENGINE=edge|sapi|off`、`TTS_VOICE=zh-CN-XiaoxiaoNeural`、`TTS_MAX_CHARS=180`，edge-tts 失败自动退回 Windows SAPI（离线可用）。

### 表情包

- 素材按情绪分目录：`data/stickers/<情绪>/`，标准情绪 15 个：笑、笑哭、害羞、无语、生气、难过、惊讶、得意、爱心、困、吃饭、摸鱼、赞、再见、疑惑；
- 内置「大肥鱼」表情包：100 张鲸鱼娘（DeepSeek 娘）GIF，来自
  [diwer/ai-biaoqingbao](https://github.com/diwer/ai-biaoqingbao)（非商业二创），
  按素材说明自动归档，文件名带 `dfy-` 前缀，挑图时优先用它们；
- 本地缺图时，回复里带 `[表情:xx]` 会自动后台同步整套（一个进程只同步一次）；
  `/找表情` 手动补缺，`/找表情 强制` 全部重下，`STICKER_AUTO_FETCH=false` 可关掉自动同步；
- `/表情` 看素材数量，`/表情 笑` 手动发一张；
- 表情素材本身不进 Git，`data/` 整个目录都在 `.gitignore` 里。

## 4. 功能和指令

### 基础问答和娱乐

| 功能 | 常用指令 | 说明 |
|---|---|---|
| 帮助 | `/帮助` | 查看功能菜单 |
| Bot 身份 | `你是谁`、`你是什么模型` | 返回固定身份介绍 |
| 一言 | `/一言` | 随机返回一句话，每次内容尽量不同 |
| 今日运势 | `/今日运势` | 生成当日运势 |
| 塔罗牌 | `/塔罗` | 抽取塔罗牌并生成图片，发送后清理临时文件 |
| 天气 | `/天气 城市` | 查询指定城市天气 |
| 签到 | `/签到` | 群内签到 |
| 修仙 | `/修仙` | 查看或推进修仙状态 |

### 游戏功能

#### 六发左轮轮盘赌

```text
/轮盘赌 多人
/轮盘赌 加入
/轮盘赌 开始
/轮盘赌 扣扳机
/轮盘赌 状态
/轮盘赌 退出
```

规则：每局 6 个弹巢中随机装 1 发子弹，玩家轮流扣扳机。中弹者在群聊中会被禁言 60 秒；Bot 没有群管理权限时，游戏仍会结束，但禁言可能失败。

单人模式：

```text
/轮盘赌 单人
/轮盘赌 扣扳机
```

#### 其他游戏

```text
/21点                 # 多人 21 点
/猜谜                 # 猜谜游戏
/成语接龙             # 成语接龙
/你画我猜             # 你画我猜
/猜歌名               # 猜歌名
```

#### 群内 CP 抽签

```text
/cp
/群内配对
/CP抽签
```

每个群每天只能抽取一次，Bot 会随机选出两名群成员并生成 CP 小故事。记录保存在 `plugins/cp_pairing/cp_history.json`，重启 Bot 后当天仍不会重复抽签。

#### 投胎模拟器

```text
/投胎
/reborn
/转世
/投胎模拟器
```

随机生成帝王、乞丐、猫、蟑螂、外星人、机器人等身世，并生成完整人生经历、转折和多种结局。

### Meme 梗图

```text
/meme 模板 文字
```

示例：

```text
/meme 哭泣猫猫 今天又是想辞职的一天
/meme 完美 这波操作稳了
/meme 举牌小人 请大家保持安静
```

查看模板：

```text
/meme 模板
/meme 模板列表
/meme list
/meme模板
/梗图模板
```

当前模板包括：哭泣猫猫、完美、神图、PornHub 标题图、举牌小人、熊猫人、狗头、震惊、经典和彩虹。生成图片发送后会自动删除临时文件。

Meme 功能依赖 Pillow：

```powershell
python -m pip install pillow
```

### 音乐和媒体

```text
/点歌 歌曲名
/点歌 歌手 歌曲名
```

支持按歌曲名、歌手或“歌手 + 歌曲名”搜索，并返回 QQ 音乐或网易云音乐结果。音乐卡片的实际显示效果取决于 NapCat 和 QQ 客户端支持情况。

B 站链接可在群内直接发送，Bot 会尝试解析并转发为视频。视频处理产生的临时文件在发送后清理；视频较大、链接受限或解析失败时会保留原链接提示。

### 群管理

群管理功能仅允许群主和其他管理员使用，Bot 自身也必须拥有对应权限。

```text
/ban @成员 分钟       # 禁言，支持分钟
/unban @成员          # 解除禁言
/ta @成员             # 踢出成员
```

群事件还包括：

- 新成员入群欢迎；
- 成员退群欢送；
- 违禁词检测；
- 群消息统计、发言排行榜和词云。

### 锐评

```text
/锐评 文字内容
/锐评头像
/锐评头像 @成员
```

支持私聊和群聊。头像或图片下载到临时目录进行处理，锐评完成后自动删除临时文件；风格为幽默、尖锐但不鼓励人身攻击。

### 戳一戳

戳 Bot 时会随机：

- 回复一条猫娘风格文字；或
- 调用 OneBot `send_poke` 反戳。

如果 NapCat 不支持反戳接口，会自动退回文字回复。

### 撤回消息监听

撤回监听会缓存近期消息。当群或好友撤回消息后，Bot 会将文字、图片、视频等内容转发给 `.env` 中配置的 Bot 管理员账号，转发完成后清理临时文件。缓存主要保存在内存中，不会长期保存完整消息。

## 5. 权限和安全

- 群管理 API 需要 Bot 为群主或管理员；
- 禁言、踢人前会检查操作者权限；
- AI API Key 只能放在本地环境变量或 `.env`；
- 不要把 `.env`、缓存文件和临时媒体提交到公开仓库；
- 处理头像、视频和撤回消息时尽量使用临时文件，发送后及时删除；
- AI 猫娘人设不会覆盖安全规则，也不会执行越权操作。

## 6. 常见日志

插件加载成功：

```text
Succeeded to load plugin "<plugin_name>" from "plugins.<plugin_name>"
```

OneBot 连接成功：

```text
OneBot V11 | Bot <QQ号> connected
```

收到群消息但没有回复时，先确认：

1. 是否加载了对应插件；
2. 命令前缀和空格是否正确；
3. 群管理功能中 Bot 是否有管理员权限；
4. AI 群聊是否 @ 了 Bot；
5. NapCat 是否保持反向 WebSocket 连接；
6. 是否安装了对应依赖（例如 Meme 功能需要 Pillow）。

## 7. 开发约定

- 每个功能优先放入独立的 `plugins/<功能名>/__init__.py`；
- 本地脚本放 `tools/`，例如 `python tools/loadcheck.py` 检查插件能否加载、
  `python tools/selfcheck.py` 做配置自检、`python tools/fetch_stickers.py` 同步表情包、
  `python tools/simulate_voice.py` 跑语音回归、`python tools/memory_star.py` 出记忆星图；
- 文件下载、图片渲染和视频处理完成后删除临时文件；
- 不在代码中硬编码 API Key；
- 新插件应使用独立 matcher，避免拦截其他插件事件；
- 修改后先执行语法检查，再重启 Bot 验证日志和实际消息响应。

# 微信视频号取证系统

基于 AScript + MCP + ADB 的自动化微信视频号侵权证据采集系统，支持一键搜索、视频录屏、截图 OCR、ASR 语音转写、引流标记检测与剧本比对。

---

## 环境依赖

### 1. 基础环境

| 依赖 | 版本/说明 | 用途 |
|------|----------|------|
| Python | 3.10+ | 后端运行环境 |
| Conda | 任意 | 推荐通过 `conda env -n zscq` 管理 |
| AScript | 最新版 IDE + 运行时 | Android 自动化控制（点击、滑动、截图） |
| ADB / scrcpy | v3.3+ | 底层设备控制、录屏、截图 |
| MCP Server | 配套 AScript MCP 服务 | 代码通过 `mcp` 库与 AScript 通信 |

### 2. Python 依赖

```bash
pip install mcp rapidfuzz pypinyin httpx pandas openpyxl python-docx
# 以及项目需要的其他包（如 PyMySQL、DBUtils、jinja2 等）
```

> **注意**：`ascript` 包**不是通过 pip 安装的**。它是 AScript IDE 自带的 Android 运行时模块，只能在 AScript IDE 或其配套环境中运行。代码里 `from ascript.android.action` 等导入在标准 Python 环境中会报错。

### 3. ASR 模型（本地离线）

本系统支持三级 ASR 后端：

| 后端 | 路径/配置 | 说明 |
|------|----------|------|
| **SenseVoice**（首选） | `D:\code\vscodeWorkDir\vosk\sherpa-onnx-sensevoice-zh-2024-07-17` | sherpa-onnx 封装，本地离线，准确率高 |
| **Paraformer**（兜底） | `D:\code\vscodeWorkDir\vosk\sherpa-onnx-paraformer-zh-2024-03-09` | sherpa-onnx 封装，本地离线 |
| **讯飞云**（可选） | `weixin/asr_xunfei.py` | 需要讯飞 API Key，云端转写 |

模型目录结构示例：

```
D:\code\vscodeWorkDir\vosk\
├── sherpa-onnx-sensevoice-zh-2024-07-17\
│   ├── model.int8.onnx
│   └── tokens.txt
├── sherpa-onnx-paraformer-zh-2024-03-09\
│   ├── model.onnx
│   └── tokens.txt
```

### 4. 手机环境

| 条件 | 设置 |
|------|------|
| USB 数据线连接 PC | 必须 |
| 开发者选项 → USB 调试 | 开启 |
| 无障碍服务 | 授权给 AScript |
| 微信 App 已安装 | 登录状态 |
| 屏幕常亮 | 建议关闭自动锁屏，避免中途黑屏 |
| 手机分辨率 | 脚本按 **1080×2400** 基准坐标缩放，支持其他分辨率自适应 |

---

## 项目结构

```
weixin/
├── core/                       # 核心采集管线
│   ├── main.py                 # 入口脚本
│   ├── collector.py            # 证据采集器
│   ├── navigator.py            # 页面导航
│   ├── video_monitor.py        # 视频监控与引流检测
│   ├── media_capture.py        # 录屏/音频控制
│   ├── scanner.py              # OCR 扫描与候选提取
│   └── store.py                # 证据持久化
│
├── asr/                        # 语音识别与剧本比对
│   ├── sensevoice.py           # SenseVoice ASR 后端（首选）
│   ├── paraformer.py           # Paraformer ASR 后端（兜底）
│   ├── xunfei.py               # 讯飞云 ASR 后端（可选）
│   ├── local_whisper.py        # faster-whisper ASR（本地）
│   └── script_matcher.py       # ASR 文本与剧本比对引擎
│
├── db/                         # 数据模型与数据库
│   ├── models.py               # 数据模型定义
│   ├── connection.py           # MySQL 连接池
│   └── mapping.py              # JSON → MySQL 字段映射
│
├── utils/                      # 通用工具
│   ├── text_quality.py         # OCR 文本质量评估
│   └── tap_recorder.py         # ADB 触控坐标录制
│
├── scripts/                    # 演示与辅助脚本
│   ├── search_demo.py          # 搜索演示
│   ├── record_asr_demo.py      # 录音+ASR 演示
│   ├── test_local_ocr.py       # 本地 OCR 测试
│   └── list_mcp_tools.py       # 列出 MCP 工具
│
├── step_tests/                 # 各模块独立测试脚本
│   ├── test_sensevoice_asr.py
│   ├── test_paraformer_asr.py
│   ├── test_script_matcher.py
│   └── ...
│
├── data/                       # 参考数据
│   ├── _script_raw.txt         # 原始剧本文本
│   └── 弃子归来震万城.doc
│
├── designs/                    # UI 设计原型
│   ├── asr_comparison.html
│   └── asr_match_design.html
│
├── docs/                       # 项目文档
│   ├── README.md               # 本文档
│   ├── CURRENT_FLOW.md         # 当前流程说明
│   ├── PLATFORM_SPEC.md        # 平台设计规范
│   └── MULTI_DEVICE_PLATFORM_SPEC.md
│
├── screenshots/                # 采集截图输出（.gitignore）
├── jsons/                      # 证据 JSON 输出（.gitignore）
├── media/                      # 录屏/音频临时文件（.gitignore）
├── run.bat                     # Windows 一键启动脚本
└── .gitignore
```

---

## 使用方式

### 方式一：Windows 一键启动（推荐）

```bash
# 进入 weixin 目录
cd weixin

# 默认运行（默认采集 2 个视频）
run.bat

# 指定采集视频数量
set WEIXIN_MAX_VIDEOS=5
run.bat

# 全量采集（不限制数量，遇到重复视频后自动停止）
set WEIXIN_MAX_VIDEOS=0
run.bat
```

### 方式二：命令行直接运行

```bash
cd weixin

# 激活 conda 环境
conda activate zscq

# 默认运行（默认采集 2 个视频）
python core/main.py

# 指定采集视频数量
set WEIXIN_MAX_VIDEOS=5
python core/main.py

# 全量采集（不限制数量，遇到重复视频后自动停止）
set WEIXIN_MAX_VIDEOS=0
python core/main.py
```

### 方式三：AScript IDE 内运行

1. 打开 **AScript IDE**（非 VS Code）
2. 打开项目 `weixin/`
3. 打开 `core/main.py` 或 `kuaishou_collect.py`
4. 按 **Ctrl + Shift + R** 或菜单 → **AScript: 运行**

> 适用于需要 AScript Android 运行时的场景（如 `ascript.android` 相关导入）。

---

## 环境变量配置

采集行为可通过以下环境变量控制：

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `WEIXIN_MAX_VIDEOS` | `2` | **采集视频数量上限**。`0` 表示全量采集（不限制，靠重复检测自动停止）。 |
| `WEIXIN_POST_EVIDENCE_HOLD_SECONDS` | `240` | 每条视频采集后停留等待时间（秒）。 |
| `WEIXIN_CAPTURE_METHOD` | `auto` | 录屏方式：`auto` / `adb` / `scrcpy`。 |
| `WEIXIN_PREFER_SCRCPY` | `True` | 是否优先使用 scrcpy 录屏。 |
| `WEIXIN_VERIFY_VIDEO_PAGE` | `False` | 是否启用视频播放页二次验证。 |
| `WEIXIN_WRITE_DB` | `False` | 是否将结果写入 MySQL 数据库。 |

**示例**：只采集 5 个视频、不录屏只截图：

```bash
set WEIXIN_MAX_VIDEOS=5
set WEIXIN_CAPTURE_METHOD=adb
conda run -n zscq python core/main.py
```

---

## 微信视频号取证流程

```
┌────────────────────────────────────────────────────────────┐
│  前置检查：ADB 连接 → 屏幕尺寸获取 → 微信前台确认           │
└────────────────────────┬───────────────────────────────────┘
                         ▼
┌────────────────────────────────────────────────────────────┐
│  1. 搜索关键词（输入框）                                    │
│  2. 切换到「视频」Tab                                      │
│  3. 点击左上角第一个视频                                    │
└────────────────────────┬───────────────────────────────────┘
                         ▼
┌────────────────────────────────────────────────────────────┐
│  视频播放页确认：                                           │
│    - 优先 UI 树节点识别                                     │
│    - 失败则 ADB 截图 + 底部布局识别（fallback）              │
└────────────────────────┬───────────────────────────────────┘
                         ▼
┌────────────────────────────────────────────────────────────┐
│  单条视频证据采集（循环执行）：                              │
│    ├─ ① 启动录屏（scrcpy --record）                         │
│    ├─ ② 播放页截图 + OCR（标题/点赞/评论等）                 │
│    ├─ ③ 引流标记检测（UI 树 / 截图分析）                     │
│    ├─ ④ 点击头像 → 博主资料卡截图                            │
│    ├─ ⑤ 资料卡「更多信息」页截图                             │
│    ├─ ⑥ 分享 → 复制链接（视频链接）                         │
│    ├─ ⑦ 保存 JSON 结果 + 同名 HTML 预览                     │
│    └─ ⑧ 停止录屏，保存视频文件                              │
└────────────────────────┬───────────────────────────────────┘
                         ▼
┌────────────────────────────────────────────────────────────┐
│  下一条视频：                                               │
│    - ADB 向上滑动（adb shell input swipe）                  │
│    - 确认新视频播放页                                        │
│    - 重复采集循环，直到达到 WEIXIN_MAX_VIDEOS 上限           │
└────────────────────────┬───────────────────────────────────┘
                         ▼
┌────────────────────────────────────────────────────────────┐
│  任务结束：                                                 │
│    - JSON 证据包落盘                                         │
│    - 可选：导入 MySQL（db_mapping.py）                        │
│    - 可选：ASR 转写 + 剧本比对（script_matcher.py）          │
└────────────────────────────────────────────────────────────┘
```

### 证据包内容

每条视频生成同名证据包，至少包含：

| 文件 | 说明 |
|------|------|
| `result_*.json` | 结构化证据数据（OCR 文本、数字、博主信息、链接） |
| `result_*.html` | 人工预览页面（截图画廊 + 结构化字段） |
| `screenshots/` | 播放页、博主资料卡、更多信息页、引流截图 |
| `record_*.mp4` | 播放页录屏（含视频画面 + 音频） |
| `audio_*.wav` | 录屏提取的音频（用于 ASR 转写） |
| `asr_*.txt` | ASR 转写文本（SenseVoice / Paraformer） |

### 视频标识符规则

`video_identifier` 不依赖分享链接，由以下稳定字段组合生成：
- 搜索词 + 视频标题 + 博主名称 + 视频号 ID + 引流标记文本 + 播放页截图 Hash

确保同一视频多次采集标识符一致，不同视频不混淆。

---

## 数据库（可选）

如需将证据导入 MySQL：

```python
# 配置数据库连接（db.py 或环境变量）
DB_HOST = "localhost"
DB_PORT = 3306
DB_USER = "root"
DB_PASSWORD = "xxx"
DB_NAME = "zscq"

# 运行导入
python db/mapping.py --json jsons/result_xxx.json
```

Schema 包含：候选基础信息、视频/博主/引流核心字段、截图列表、媒体录制字段、`captured_at` 时间戳。

---

## 注意事项

1. **AScript 环境隔离**：`core/main.py` 中的 `from ascript.android...` 只能在 AScript IDE 运行；标准 Python 环境会报 `ModuleNotFoundError`。`run.bat` 和 `python core/main.py` 执行的是不涉及 AScript 导入的分支逻辑。
2. **分辨率自适应**：所有点击坐标和裁剪区域基于 **1080×2400** 计算，通过 `get_phone_screen_size_via_adb()` 获取实际分辨率后自动缩放。
3. **分享链接复制**：当前「复制链接」步骤依赖 OCR 识别「复制」按钮位置，偶有偏差；系统内置 fallback 固定坐标点击兜底。
4. **屏幕常亮**：采集过程中若手机自动锁屏，会导致 ADB 截图/滑动失败。建议采集前关闭自动锁屏或保持屏幕常亮。

---

## 相关文档

- `CURRENT_FLOW.md` — 当前流程详细说明与已知问题
- `PLATFORM_SPEC.md` — 取证平台设计规范（UI/UX、状态机、聚合规则）
- `MULTI_DEVICE_PLATFORM_SPEC.md` — 多设备并发采集设计

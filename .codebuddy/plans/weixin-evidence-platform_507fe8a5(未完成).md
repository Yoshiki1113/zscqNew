---
name: weixin-evidence-platform
overview: 在 weixin/ 目录下新建 web/ 子项目，基于 FastAPI+Jinja2+ECharts 搭建微信视频号取证 Web 平台，实现首页（一键取证+前置检查）、任务运行页（实时日志）、结果列表页、证据详情页四个核心页面，复用现有 collector.py/store.py/db.py 取证底座。
design:
  architecture:
    framework: react
  styleKeywords:
    - 专业取证后台
    - 克制稳重
    - 深青绿主色
    - 卡片布局
    - 双栏证据详情
    - 终端风格日志
    - 状态胶囊标签
  fontSystem:
    fontFamily: PingFang SC, Microsoft YaHei
    heading:
      size: 24px
      weight: 700
    subheading:
      size: 16px
      weight: 600
    body:
      size: 14px
      weight: 400
  colorSystem:
    primary:
      - "#1a6b5f"
      - "#145249"
      - "#228a7a"
    background:
      - "#f5f6f8"
      - "#ffffff"
      - "#1e1e1e"
    text:
      - "#1a1a1a"
      - "#5a5a5a"
      - "#8a8a8a"
    functional:
      - "#d4532a"
      - "#2a9d4e"
      - "#d4a02a"
      - "#1a6b5f"
todos:
  - id: create-db-schema
    content: 使用 [skill:weixin-video-monitor] 查阅现有 db_mapping.py/models.py 接口，新增 tasks 和 review_results 建表 SQL，为 weixin_video_evidence 表添加 review_status 字段，新增 Task/ReviewResult dataclass
    status: pending
  - id: create-web-scaffold
    content: 创建 weixin/web/ 目录骨架：app.py FastAPI入口、config.py 配置、templates/base.html 基模板（导航+全局样式）、static/css/platform.css 全局样式
    status: pending
  - id: build-home-page
    content: 实现首页：services/checks.py 5项前置检查函数、routes/home.py 首页路由（GET页面+POST检查）、templates/home.html（表单+状态灯+一键取证按钮）、static/js/home.js 前端轮询交互
    status: pending
    dependencies:
      - create-web-scaffold
  - id: build-task-runner
    content: 实现 services/task_runner.py（包装 main.py 管线，通过 asyncio.Queue 推送日志）、routes/task.py（SSE日志流 + 任务页面）、templates/task.html（终端日志+截图区）、static/js/task.js（EventSource客户端）
    status: pending
    dependencies:
      - create-web-scaffold
      - create-db-schema
  - id: build-results-list
    content: 实现结果列表页：services/db_service.py 数据库查询封装、routes/results.py（列表+筛选API）、templates/results.html（卡片网格+筛选栏）、static/js/results.js（筛选交互）
    status: pending
    dependencies:
      - create-web-scaffold
      - create-db-schema
  - id: build-evidence-detail
    content: 实现证据详情页：routes/evidence.py（详情GET+复核POST）、templates/evidence.html（双栏：左字段+复核按钮，右录屏播放器+截图画廊+JSON）、复核状态变更记录操作人和时间
    status: pending
    dependencies:
      - create-web-scaffold
      - create-db-schema
      - build-results-list
  - id: integration-test
    content: 端到端集成测试：启动 FastAPI 服务，验证首页检查→发起任务→SSE日志→结果列表→证据详情→复核状态更新 全流程
    status: pending
    dependencies:
      - build-task-runner
      - build-evidence-detail
---

## 产品概述

基于 PLATFORM_SPEC.md 设计文档，在 `weixin/web/` 下搭建一个独立 FastAPI 取证 Web 平台。先支持微信视频号平台，后续可扩展其他平台。平台核心能力：一键发起取证任务、实时查看取证日志、按视频维度浏览采集结果、逐条查看证据详情并进行人工复核。

## 核心功能

### 首页（一键取证）

- 平台选择下拉框（初期仅微信视频号）
- 关键词输入框
- 5 项前置检查状态灯：USB连接、ADB可用、AScript可连接、录屏能力、存储目录可写。全部绿灯后一键取证按钮才可点击
- 一键取证按钮，点击后跳转到任务运行页

### 任务运行页（实时监控）

- 当前取证步骤文字提示
- 实时日志流（SSE 推送，终端风格滚动显示）
- 当前截图缩略图（最近一次截图预览）
- 录屏状态指示
- 失败时展示错误原因和重试按钮

### 结果列表页

- 卡片列表，每个卡片展示：博主名称、视频号ID、主体类型、企业全称、喜欢/收藏/转发/评论数、视频链接、复核状态标签（红侵权/绿白名单/黄不确定）
- 支持按博主名称、复核状态、时间范围筛选
- 点击卡片进入证据详情页

### 证据详情页

- 左栏：结构化字段（搜索词、博主名、视频号ID、企业全称、互动数据、引流标记、复核状态）+ 复核操作按钮
- 右栏：录屏播放器 + 截图画廊 + 原始JSON折叠区

## 技术栈

- **后端框架**：FastAPI + Uvicorn（Python 异步）
- **模板引擎**：Jinja2
- **实时通信**：SSE（Server-Sent Events，FastAPI 原生 StreamingResponse）
- **数据库**：MySQL 8.0 + pymysql（直连模式，复用现有 db.py 的 get_connection 模式）
- **前端**：原生 HTML/CSS/JS + ECharts（仅在需要图表时使用）
- **异步任务**：asyncio.create_task（取证流程在后台协程执行，与 Web 请求分离）
- **项目路径**：`weixin/web/` 独立子目录，复用 `weixin/` 下现有模块

## 实现方案

### 核心策略：Web 层封装 CLI 管线

不改动 `main.py`/`collector.py` 核心逻辑。Web 层通过以下方式与现有代码集成：

1. 导入现有函数：`from main import connect_device_auto_v2, search_keyword, run_on_phone`
2. 将 `main.py` 的 `run()` 函数逻辑拆解为可被 Web 调用的异步生成器，每步通过 `asyncio.Queue` 推送日志行
3. 前置检查独立为 `web/services/checks.py`，调用 adb 子进程和 MCP 探测

### 取证管线封装（`web/services/task_runner.py`）

创建一个 `TaskRunner` 类，包装 `main.py` 的取证流程：

- 接收关键词、环境配置
- 内部调用 `collector.collect_current_video()` 等现有函数
- 通过 `asyncio.Queue` 将每步日志推送给 SSE 消费者
- 取证完成后通过 `store.save_record()` 写入 JSON，通过 `db.insert_evidence_record()` 写入 MySQL
- 任务状态和日志存入 `tasks` 表

### SSE 日志推送

FastAPI 端点 `GET /api/tasks/{task_id}/stream` 返回 `StreamingResponse`，持续从 `asyncio.Queue` 读取日志行并写入 SSE 格式。前端使用 `EventSource` API 接收。

### 数据库扩展

在现有 `zscq` 库基础上新增 2 张表（通过 `db_mapping.py` 扩展）：

- **tasks**：管理取证任务生命周期（id, keyword, status, log_json, created_at 等）
- **review_results**：视频复核记录（id, evidence_row_id, status, reviewer, reviewed_at, notes）
- **weixin_video_evidence** 表新增字段：`review_status VARCHAR(16) DEFAULT '不确定'`，`video_identifier VARCHAR(64)`

### 前置检查实现

`web/services/checks.py` 提供 5 个检查函数：

1. **USB连接**：`adb devices` 检查是否有 device 状态设备
2. **ADB可用**：`adb shell echo ok` 返回值
3. **AScript连接**：MCP `connect_device` 调用是否成功
4. **录屏能力**：`scrcpy --version` + `ffmpeg -version` 是否存在
5. **存储目录**：`os.access(SCREENSHOT_DIR, os.W_OK)` + `os.access(JSONS_DIR, os.W_OK)`

### 性能考虑

- 取证任务为异步协程，不阻塞 Web 请求循环
- SSE 日志行采用批量发送（每 0.5s 或缓冲区满 10 条），避免频繁 I/O
- 结果列表分页查询（LIMIT/OFFSET），避免一次性加载全部记录
- 截图画廊使用缩略图 + 点击放大，减少首屏带宽

## 目录结构

```
weixin/web/
├── app.py                      # [NEW] FastAPI 应用入口，注册路由
├── config.py                   # [NEW] 全局配置（端口、DB参数、路径）
├── routes/
│   ├── home.py                 # [NEW] 首页路由（GET/POST 检查、发起任务）
│   ├── task.py                 # [NEW] 任务运行页路由（GET 页面 + SSE 日志流）
│   ├── results.py              # [NEW] 结果列表页路由（GET 列表 + 筛选）
│   └── evidence.py             # [NEW] 证据详情页路由（GET 详情 + POST 复核）
├── services/
│   ├── checks.py               # [NEW] 5项前置检查函数
│   ├── task_runner.py          # [NEW] 任务运行器（包装 main.py 管线 + Queue 日志）
│   └── db_service.py           # [NEW] Web 层数据库操作封装（查询/写入/复核）
├── templates/
│   ├── base.html               # [NEW] 基模板（导航栏、全局样式）
│   ├── home.html               # [NEW] 首页模板（表单+状态灯+按钮）
│   ├── task.html               # [NEW] 任务运行页模板（日志终端+截图区）
│   ├── results.html            # [NEW] 结果列表页模板（卡片网格+筛选）
│   └── evidence.html           # [NEW] 证据详情页模板（双栏布局）
├── static/
│   ├── css/
│   │   └── platform.css        # [NEW] 全局样式（深青绿主色、卡片、按钮、标签）
│   └── js/
│       ├── home.js              # [NEW] 首页交互（前置检查轮询、按钮状态）
│       ├── task.js              # [NEW] 任务页SSE客户端（日志滚动、截图预览）
│       └── results.js           # [NEW] 列表页筛选交互
└── weixin/                     # （现有目录，不动）
    ├── main.py                 # [MODIFY] 新增可选 async generator 模式供 web 调用
    ├── collector.py            # [不变]
    ├── db.py                   # [不变]
    ├── db_mapping.py           # [MODIFY] 新增 tasks/review_results 建表SQL
    ├── models.py               # [MODIFY] 新增 Task, ReviewResult dataclass
    └── store.py                # [不变]
```

## 关键代码结构

### TaskRunner 核心接口

```python
class TaskRunner:
    def __init__(self, keyword: str):
        self.keyword = keyword
        self.log_queue: asyncio.Queue = asyncio.Queue()
        self.status = "pending"  # pending/running/completed/failed
        self.current_step = ""

    async def run(self):
        """后台运行，逐步骤推送日志到 log_queue"""
        await self.log_queue.put("[系统] 开始取证任务...")
        # 1. 连接MCP + 设备
        # 2. 启动录屏片段
        # 3. 搜索关键词
        # 4. 点击第一个视频
        # 5. 循环采集（每步推日志）
        # 6. 完成后更新状态
```

### SSE 端点模式

```python
@router.get("/api/tasks/{task_id}/stream")
async def task_stream(task_id: str):
    async def event_generator():
        queue = get_task_queue(task_id)
        while True:
            line = await queue.get()
            yield f"data: {line}\n\n"
            if line.startswith("[完成]") or line.startswith("[失败]"):
                break
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

## 设计风格

采用"专业取证后台"风格——克制、稳重、信息密度适中。深青绿色系作为主色调，配合橙红色强调按钮和醒目的复核状态标签。页面布局以顶部固定导航+主内容区为主，证据详情页采用双栏布局（左字段、右媒体）。

## 页面设计

### 首页

- 顶部：平台标题"取证平台" + 导航链接（首页、结果列表）
- 中部左侧：表单区——平台选择下拉框、关键词输入、一键取证主按钮
- 中部右侧：5 项前置检查状态灯（圆形指示灯+标签），全部绿灯时按钮激活
- 底部：最近任务列表（简要表格）

### 任务运行页

- 顶部：当前步骤大字提示 + 进度状态
- 中部：终端风格日志区（深色背景、等宽字体、自动滚动到底部）
- 右侧边栏：当前截图缩略图、录屏状态指示
- 底部：失败时显示红色错误框+重试按钮

### 结果列表页

- 顶部：筛选栏（博主搜索框、状态下拉、时间范围）
- 中部：卡片网格布局（3列），每个卡片含博主名、视频号ID、企业全称、互动数行、视频链接、复核状态胶囊标签
- 颜色语义：侵权=红色(#d4532a)、白名单=绿色(#2a9d4e)、不确定=琥珀色(#d4a02a)

### 证据详情页

- 顶部：面包屑导航 + 视频标题
- 左栏（40%）：结构化字段分组（视频信息、博主身份、引流信息），底部复核操作区（三个状态按钮+备注输入）
- 右栏（60%）：录屏播放器（video标签）、截图画廊（grid缩略图，点击放大）、原始JSON折叠面板

## Agent Extensions

### Skill

- **weixin-video-monitor**
- 用途：提供 weixin/ 项目现有模块的完整 API 参考和流程文档，在修改 db_mapping.py/models.py 和编写 task_runner.py 时查阅模块接口
- 预期结果：确保新增代码与现有 collector.py、store.py、db.py 接口兼容，避免引入破坏性变更
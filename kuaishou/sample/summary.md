# zscqAndroid 项目概览

## 定位

基于 **AScript Android 自动化框架**的知识产权（知识产权）监测取证工具。运行在 Android 设备上，自动在 **快手 App** 中搜索指定关键词，进入视频播放页，循环滑动并截图取证，用于后续 PC 端 OCR/比对。

## 文件结构

```
zscqAndroid/
├── __init__.py          # 包入口，AScript 点击"运行"时触发
├── main.py              # AScript IDE 本地运行入口
├── kuaishou_collect.py  # 快手取证精简流程（核心业务流程）
├── test.py              # 底层自动化工具库 + 完整的快手取证流程（含搜索结果页全量滑动）
├── build.as             # AScript 构建配置（依赖：opencv, requests, pymysql, numpy 等）
├── .gitignore           # 仅忽略 .vscode/.ascript-sync.json
├── .vscode/
│   ├── .ascript-sync.json    # AScript 同步配置
│   ├── .syncignore
│   └── settings.json
└── res/img/             # 资源图片目录
```

## 核心模块

### test.py（自动化工具库 + 完整流程）

- **屏幕操作**: 截图(`screenshot`)、保存(`save_screenshot`)、点击(`tap`/`tap_pct`/`tap_text`/`tap_id`)、滑动(`swipe`/`swipe_pct`/`swipe_up/down/left/right`)、长按
- **系统按键**: 返回、Home、最近任务、通知栏
- **输入搜索**: `input_text` / `input_then_search`（输入后点击"搜索"按钮）
- **定时截屏**: `auto_capture` 循环截图
- **知识产权取证流程** `ip_kuaishou_collect()`: 搜索关键词 → 滑到底 → 回顶 → 点第一个视频 → 循环上滑截图直到到底
- **辅助函数**: 画面指纹比对(`frame_signature`)、视频播放页判定(`is_video_play_page`)、到底文案检测(`has_any_text`)、侧边JSON元数据保存(`snap_with_sidecar`)

### kuaishou_collect.py（精简版取证流程）

精简版 `ip_kuaishou_collect()`: 移除了"搜索结果页先滑到底再回顶"的步骤，直接进入首个视频开始截图取证，速度更快。

### main.py / __init__.py（入口）

两个入口文件行为一致：
- 有命令行参数 → 透传给 `kuaishou_collect.run_cli()`
- 无参数 → 默认关键词 `"弃子归来震万城"`

## 业务流程

1. 在快手 App 中点击搜索图标
2. 输入关键词（如"弃子归来震万城"）
3. 切换到"视频"导航标签
4. 点击第一个视频进入播放页
5. 循环上滑切换下一个视频，每切一个截一张图
6. 每张截图附带 JSON sidecar（含平台、关键词、步骤名、时间戳、分辨率等元数据）
7. 检测到"没有更多了"等文案或画面连续无变化时停止

截图保存路径: `/sdcard/DCIM/ZSCQ/kuaishou/<关键词>/`

## 技术栈

- **运行时**: AScript (Android 自动化框架)
- **语言**: Python 3
- **依赖**: opencv-python-headless, requests, pymysql, numpy, websocket-client, pillow, pandas, openpyxl, schedule, pycryptodome

## 入口命令

```bash
# 自动定时截图
python test.py auto [间隔秒] [次数]

# 快手取证完整流程
python test.py ipflow <关键词> [轮数] [每轮截图数]

# 精简流程（kuaishou_collect）
python kuaishou_collect.py <关键词>
```

## 运行流程

### 触发方式

```
┌──────────────────────────────────────────────────────────────┐
│  触发方式                                                    │
│  ┌─────────────┐  ┌──────────────────┐  ┌───────────────┐  │
│  │ AScript IDE  │  │ ADB shell 命令行  │  │ 定时任务/脚本  │  │
│  │ 点击"运行"   │  │ python main.py …  │  │ 调度触发      │  │
│  └──────┬──────┘  └────────┬─────────┘  └───────┬───────┘  │
│         └──────────────────┼────────────────────┘           │
│                            ▼                                │
│                    ┌────────────────┐                       │
│                    │  __init__.py   │                       │
│                    │  或 main.py    │                       │
│                    │  (入口统一)     │                       │
│                    └───────┬────────┘                       │
│                            ▼                                │
│              ┌──────────────────────────┐                   │
│              │ kuaishou_collect.run_cli()│                   │
│              │ (转发到精简版取证流程)     │                   │
│              └──────────────────────────┘                   │
└──────────────────────────────────────────────────────────────┘
```

### 完整运行流程图

```
启动
 │
 ├─ 1. 入口 (__init__.py / main.py)
 │    ├─ 判断是否有命令行参数
 │    ├─ 有 → 透传给 kuaishou_collect.run_cli(argv)
 │    └─ 无 → 使用默认关键词 "弃子归来震万城"
 │
 ├─ 2. kuaishou_collect.run_cli()
 │    └─ 解析关键词 → 调用 ip_kuaishou_collect(keyword)
 │
 ├─ 3. search_keyword_flow(keyword)          【test.py】
 │    ├─ 3.1 点击右上角搜索图标
 │    │    ├─ 优先查找文字"搜索"控件并点击
 │    │    └─ 失败则点击兜底坐标 (92%, 7%)
 │    ├─ 3.2 点击搜索输入框 (50%, 10%)
 │    ├─ 3.3 输入关键词
 │    │    ├─ act.input(keyword) 输入文字
 │    │    └─ 等待0.4秒
 │    └─ 3.4 触发搜索（循环3次，每次间隔2秒）
 │         ├─ 查找"搜索"按钮控件并点击
 │         └─ 失败则点击兜底坐标 (92%, 10%)
 │
 ├─ 4. 等待搜索结果加载（5秒）
 │
 ├─ 5. 点击"视频"导航标签
 │    ├─ 优先查找文字"视频"控件并点击
 │    └─ 失败则点击兜底坐标 (30%, 13%)
 │
 ├─ 6. 点击第一个视频，进入播放页
 │    ├─ 最多重试4轮
 │    ├─ 每轮尝试6个坐标点（绝对坐标 + 百分比坐标）
 │    ├─ 每次尝试后等待1.6秒
 │    ├─ 通过特征文案判断是否进入播放页:
 │    │   "快来抢首评吧" / "抢首评" / "说点什么" / "相关搜索" / "分享"
 │    └─ 仍无法确认时，对比画面是否变化 + 结果页导航是否消失
 │
 ├─ 7. 进入播放页后，立即截图第1张
 │    ├─ 保存 PNG 到 /sdcard/DCIM/ZSCQ/kuaishou/<keyword>/
 │    └─ 同时生成 JSON sidecar（schema版本、平台、关键词、步骤名、时间戳、分辨率）
 │
 ├─ 8. 循环上滑切换下一个视频并截图
 │    ├─ 上滑: (50%, 82%) → (50%, 18%)，耗时360ms
 │    ├─ 等待1.6秒让视频加载
 │    ├─ 截图并计算 MD5 指纹
 │    ├─ 与上一张画面指纹比较:
 │    │   ├─ 变化了 → 保存截图 + sidecar，继续滑动
 │    │   └─ 未变化 → still_count +1，累计6次则判定到底
 │    ├─ 每次滑动后检测到底文案:
 │    │   "没有更多了" / "无更多作品" / "没有更多作品" / "没有更多视频"
 │    └─ 异常保护: 超过2000次滑动强制停止
 │
 └─ 9. 流程结束
      └─ 输出 [✓] 精简取证流程完成
```

### AScript 运行时行为

脚本运行在 **AScript App** 环境中，底层工作机制：

1. **AScript App** 安装在 Android 手机上，提供 Python 3 解释器和自动化 API
2. 通过无障碍服务（AccessibilityService）获取控件信息和执行点击
3. 通过 MediaProjection 截屏 API 实现截图
4. `build.as` 中的 `pip` 依赖在 AScript 构建时自动安装到手机端

截图文件存储在手机本地路径 `/sdcard/DCIM/ZSCQ/kuaishou/<关键词>/`，后续可通过 ADB pull 或 AScript 文件管理导出到 PC。

### 两个流程版本对比

| 步骤 | 完整版 (test.py ipflow) | 精简版 (kuaishou_collect.py) |
|------|------------------------|---------------------------|
| 搜索关键词 | ✓ | ✓ |
| 点击"视频"导航 | ✓ | ✓ |
| 搜索结果页滑到底 | ✓ | ✗ |
| 搜索结果页回顶 | ✓ | ✗ |
| 点击第一个视频 | ✓ | ✓ |
| 播放页循环截图 | ✓ | ✓ |
| 耗时 | 较长（多出搜索页滑动时间） | 较短（跳过搜索页滑动） |

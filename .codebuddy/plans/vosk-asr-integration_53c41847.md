---
name: vosk-asr-integration
overview: 将 Vosk 离线语音转文字嵌入到微信视频号固证流程中，创建 asr_vosk.py 模块、集成到 collector.py、更新 models/db_mapping、编写单步测试。
todos:
  - id: create-asr-vosk-module
    content: 使用 [skill:weixin-video-monitor] 查阅现有 asr_local.py 接口模式，新建 weixin/asr_vosk.py：实现 model 加载（VOSK_MODEL_DIR 环境变量 + weixin/vosk-model-cn/ 默认回退）、core_transcribe_for_record() 公共函数（根据 video_identifier 命名输出，写 media_info 各字段）、transcribe_wav() 底层转写（skip WAV header、流式读取 4000 字节块、收集 Result 和 FinalResult）
    status: completed
  - id: update-models-and-db
    content: 更新 models.py media_info 新增 asr_text_path/asr_model 字段；更新 db_mapping.py 建表 SQL 新增 asr_text_path/asr_model 两列，evidence_record_to_db_row() 行映射新增对应字段；更新 web/services/db_service.py ensure_tables() 的 missing_columns 列表
    status: completed
  - id: integrate-cli-path
    content: 修改 main.py attach_recording_media()：在 extract_audio 成功后调用 core_transcribe_for_record()；修改 collector.py collect_current_video() 预录片段分支（recording_video_path 非空时）同样的 ASR 调用
    status: completed
    dependencies:
      - create-asr-vosk-module
      - update-models-and-db
  - id: integrate-web-path
    content: 修改 web/services/task_runner.py _run_pipeline() 循环：在 collect_current_video 返回 + asyncio.sleep 后，从 record.media_info 取 recording_audio_path，若有且非空则调用 core_transcribe_for_record()
    status: completed
    dependencies:
      - create-asr-vosk-module
      - update-models-and-db
  - id: create-step-test
    content: 新建 weixin/step_tests/test_vosk_asr.py：CLI 脚本，解析 --audio / --model / --output 参数，调用 asr_vosk.transcribe_wav()，输出纯文本文件，打印转写耗时和文本预览
    status: completed
    dependencies:
      - create-asr-vosk-module
  - id: verify-end-to-end
    content: 端到端验证：用一条已有 wav 文件运行 test_vosk_asr.py 确认转写正常；再启动 CLI 模式 `python main.py` 跑一条完整取证，检查 JSON 中 asr_text/asr_text_path/asr_model 是否已正确填充
    status: completed
    dependencies:
      - integrate-cli-path
      - integrate-web-path
      - create-step-test
---

## 需求概述

按照 `weixin/step_tests/conver.txt` 的方案，将 **Vosk 离线语音转文字** 嵌入微信视频号固证流程。

## 核心要点

1. **创建 Vosk ASR 模块** (`asr_vosk.py`)：封装模型加载、WAV 头跳过、流式转写、输出纯文本 + JSON
2. **在固证流程中插入 ASR 步骤**：音频提取后立即转写，结果写回 `EvidenceRecord.media_info`
3. **防串乱机制**：ASR 输入/输出文件命名一律包含 `video_identifier`，保存前做绑定校验
4. **单步测试脚本**： `python weixin/step_tests/test_vosk_asr.py --audio xxx.wav --model vosk-model-cn --output xxx.asr.txt`
5. **数据模型扩展**：`models.py` 新增 `asr_text_path`/`asr_model` 字段，`db_mapping.py` 新增对应数据库列

## 反串乱规则

- `media_info["asr_source_video_identifier"] = candidate["video_identifier"]`
- ASR 输出文件路径包含 `video_identifier`：`media/{video_identifier}.asr.txt` / `media/{video_identifier}.asr.json`

## 技术方案

### Vosk 选型理由

| 因素 | Vosk | faster-whisper (已有 asr_local.py) |
| --- | --- | --- |
| 推理速度 | 快，纯 C++ 引擎 | 较慢，依赖 onnxruntime |
| 内存占用 | 低 | 中等 |
| 离线可用 | 是 | 是 |
| 中文支持 | 专有中文模型 (vosk-model-cn-0.22) | 通用多语言 |
| 安装方式 | `pip install vosk` + 下载模型 | `pip install faster-whisper`（自动下载） |


用户选择 Vosk 核心理由：速度优先，轻量离线。

### 实现策略

#### 插入点设计

当前音频提取和录屏挂载发生在两条路径：

**CLI 路径** (`main.py` run 函数，第 960-971 行)：

```
collect_current_video() → stop_capture_session() → attach_recording_media() → save_record()
```

录音是在 `collect_current_video` **之后**停止的，因此 ASR 最自然的插入点是 `attach_recording_media()` 函数（第 864-886 行）——该函数已经完成 probe/extract 操作，在第 886 行后追加 ASR 调用即可。

**Web 路径** (`web/services/task_runner.py`，第 222-238 行)：

```
collect_current_video() → asyncio.sleep(hold_seconds) → save_record()
```

Web 模式中未调用 `attach_recording_media()`，`collect_current_video` 在被调用时不传 `recording_video_path` 参数。因此需要在 `task_runner.py` 循环中，`collect_current_video()` 后单独处理音频提取 + ASR。

**collector.py 预录片段路径**（第 94-102 行）：
当 `recording_video_path` 非空时，该分支自己处理音频提取，也需在此追加 ASR。

#### 统一入口方案

为避免重复代码，设计一个公共函数 `core_transcribe_for_record()`：

```python
# asr_vosk.py
def core_transcribe_for_record(record, wav_path: str, video_identifier: str = ""):
    """Run Vosk ASR on a wav and populate record.media_info fields."""
    # 1. 确定 video_identifier（从 record 中提取或传入）
    # 2. 构造输出路径：media/{vid}.asr.txt, media/{vid}.asr.json
    # 3. 调用 Vosk 转写
    # 4. 写入 record.media_info["asr_text"], asr_text_path, asr_json_path, asr_model
    # 5. 写入 asr_source_video_identifier 做绑定校验
```

三处调用点统一使用此函数：

- `main.py` `attach_recording_media()` 末尾
- `collector.py` `collect_current_video()` 预录片段分支末尾
- `task_runner.py` `_run_pipeline()` 循环中 save_record 前

### 数据模型变更

#### models.py — media_info 新增字段

```
"asr_text_path": "",      # 转写纯文本文件路径
"asr_model": "",          # ASR 模型标识，如 "vosk-cn-0.22"
```

#### db_mapping.py — 建表 SQL 新增列

```sql
asr_text_path VARCHAR(1000) NOT NULL DEFAULT '',
asr_model VARCHAR(32) NOT NULL DEFAULT '',
```

行映射函数 `evidence_record_to_db_row()` 同步更新。

### 目录结构

```
weixin/
├── asr_vosk.py                 # [NEW] Vosk ASR 封装模块
├── models.py                   # [MODIFY] media_info 新增 asr_text_path, asr_model
├── db_mapping.py               # [MODIFY] 建表 SQL + 行映射新增字段
├── collector.py                # [MODIFY] 预录片段路径追加 ASR
├── main.py                     # [MODIFY] attach_recording_media() 追加 ASR
├── step_tests/
│   └── test_vosk_asr.py        # [NEW] 单步测试脚本
├── web/
│   └── services/
│       ├── task_runner.py       # [MODIFY] Web 路径 loop 中追加 ASR
│       └── db_service.py        # [MODIFY] missing_columns 列表追加 asr_text_path/asr_model
└── media/
    ├── scrcpy_*.mp4             # 现有录屏文件（时间戳命名）
    ├── scrcpy_*.wav             # 现有音频文件（时间戳命名）
    └── {video_identifier}.asr.txt/json  # [NEW] ASR 产物（video_identifier 命名）
```

## Agent Extensions

### Skill

- **weixin-video-monitor**
- 目的：在修改 collector.py、models.py、db_mapping.py、main.py 时查阅现有模块接口，确保新增代码与现有 collector/store/db 接口兼容
- 预期结果：ASR 调用正确嵌入现有数据流，不破坏原有取证步骤顺序
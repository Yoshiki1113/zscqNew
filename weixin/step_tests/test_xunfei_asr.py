"""Single-step test: iFlytek (科大讯飞) cloud ASR.

Prerequisites:
  1. Activate "语音听写（流式版）" service at https://console.xfyun.cn/
  2. Get APPID / APIKey / APISecret from the service page

Usage:
    python weixin/step_tests/test_xunfei_asr.py --audio media/xxx.wav --appid xxx --apikey xxx --apisecret xxx
    python weixin/step_tests/test_xunfei_asr.py --audio media/xxx.wav  # uses env vars or defaults
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_WEIXIN_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_WEIXIN_DIR))


def main():
    parser = argparse.ArgumentParser(description="iFlytek ASR single-step test")
    parser.add_argument("--audio", required=True, help="Path to 16kHz mono WAV file")
    parser.add_argument("--appid", default="", help="iFlytek APPID")
    parser.add_argument("--apikey", default="", help="iFlytek APIKey")
    parser.add_argument("--apisecret", default="", help="iFlytek APISecret")
    parser.add_argument("--output", default="", help="Output text file path")
    args = parser.parse_args()

    audio_path = Path(args.audio).resolve()
    if not audio_path.exists():
        print(f"[ERROR] Audio not found: {audio_path}")
        sys.exit(1)

    from asr_xunfei import transcribe_wav

    try:
        text = transcribe_wav(
            str(audio_path),
            appid=args.appid,
            apikey=args.apikey,
            apisecret=args.apisecret,
        )
    except RuntimeError as exc:
        if "11201" in str(exc):
            print(f"\n[ERROR] {exc}")
            print("\n请确认已完成以下步骤：")
            print("  1. 打开 https://console.xfyun.cn/")
            print("  2. 进入「我的应用」→ 选择该应用")
            print("  3. 点击「服务管理」→ 找到「语音听写（流式版）」")
            print("  4. 点击「开通」或「领取免费额度」")
        else:
            print(f"[ERROR] {exc}")
        sys.exit(1)

    print(f"\n---XUNFEI RESULT ({len(text)} chars)---")
    print(text)

    output_path = Path(args.output) if args.output else audio_path.with_suffix(".xunfei.txt")
    output_path.write_text(text, encoding="utf-8")
    print(f"\nOutput saved: {output_path}")


if __name__ == "__main__":
    main()

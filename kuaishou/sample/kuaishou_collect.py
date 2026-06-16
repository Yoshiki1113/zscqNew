"""
快手取证精简流程：
1) 搜索关键词
2) 点“视频”导航
3) 直接点开第一个视频
4) 进入播放页后开始截图取证，持续上滑到最后
"""

import time

try:
    from .test import (
        search_keyword_flow,
        tap_text,
        tap_pct,
        has_any_text,
        enter_first_video_from_result,
        screenshot,
        snap_with_sidecar,
        frame_signature,
        swipe_pct,
    )
except ImportError:
    from test import (
        search_keyword_flow,
        tap_text,
        tap_pct,
        has_any_text,
        enter_first_video_from_result,
        screenshot,
        snap_with_sidecar,
        frame_signature,
        swipe_pct,
    )


def ip_kuaishou_collect(keyword):
    """
    精简版快手取证：
    - 不做搜索结果页“先到底再回顶”
    - 直接进入首个视频开始取证
    """
    print("=" * 52)
    print(f"  [ZSCQ] 快手取证(精简)启动  keyword={keyword}")
    print("=" * 52)

    search_keyword_flow(keyword)
    print("[flow] 等待搜索结果稳定（5s）")
    time.sleep(5)

    print("[flow] 点击搜索导航：视频")
    if not tap_text("视频"):
        tap_pct(0.30, 0.13)
        print('[~] 未识别到“视频”文字，已点击导航兜底坐标')
    time.sleep(1.0)

    print("[flow] 点击第一个视频")
    if not enter_first_video_from_result(max_rounds=4):
        print("[✗] 多次尝试后仍未进入播放页，停止本次流程")
        return 1

    time.sleep(2.0)
    print("[flow] 已点开第一个视频，开始截图")

    first_bmp = screenshot()
    snap_with_sidecar(keyword, "video_001", platform="kuaishou", bitmap=first_bmp)
    prev_sig = frame_signature(first_bmp)

    print("[flow] 开始连续切换下一个视频并截图，直到到底")
    still_count = 0
    max_still = 6
    emergency_guard = 2000  # 仅异常兜底，不作为常规停止条件
    idx = 1
    end_hints = ["没有更多了", "无更多作品", "没有更多作品", "没有更多视频"]
    guard_count = 0
    while still_count < max_still:
        guard_count += 1
        if guard_count > emergency_guard:
            print("[~] 达到异常保护上限，停止滑动以防死循环")
            break

        hint = has_any_text(end_hints)
        if hint:
            print(f"[✓] 检测到到底文案: {hint}，停止滑动")
            break

        swipe_pct(0.50, 0.82, 0.50, 0.18, duration=360)
        time.sleep(1.6)

        bmp = screenshot()
        sig = frame_signature(bmp)

        if sig == prev_sig:
            still_count += 1
            print(f"[~] 画面未变化（{still_count}/{max_still}），可能已划不动")
        else:
            still_count = 0
            idx += 1
            step = f"video_{idx:03d}"
            snap_with_sidecar(keyword, step, platform="kuaishou", bitmap=bmp)
            print(f"[✓] 已切到下一个视频并截图: {step}")

        hint = has_any_text(end_hints)
        if hint:
            print(f"[✓] 检测到到底文案: {hint}，停止滑动")
            break

        prev_sig = sig

    print("\n[✓] 精简取证流程完成")
    return 0


def run_cli(argv=None):
    import sys

    if argv is None:
        argv = sys.argv[1:]

    if len(argv) < 1:
        print("用法: python kuaishou_collect.py <关键词>")
        return 1

    return ip_kuaishou_collect(argv[0])


if __name__ == "__main__":
    raise SystemExit(run_cli())

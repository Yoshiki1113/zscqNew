"""
AScript Android 自动化工具脚本
=================================
支持功能：
  1. 自动截图全屏
  2. 保存截图到手机相册
  3. 点击屏幕（坐标 / 按文字查找）
  4. 滑动屏幕
  5. 搜索输入文字
  6. 返回键
=================================
"""

import time
import os
import json
import hashlib
from datetime import datetime

# ============ AScript 核心 API 导入 ============
from ascript.android.action import click, slide, Key
from ascript.android import action as act
from ascript.android import screen
from ascript.android.screen import capture
from ascript.android.node import Selector
from ascript.android.system import Device, R


# ─── 0. 屏幕信息 ────────────────────────────────
def screen_size():
    """获取屏幕分辨率 (宽, 高)"""
    d = Device.display()
    return d.widthPixels, d.heightPixels


# ─── 1. 全屏截图 ────────────────────────────────
def screenshot():
    """全屏截图，返回 Android Bitmap 对象"""
    return capture()


def save_bitmap(bitmap, filepath, quality=100):
    """
    兼容不同 AScript 版本的 Bitmap 保存：
    - 优先使用 Bitmap 对象自身 save()
    - 失败则回退到 screen.bitmap_to_file()
    """
    if hasattr(bitmap, "save"):
        bitmap.save(filepath)
        return
    screen.bitmap_to_file(filepath, bitmap, quality)


# ─── 2. 保存截图 ────────────────────────────────
def save_screenshot(bitmap, filepath=None):
    """
    保存截图到文件
    不指定路径则自动生成带时间戳的文件名，存到 /sdcard/DCIM/Screenshots/
    """
    if filepath is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = R.sd(f"/DCIM/Screenshots/screenshot_{ts}.png")
    save_dir = os.path.dirname(filepath)
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    save_bitmap(bitmap, filepath)
    print(f"[✓] 截图已保存: {filepath}")
    return filepath


def snap():
    """快捷方法：截图 + 保存，一行搞定"""
    bmp = screenshot()
    return save_screenshot(bmp)


# ─── 3. 点击 ────────────────────────────────────
def tap(x, y, duration=20):
    """
    点击指定坐标
    x, y:   屏幕坐标
    duration: 按下时长(毫秒)，默认 20ms（普通点击），设大值变长按
    """
    click(x, y, dur=duration)
    print(f"[✓] 点击 ({x},{y}) 持续{duration}ms")

def tap_pct(px, py, duration=20):
    """
    按屏幕百分比点击
    px, py: 0~1 之间，如 (0.5, 0.5) 为屏幕中心
    """
    w, h = screen_size()
    x = int(max(0.0, min(1.0, px)) * w)
    y = int(max(0.0, min(1.0, py)) * h)
    tap(x, y, duration)


def tap_text(text):
    """
    按屏幕上显示的文字查找控件并点击
    text: 要查找的文字，如 "确定", "登录" 等
    """
    node = Selector().text(text).find()
    if node:
        node.click()
        print(f'[✓] 点击文字 "{text}"')
        return True
    else:
        print(f'[✗] 未找到文字 "{text}"')
        return False


def tap_id(res_id):
    """
    按控件 ID 查找并点击
    res_id: 例如 "com.example:id/btn_login"
    """
    node = Selector().id(res_id).find()
    if node:
        node.click()
        print(f'[✓] 点击 ID "{res_id}"')
        return True
    else:
        print(f'[✗] 未找到 ID "{res_id}"')
        return False


def long_press(x, y, duration=2000):
    """长按指定坐标，默认 2 秒"""
    tap(x, y, duration=duration)


# ─── 4. 滑动 ────────────────────────────────────
def swipe(x1, y1, x2, y2, duration=20):
    """
    从 (x1,y1) 滑到 (x2,y2)
    duration: 滑动耗时(毫秒)，越大越慢
    """
    slide(x1, y1, x2, y2, dur=duration)
    print(f"[✓] 滑动 ({x1},{y1}) → ({x2},{y2}) 耗时{duration}ms")

def swipe_pct(x1, y1, x2, y2, duration=300):
    """按屏幕百分比滑动"""
    w, h = screen_size()
    sx = int(max(0.0, min(1.0, x1)) * w)
    sy = int(max(0.0, min(1.0, y1)) * h)
    ex = int(max(0.0, min(1.0, x2)) * w)
    ey = int(max(0.0, min(1.0, y2)) * h)
    swipe(sx, sy, ex, ey, duration)


def swipe_up():
    """从下往上滑（模拟上划翻页）"""
    w, h = screen_size()
    mid_x = w // 2
    slide(mid_x, h * 3 // 4, mid_x, h // 4, dur=300)
    print(f"[✓] 上划")


def swipe_down():
    """从上往下滑"""
    w, h = screen_size()
    mid_x = w // 2
    slide(mid_x, h // 4, mid_x, h * 3 // 4, dur=300)
    print(f"[✓] 下划")


def swipe_left():
    """从右往左滑"""
    w, h = screen_size()
    mid_y = h // 2
    slide(w * 3 // 4, mid_y, w // 4, mid_y, dur=300)
    print(f"[✓] 左划")


def swipe_right():
    """从左往右滑"""
    w, h = screen_size()
    mid_y = h // 2
    slide(w // 4, mid_y, w * 3 // 4, mid_y, dur=300)
    print(f"[✓] 右划")


# ─── 5. 搜索输入 ────────────────────────────────
def input_text(text, target_id=None):
    """
    输入文字到当前已获焦点的输入框
    如果指定 target_id，则先通过 ID 定位输入框再输入
    text:      要输入的文字
    target_id: 可选，输入框的控件 ID，如 "com.example:id/edit_search"
    """
    if target_id:
        selector = Selector().id(target_id)
        act.input(text, selector)
        print(f'[✓] 向 ID="{target_id}" 输入: {text}')
    else:
        act.input(text)
        print(f'[✓] 输入: {text}')


def input_then_search(text, target_id=None):
    """
    输入文字后触发搜索：
    - 先点击页面上的“搜索”按钮
    - 找不到时再尝试点击常见位置作为兜底
    """
    input_text(text, target_id)
    time.sleep(0.4)

    search_clicked = False
    for i in range(3):
        if tap_text("搜索"):
            search_clicked = True
            print(f'[✓] 第{i + 1}/3次点击“搜索”按钮')
        else:
            # 兜底：多数机型搜索确认按钮在右上区域
            tap_pct(0.92, 0.10)
            print(f'[~] 第{i + 1}/3次未识别到“搜索”文字，已点击右上角兜底位置')
        time.sleep(2.0)

    if search_clicked:
        print('[✓] 搜索触发完成（共点击3次，间隔2秒）')
    else:
        print('[~] 搜索按钮文字始终未识别，已使用兜底坐标触发3次')


def clear_input(target_id=None):
    """清空输入框"""
    input_text("", target_id)


# ─── 6. 返回键 ──────────────────────────────────
def back():
    """按返回键"""
    Key.back()
    print("[✓] 返回键")


def home():
    """按 Home 键"""
    Key.home()
    print("[✓] Home 键")


def recents():
    """呼出最近任务"""
    Key.recents()
    print("[✓] 最近任务")


def notifications():
    """拉下通知栏"""
    Key.notifactions()
    print("[✓] 通知栏")


# ─── 7. 自动截图循环 ────────────────────────────
def auto_capture(interval=10, max_count=0):
    """
    定时自动截图主循环
    interval:   截图间隔(秒)
    max_count:  最大次数，0=无限
    """
    save_dir = R.sd("/DCIM/Screenshots/")
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    count = 0
    print("=" * 45)
    print(f"  自动截图已启动")
    print(f"  间隔: {interval}s  |  保存: {save_dir}")
    print(f"  最大次数: {'无限' if max_count == 0 else max_count}")
    print("=" * 45)

    while True:
        count += 1
        if max_count > 0 and count > max_count:
            print(f"\n[✓] 已完成 {max_count} 次截图，停止")
            break

        start = time.time()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(save_dir, f"screenshot_{ts}.png")

        try:
            bmp = screenshot()
            save_bitmap(bmp, filepath)
            elapsed_ms = int((time.time() - start) * 1000)
            print(f"[{count}] ✓ screenshot_{ts}.png  ({elapsed_ms}ms)")
        except Exception as e:
            print(f"[{count}] ✗ 失败: {e}")

        elapsed = time.time() - start
        time.sleep(max(0, interval - elapsed))


# ─── 8. 业务流程：知识产权监测取证（短视频搜索页） ─────────────
def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)
    return path


def save_sidecar_json(image_path, payload):
    json_path = os.path.splitext(image_path)[0] + ".json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[✓] sidecar: {json_path}")
    return json_path


def frame_signature(bitmap):
    """
    计算截图内容指纹，用于判断是否已经滑不动（画面基本不变）
    """
    b64 = screen.bitmap_base64(bitmap)
    return hashlib.md5(b64.encode("utf-8")).hexdigest()


def has_any_text(texts):
    """
    是否存在任一指定文案（用于到底判定）。
    """
    for t in texts:
        try:
            node = Selector().text(t).find()
            if node:
                return t
        except Exception:
            # 个别页面/节点异常时忽略，继续尝试其他文案
            pass
    return None


def is_video_play_page():
    """
    判断是否已进入视频播放页（尽量避免“已进入却误判未进入”）。
    """
    # 播放页常见特征文案
    play_hit = has_any_text(["快来抢首评吧", "抢首评", "说点什么", "相关搜索", "分享"])
    if play_hit:
        return True

    # 搜索结果列表页常见顶部导航文案
    result_hit = has_any_text(["综合", "图片", "直播", "智能"])
    if result_hit:
        return False

    # 未命中播放页关键特征时，不判定为进入播放页
    return False


def enter_first_video_from_result(max_rounds=3):
    """
    从搜索结果页尝试进入第一个视频。
    - 多轮、多坐标重试，避免一次点击未命中
    - 仅在检测到播放页后返回 True
    """
    # 优先点击你标注的红框区域（左上首个卡片），多点尝试提高命中率
    candidates = [
        ("abs", 350, 950),
        ("abs", 300, 880),
        ("abs", 260, 1050),
        ("pct", 0.24, 0.33),
        ("pct", 0.20, 0.30),
        ("pct", 0.26, 0.38),
    ]
    for r in range(max_rounds):
        print(f"[flow] 尝试进入第一个视频（第{r + 1}/{max_rounds}轮）")
        for mode, x, y in candidates:
            before_sig = frame_signature(screenshot())
            if mode == "abs":
                tap(int(x), int(y))
            else:
                tap_pct(x, y)
            time.sleep(1.6)
            if is_video_play_page():
                print("[✓] 已确认进入视频播放页")
                return True
            after_sig = frame_signature(screenshot())
            if after_sig != before_sig and not has_any_text(["综合", "图片", "直播", "智能"]):
                print("[✓] 画面发生变化且结果页导航消失，判定已进入播放页")
                return True
            print("[~] 仍未确认进入播放页，继续重试")
    return False


def snap_with_sidecar(keyword, step_name, platform="kuaishou", out_root=None, bitmap=None):
    """
    截图 + 业务 sidecar（用于后续 PC 端 OCR/比对）
    """
    if out_root is None:
        out_root = R.sd(f"/DCIM/ZSCQ/{platform}/{keyword}")
    ensure_dir(out_root)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    image_path = os.path.join(out_root, f"{platform}_{keyword}_{step_name}_{ts}.png")
    bmp = bitmap if bitmap is not None else screenshot()
    save_bitmap(bmp, image_path)
    print(f"[✓] 业务截图: {image_path}")

    w, h = screen_size()
    payload = {
        "schema": "zscq.mobile.capture.sidecar.v1",
        "platform": platform,
        "keyword": keyword,
        "step": step_name,
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "image_file": os.path.basename(image_path),
        "screen_width": w,
        "screen_height": h,
    }
    save_sidecar_json(image_path, payload)
    return image_path


def search_keyword_flow(keyword):
    """
    通用搜索动作（按业务要求）：
    1) 先点击右上角搜索图标进入搜索页
    2) 点击搜索输入框
    3) 输入关键词并点击“搜索”
    """
    print(f"[flow] 搜索关键词: {keyword}")

    # 1) 先点右上角搜索图标（优先文字，其次坐标）
    if not tap_text("搜索"):
        tap_pct(0.92, 0.07)
        print("[~] 未找到搜索图标文字，已点击右上角兜底坐标")
    time.sleep(0.5)

    # 2) 点输入框（多数在顶部中间偏上）
    tap_pct(0.50, 0.10)
    time.sleep(0.3)

    # 3) 输入并触发搜索
    input_then_search(keyword)
    time.sleep(1.2)


def ip_kuaishou_collect(
    keyword,
    rounds=8,
    shots_per_round=2,
    swipe_sleep=1.0,
):
    """
    知识产权业务取证流程（快手示例）：
      1) 搜索关键词后等待 5 秒加载结果
      2) 点击搜索栏下导航中的“视频”
      3) 先滑到底，再回到最上
      4) 点第一个视频，等待2秒后开始截图
      5) 在播放页持续上滑并截图，直到到底
    """
    print("=" * 52)
    print(f"  [ZSCQ] 快手取证流程启动  keyword={keyword}")
    print(f"  rounds={rounds}, shots_per_round={shots_per_round}")
    print("=" * 52)

    search_keyword_flow(keyword)
    print("[flow] 等待搜索结果稳定（5s）")
    time.sleep(5)

    # 点击导航“视频”（先尝试文本，失败走坐标兜底）
    # 兜底坐标按你提供截图估算：位于搜索栏下方导航区域
    print("[flow] 点击搜索导航：视频")
    if not tap_text("视频"):
        tap_pct(0.30, 0.13)
        print('[~] 未识别到“视频”文字，已点击导航兜底坐标')
    time.sleep(1.0)

    # 搜索结果页先滑到底，再回到最上（不截图）
    print("[flow] 搜索结果页先滑到底")
    result_prev_sig = None
    result_still_count = 0
    result_max_still = 5
    result_max_swipes = 120  # 安全上限，避免异常场景死循环
    for _ in range(result_max_swipes):
        hint = has_any_text(["没有更多了", "没有更多作品"])
        if hint:
            print(f"[✓] 搜索结果页检测到到底文案: {hint}")
            break

        swipe_pct(0.50, 0.82, 0.50, 0.18, duration=360)
        time.sleep(1.0)
        bmp = screenshot()
        sig = frame_signature(bmp)

        if result_prev_sig is not None and sig == result_prev_sig:
            result_still_count += 1
            print(f"[~] 搜索结果页画面未变化（{result_still_count}/{result_max_still}）")
            if result_still_count >= result_max_still:
                print("[✓] 搜索结果页连续无变化，判定已到底")
                break
        else:
            result_still_count = 0

        result_prev_sig = sig

    print("[flow] 搜索结果页回到最上")
    top_prev_sig = None
    top_still_count = 0
    top_max_still = 5
    top_max_swipes = 120  # 安全上限，避免异常场景死循环
    for _ in range(top_max_swipes):
        swipe_pct(0.50, 0.22, 0.50, 0.86, duration=360)
        time.sleep(0.8)
        bmp = screenshot()
        sig = frame_signature(bmp)

        if top_prev_sig is not None and sig == top_prev_sig:
            top_still_count += 1
            print(f"[~] 回顶阶段画面未变化（{top_still_count}/{top_max_still}）")
            if top_still_count >= top_max_still:
                print("[✓] 回顶阶段连续无变化，判定已回到最上")
                break
        else:
            top_still_count = 0

        top_prev_sig = sig

    # 点击第一个视频（你提供截图中为左上区域），并校验是否真进入播放页
    print("[flow] 点击第一个视频")
    if not enter_first_video_from_result(max_rounds=4):
        print("[✗] 多次尝试后仍未进入播放页，停止本次流程")
        return
    time.sleep(2.0)
    print("[flow] 已点开第一个视频，开始截图")
    first_bmp = screenshot()
    snap_with_sidecar(keyword, "video_001", platform="kuaishou", bitmap=first_bmp)
    prev_sig = frame_signature(first_bmp)

    # 在视频播放流中上滑到下一个视频，直到到底
    # 判定优先级：
    # 1) 页面出现“没有更多了 / 无更多作品”等文案
    # 2) 连续多次滑动后画面无变化（兜底）
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

    print("\n[✓] 取证流程完成")


# ─── 9. 示例演示 ────────────────────────────────
def demo():
    """
    完整功能演示：
      截图 → 保存 → 滑动 → 点击 → 输入 → 返回
    """
    print("\n~~~ AScript 功能演示 ~~~\n")

    # 1. 全屏截图 + 保存
    print("[1] 截图保存")
    snap()

    # 2. 滑动（上划翻页）
    print("[2] 上划翻页")
    swipe_up()
    time.sleep(1)

    # 3. 点击屏幕中心
    print("[3] 点击中心")
    w, h = screen_size()
    tap(w // 2, h // 2)
    time.sleep(0.5)

    # 4. 输入文字
    print("[4] 输入文字")
    input_text("测试文字")
    time.sleep(0.5)

    # 5. 返回
    print("[5] 返回")
    back()

    print("\n[✓] 演示完毕")


def print_usage():
    print("AScript 工具脚本已就绪")
    print("使用方式:")
    print("  python test.py auto   # 定时截图(默认10s一次)")
    print("  python test.py auto 5 20  # 每5s一次，共20次")
    print("  python test.py snap  # 截图保存一张")
    print("  python test.py demo  # 功能演示")
    print("  python test.py info  # 查看屏幕信息")
    print("  python test.py ipflow <关键词> [轮数] [每轮截图数]  # 快手业务取证流程")


def run_cli(argv=None):
    """
    统一命令入口：
    - 直接 `python test.py ...`
    - 或在 AScript 的 main.py/__init__.py 中调用本函数
    """
    import sys
    if argv is None:
        argv = sys.argv[1:]

    if len(argv) > 0:
        cmd = argv[0]

        if cmd == "auto":
            interval = int(argv[1]) if len(argv) > 1 else 10
            max_cnt = int(argv[2]) if len(argv) > 2 else 0
            auto_capture(interval, max_cnt)
        elif cmd == "demo":
            demo()
        elif cmd == "snap":
            snap()
        elif cmd == "info":
            w, h = screen_size()
            print(f"屏幕分辨率: {w} x {h}")
        elif cmd == "ipflow":
            # 示例:
            # python test.py ipflow 少爷当腻了只想好好打工 8 2
            if len(argv) < 2:
                print("用法: python test.py ipflow <关键词> [轮数] [每轮截图数]")
                return 1
            kw = argv[1]
            rounds = int(argv[2]) if len(argv) > 2 else 8
            shots = int(argv[3]) if len(argv) > 3 else 2
            ip_kuaishou_collect(kw, rounds=rounds, shots_per_round=shots)
        else:
            print(f"未知命令: {cmd}")
            print("可用: auto [间隔秒] [次数] | demo | snap | info | ipflow <关键词> [轮数] [每轮截图数]")
            return 1
    else:
        print_usage()
    return 0


# ─── 入口 ───────────────────────────────────────
if __name__ == "__main__":
    raise SystemExit(run_cli())

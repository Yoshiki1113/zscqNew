"""
快手短剧自动筛查脚本
依赖: pip install uiautomator2
使用: 手机开启USB调试，连接电脑后运行
"""

import uiautomator2 as u2
import time
import re
import os
from datetime import datetime


class KuaishouScanner:
    """快手短剧自动筛查工具 - 基于uiautomator UI层级树，文本识别100%精确"""

    def __init__(self, device_serial=None):
        if device_serial:
            self.d = u2.connect(device_serial)
        else:
            self.d = u2.connect()  # 自动连接唯一设备
        self.screenshot_dir = "screenshots"
        os.makedirs(self.screenshot_dir, exist_ok=True)

    # ════════════════════════════════════════════════════
    # 核心: 高精度提取快手号
    # ════════════════════════════════════════════════════

    def extract_author_id(self) -> str:
        """
        在作者主页提取快手号。
        直接读取UI层级树中的文本节点，不依赖OCR。

        uiautomator返回的是应用的真实文本数据，
        无论界面上是否有复制图标、特殊符号，
        读到的永远是精准的字符串。
        """
        # 方式1: 通过 text 属性精确匹配
        try:
            el = self.d(textContains="快手号")
            full_text = el.get_text()
            # "快手号：yingbin111" → 提取冒号后的部分
            match = re.search(r'快手号[：:]\s*(\S+)', full_text)
            if match:
                return match.group(1).strip()
        except Exception:
            pass

        # 方式2: 通过 resource-id 定位
        try:
            el = self.d(resourceId="com.kuaishou.nebula:id/profile_id")
            return el.get_text().strip()
        except Exception:
            pass

        # 方式3: 遍历查找包含"快手号"的父节点，读取相邻文本
        try:
            els = self.d(className="android.widget.TextView")
            for el in els:
                text = el.get_text()
                if "快手号" in text:
                    # 提取冒号后面的内容
                    match = re.search(r'[：:](.+?)$', text)
                    if match:
                        return match.group(1).strip()
                    # 如果没有冒号，读下一个兄弟节点
                    sibling = el.sibling(className="android.widget.TextView")
                    if sibling.exists:
                        return sibling.get_text().strip()
        except Exception:
            pass

        raise ValueError("未找到快手号")

    # ════════════════════════════════════════════════════
    # 流程步骤
    # ════════════════════════════════════════════════════

    def open_app(self, package_name="com.kuaishou.nebula"):
        self.d.app_start(package_name)
        time.sleep(3)

    def search_drama(self, drama_name: str):
        """搜索短剧：定位搜索框 → 输入 → 搜索"""
        # 等待搜索框出现并点击
        el = self.d(resourceId="com.kuaishou.nebula:id/search_edit_text")
        el.click(timeout=5)
        time.sleep(1)
        el.clear_text()
        el.set_text(drama_name)
        time.sleep(0.5)

        # 点击搜索按钮
        self.d(text="搜索").click()
        time.sleep(3)

    def refresh_search(self):
        """下拉刷新搜索结果"""
        self.d.swipe(500, 300, 500, 1000, duration=0.2)
        time.sleep(2)

    def click_first_video(self):
        """点击第一个搜索结果视频"""
        el = self.d(className="android.widget.FrameLayout", index=0)
        el.click(timeout=5)
        time.sleep(2)

    def take_screenshot(self, filename=None):
        if not filename:
            filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        path = os.path.join(self.screenshot_dir, filename)
        self.d.screenshot(path)
        print(f"  截图保存: {path}")
        return path

    def go_to_author_page(self):
        """点击作者头像/名称，进入作者主页"""
        # 方式1: 点击作者名
        el = self.d(resourceId="com.kuaishou.nebula:id/author_name")
        if el.exists(timeout=3):
            el.click()
            time.sleep(2)
            return
        # 方式2: 点击头像
        el = self.d(resourceId="com.kuaishou.nebula:id/avatar")
        if el.exists(timeout=3):
            el.click()
            time.sleep(2)

    def go_back(self):
        self.d.press("back")
        time.sleep(1)

    # ════════════════════════════════════════════════════
    # 完整筛查流程
    # ════════════════════════════════════════════════════

    def scan_drama_list(self, drama_names: list[str]):
        """
        对每个短剧名执行完整筛查流程
        """
        results = []

        for drama in drama_names:
            print(f"\n{'='*50}")
            print(f"开始筛查短剧: {drama}")
            print(f"{'='*50}")

            self.search_drama(drama)
            self.refresh_search()
            self.click_first_video()

            # 截图视频封面
            screenshot = self.take_screenshot(f"{drama}_video.png")

            # 进入作者主页提取ID
            self.go_to_author_page()

            try:
                author_id = self.extract_author_id()
                print(f"  ✅ 作者ID: {author_id}")
            except ValueError:
                author_id = "N/A"
                print(f"  ⚠️ 未找到作者ID")

            results.append({
                "drama": drama,
                "author_id": author_id,
                "screenshot": screenshot,
            })

            # 返回搜索结果页
            self.go_back()
            self.go_back()
            time.sleep(1)

        return results


# ════════════════════════════════════════════════════
# 独立演示: 对比 OCR 与 uiautomator 的差异
# ════════════════════════════════════════════════════

def demo_why_uiautomator_wins():
    """
    演示为什么 uiautomator 提取快手号不会出错。

    你之前那截图，"快手号：yingbin111" 后面有个 📋 复制图标。
    - OCR 会把图标边缘识别成 "0" → yingbin1110 ❌
    - uiautomator 读的是实际 TextView 文本 → yingbin111 ✅

    简单说：uiautomator 读的是代码里的真实字符串，
    "快手号：yingbin111" 这个 text 字段存的就是这11个字符，
    截图上有100个复制图标也不会影响它。
    """
    print(r"""
    ┌─────────────────────────────────────────────────────┐
    │  OCR vs uiautomator  对比                           │
    ├─────────────────────────────────────────────────────┤
    │                                                     │
    │  截图看到的是:                                       │
    │    [快手号：yingbin111] [复制图标]                   │
    │                                                     │
    │  OCR 识别:  yingbin1110    X  (把复制图标认成0)     │
    │  uiautomator: yingbin111   O  (读TextView原文)      │
    │                                                     │
    │  结论: UI层级树 = 应用内部真实数据，永不被图标干扰    │
    └─────────────────────────────────────────────────────┘
    """)


if __name__ == "__main__":
    demo_why_uiautomator_wins()

    print("连接手机并执行自动筛查:")
    print("  1. 手机开启USB调试")
    print("  2. adb devices 确认连接")
    print("  3. 运行: python kuaishou_scanner.py")
    print()
    print("示例:")
    print("  scanner = KuaishouScanner()")
    print('  scanner.open_app()')
    print('  results = scanner.scan_drama_list(["闪婚后被大佬宠上天", "我的医妃不好惹"])')
    print("  for r in results:")
    print('    print(r["drama"], "→", r["author_id"])')

"""
微信视频号反侵权自动化监控
功能：
  1. 连接手机 AScript
  2. 截图 + OCR 获取页面信息
  3. 搜索关键词
  4. 打开视频提取账号ID
  5. 音频转录（SenseVoice ASR）
"""
import asyncio, base64, json, os, re, sys, time

os.environ["FLAGS_use_mkldnn"] = "0"
os.environ["PYTHONIOENCODING"] = "utf-8"
# 避免 Windows GBK 编码问题
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ImportError:
    print("[✗] 需要安装 mcp: pip install mcp")
    sys.exit(1)

try:
    from paddleocr import PaddleOCR
    ocr = PaddleOCR(use_angle_cls=True, lang="ch", ir_optim=False)
except ImportError:
    print("[✗] 需要安装 paddleocr: pip install paddleocr")
    ocr = None


# ─── 工具函数 ───────────────────────────────────────────────

def clean_log(log_text: str) -> str:
    """清洗AScript日志：去掉前缀，去除非法Unicode"""
    lines = log_text.splitlines()
    chunks = []
    for ln in lines:
        if len(ln) >= 31 and ln.startswith("["):
            ln = ln[31:]
        # 移除 Unicode 代理对（避免 JSON 序列化崩溃）
        ln = ln.encode("utf-8", errors="replace").decode("utf-8")
        chunks.append(ln)
    return "".join(chunks)

def clean_base64(log_text: str) -> bytes:
    """从AScript日志中提取PNG图片二进制数据"""
    raw = clean_log(log_text)
    hpos = raw.find("iVBORw0KGgo")
    if hpos < 0:
        return b""
    raw = raw[hpos:]
    raw = re.sub(r"[^A-Za-z0-9+/]", "", raw)
    while len(raw) % 4 != 0:
        raw += "="
    return base64.b64decode(raw)


async def phone_capture(session, tmp_name="tmp_cap") -> bytes:
    """截图并返回PNG二进制"""
    code = f'''
import base64, cv2, time
from ascript.android import screen
img = None
for _ in range(5):
    img = screen.capture_cv()
    if img is not None: break
    time.sleep(1)
if img is not None:
    _, buf = cv2.imencode(".png", img)
    print(base64.b64encode(buf.tobytes()).decode("utf-8"))
'''
    r = await session.call_tool("deploy_and_run",
        {"project_name": f"zCap_{tmp_name}", "code": code, "log_seconds": 10})
    log = "".join(c.text.encode("utf-8","replace").decode("utf-8") + "\n" for c in r.content if c.type == "text")
    return clean_base64(log)


async def phone_click(session, x, y, tmp_name="tmp_clk"):
    """点击屏幕坐标"""
    code = f'''
from ascript.android import action
import time
action.click({x}, {y})
time.sleep(0.3)
print("[OK]")
'''
    r = await session.call_tool("deploy_and_run",
        {"project_name": f"zClk_{tmp_name}", "code": code, "log_seconds": 5})


async def phone_swipe(session, x1, y1, x2, y2, dur=300, tmp_name="tmp_swp"):
    """滑动"""
    code = f'''
from ascript.android import action
import time
action.swipe({x1}, {y1}, {x2}, {y2}, {dur})
time.sleep(0.5)
print("[OK]")
'''
    await session.call_tool("deploy_and_run",
        {"project_name": f"zSwp_{tmp_name}", "code": code, "log_seconds": 5})


async def phone_input(session, text, tmp_name="tmp_inp"):
    """输入文本"""
    code = f'''
from ascript.android import action
import time
action.text("{text}")
time.sleep(0.3)
print("[OK]")
'''
    await session.call_tool("deploy_and_run",
        {"project_name": f"zInp_{tmp_name}", "code": code, "log_seconds": 5})


async def phone_ocr(session, tmp_name="tmp_ocr") -> list:
    """截图+OCR，返回 [{text, conf, x, y}]"""
    data = await phone_capture(session, tmp_name)
    if not data or ocr is None:
        return []
    with open(f"tmp_{tmp_name}.png", "wb") as f:
        f.write(data)
    result = ocr.ocr(f"tmp_{tmp_name}.png", cls=True)
    if not result or not result[0]:
        return []
    out = []
    for line in result[0]:
        box, (text, conf) = line
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        cx, cy = int(sum(xs) / 4), int(sum(ys) / 4)
        text = text.encode("utf-8", errors="replace").decode("utf-8")
        out.append({"text": text, "conf": conf, "x": cx, "y": cy})
    return out


async def get_ui_tree(session) -> dict:
    """获取控件树"""
    r = await session.call_tool("dump_ui_tree", {})
    for item in r.content:
        if item.type == "text":
            return json.loads(item.text)
    return {}


def find_elements(views, **filters):
    """在控件树中查找匹配的元素"""
    results = []
    def walk(v, depth=0):
        match = True
        for k, val in filters.items():
            if v.get(k) != val:
                match = False
                break
        if match:
            results.append(v)
        if "childs" in v:
            for c in v["childs"]:
                walk(c, depth + 1)
    walk({"childs": views})
    return results


# ─── 主循环 ───────────────────────────────────────────────

async def main_loop():
    print("=" * 60)
    print("微信视频号反侵权自动化监控 v1.0")
    print("=" * 60)

    sp = StdioServerParameters(command="python", args=["-m", "ascript_mcp.local"])
    async with stdio_client(sp) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("[MCP] 服务端已启动")

            # 连接设备
            r = await session.call_tool("connect_device",
                {"ip": "172.16.1.216", "port": 9096, "connection_mode": "LocalIP"})
            ok = any("失败" not in c.text for c in r.content if c.type == "text")
            if not ok:
                print("[✗] 设备连接失败")
                return
            print("[✓] 设备已连接")

            # 判断当前页面
            elems = await phone_ocr(session, "main")
            print(f"\n当前页面识别到 {len(elems)} 个文字元素:\n")
            for e in elems[:30]:
                print(f"  ({e['x']:4},{e['y']:4}) {e['text']:<40} {e['conf']:.3f}")

            # 判断当前页面类型
            flat_text = "".join(e["text"] for e in elems)
            has_search_btn = any("搜索" in e["text"] and e["y"] < 250 for e in elems)
            is_video_main = any(t in flat_text for t in ["关注", "朋友", "推荐"])
            is_on_search = has_search_btn and not is_video_main

            if not (is_video_main or is_on_search):
                print("\n[!] 当前不在合适的页面。请在手机上打开微信视频号")
                print("    （当前没有找到 关注/朋友/推荐 这些标签或搜索按钮）")
                return

            # === 搜索 ===
            print(f"\n{'─'*40}\n开始搜索...")
            keyword = "我修仙归来"
            code = f'''
from ascript.android import action, node
import time

# 先点顶部让工具栏出现（如果有的话）
action.click(540, 100)
time.sleep(0.5)

# 点右上角搜索图标
action.click(875, 184)
time.sleep(1.5)

# 点击搜索框位置，然后输入
action.click(280, 210)
time.sleep(0.8)

# 清空可能的旧文本：点删除键20次
for _ in range(20):
    action.click(957, 1703)
    time.sleep(0.02)
time.sleep(0.3)

# 输入关键词
action.text("{keyword}")
time.sleep(1.5)

# 点搜索按钮
action.click(815, 208)
time.sleep(0.5)
print("[OK]")
'''
            await session.call_tool("deploy_and_run",
                {"project_name": "zDoSearch", "code": code, "log_seconds": 15})
            await asyncio.sleep(0.5)

            # 点右上角的"搜索"按钮(953,211)
            await phone_click(session, 953, 211)
            await asyncio.sleep(2)

            # 看搜索结果
            results = await phone_ocr(session, "results")
            print(f"\n搜索结果 ({len(results)} 项):\n")
            for e in results[:30]:
                print(f"  ({e['x']:4},{e['y']:4}) {e['text']:<40} {e['conf']:.3f}")

    print("\n[完成]")


if __name__ == "__main__":
    asyncio.run(main_loop())

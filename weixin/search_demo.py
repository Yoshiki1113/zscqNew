"""
微信视频号搜索脚本 v2 - 处理所有页面状态
"""
import asyncio, base64, json, os, re, sys, time
os.environ["FLAGS_use_mkldnn"] = "0"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from paddleocr import PaddleOCR
ocr = PaddleOCR(use_angle_cls=True, lang="ch", ir_optim=False)

def clean_log(log_text):
    lines = log_text.splitlines()
    chunks = []
    for ln in lines:
        if len(ln) >= 31 and ln.startswith("["):
            ln = ln[31:]
        ln = ln.encode("utf-8", errors="replace").decode("utf-8")
        chunks.append(ln)
    return "".join(chunks)

def extract_png(log_text):
    raw = clean_log(log_text)
    hpos = raw.find("iVBORw0KGgo")
    if hpos < 0:
        return b""
    raw = raw[hpos:]
    raw = re.sub(r"[^A-Za-z0-9+/]", "", raw)
    while len(raw) % 4 != 0:
        raw += "="
    return base64.b64decode(raw)

def do_ocr(img_bytes):
    if not img_bytes or ocr is None:
        return []
    with open("_tmp_ocr.png", "wb") as f:
        f.write(img_bytes)
    r = ocr.ocr("_tmp_ocr.png", cls=True)
    if not r or not r[0]:
        return []
    out = []
    for line in r[0]:
        box, (txt, cf) = line
        out.append({"text": txt, "conf": cf, "x": int(sum(p[0] for p in box)/4), "y": int(sum(p[1] for p in box)/4)})
    return out

async def screen_state(session):
    """截图并识别"""
    code = """
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
"""
    r = await session.call_tool("deploy_and_run", {"project_name": "zSt", "code": code, "log_seconds": 10})
    log = "".join(c.text.encode("utf-8","replace").decode("utf-8")+"\n" for c in r.content if c.type=="text")
    return extract_png(log)

async def run_action(session, code, name="act"):
    """执行动作脚本"""
    r = await session.call_tool("deploy_and_run", {"project_name": f"zAct_{name}", "code": code, "log_seconds": 8})
    log = "".join(c.text.encode("utf-8","replace").decode("utf-8")+"\n" for c in r.content if c.type=="text")
    return clean_log(log)

async def main():
    sp = StdioServerParameters(command="python", args=["-m", "ascript_mcp.local"])
    async with stdio_client(sp) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await session.call_tool("connect_device", {"ip": "172.16.1.216", "port": 9096, "connection_mode": "LocalIP"})

            # 1. 看当前页面
            img = await screen_state(session)
            elems = do_ocr(img)
            texts = "".join(e["text"] for e in elems)
            is_main = "关注" in texts and "朋友" in texts and "推荐" in texts
            page_name = "主页" if is_main else "搜索页/其他"
            print(f"[页面] {page_name} ({len(elems)}元素)")

            # 2. 先回到主页（如果在搜索页的话）
            back_script = '''
from ascript.android import action, node
import time
# 点取消/返回按钮
cancel = node.Selector().text("取消").find()
if not cancel:
    cancel = node.Selector().text("返回").find()
if cancel:
    cancel.click()
    time.sleep(1)
else:
    # 坐标：点返回或取消
    action.click(100, 184)
    time.sleep(0.5)
    action.click(100, 184)
    time.sleep(1)
print("[BACK]")
'''
            await run_action(session, back_script, "back")
            await asyncio.sleep(1)

            # 3. 从主页搜索
            keyword = "我修仙归来"
            search_script = f'''
from ascript.android import action
import time

# 从主页点顶部（显示工具栏）
action.click(540, 100)
time.sleep(0.8)

# 点搜索图标
action.click(875, 184)
time.sleep(2.5)

# 点搜索框位置（键盘弹出后）
action.click(300, 210)
time.sleep(1)

# 清空 + 输入
for _ in range(30):
    action.click(957, 1703)
    time.sleep(0.02)
time.sleep(0.5)

action.text("{keyword}")
time.sleep(2)

# 点搜索
action.click(815, 208)
print("[DONE]")
'''
            await run_action(session, search_script, "search")
            await asyncio.sleep(2)

            # 3. 看结果
            img = await screen_state(session)
            elems = do_ocr(img)
            print(f"\n最终结果 ({len(elems)} 项):\n")
            for e in elems[:35]:
                print(f"  ({e['x']:4},{e['y']:4}) {e['text']:<45} {e['conf']:.3f}")

asyncio.run(main())

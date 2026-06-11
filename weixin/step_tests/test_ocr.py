"""
单步测试：测试 ascript 原生 OCR 识别能力
用法: python test_ocr.py
功能：
  1. 连接手机
  2. 在当前页面执行 OCR 全屏识别
  3. 输出识别到的所有文字及坐标
"""
import asyncio, json, os, re, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from ascript.android.screen import Ocr
import json

sys.stdout.reconfigure(encoding='utf-8')

PHONE_IP = "172.16.1.216"
PHONE_PORT = 9096


async def run_on_phone(session, code, log_sec=15):
    """通过 deploy_and_run 在手机端执行代码"""
    r = await session.call_tool("deploy_and_run", {
        "project_name": "zscqAndroid",
        "code": code,
        "log_seconds": log_sec,
    })
    out = {"log": "", "images": []}
    for item in r.content:
        if item.type == "text":
            out["log"] += item.text + "\n"
        elif item.type == "image":
            out["images"].append(item.data)
    return out


async def connect_device_auto(session):
    print(f"[连接] 尝试直连 {PHONE_IP}:{PHONE_PORT} ...")
    r = await session.call_tool("connect_device", {
        "ip": PHONE_IP, "port": PHONE_PORT, "connection_mode": "LocalIP",
    })
    ok = False
    for item in r.content:
        if item.type == "text":
            if "失败" not in item.text and "fail" not in item.text.lower():
                ok = True
    if ok:
        print("[连接] 直连成功")
        return True

    print("[连接] 直连失败，开始扫描设备...")
    r = await session.call_tool("scan_devices", {"port": PHONE_PORT})
    for item in r.content:
        if item.type == "text":
            for line in item.text.split("\n"):
                m = re.search(r"IP:\s*([\d.]+):(\d+)", line)
                if m:
                    ip2, port2 = m.group(1), int(m.group(2))
                    await session.call_tool("connect_device", {
                        "ip": ip2, "port": port2, "connection_mode": "LocalIP",
                    })
                    print(f"[连接] 扫描发现设备 {ip2}:{port2}")
                    return True
    return False


async def test_ocr_fullscreen(session):
    """全屏 OCR 识别测试"""
    print("\n[OCR] 开始全屏识别（PaddleOCR）...")
    print("[OCR] 请确保手机当前显示的是目标页面（如视频号播放页）")
    print("[OCR] 识别可能需要 2-5 秒...\n")

    code = '''
from ascript.android.screen import Ocr
import json

Ocr.set_engine("paddle")
results = Ocr.ocr()

output = []
for item in results:
    if isinstance(item, dict):
        text = item.get("text", "")
        if "box" in item:
            box = item["box"]
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            x, y = int(sum(xs)/len(xs)), int(sum(ys)/len(ys))
            w, h = max(xs) - min(xs), max(ys) - min(ys)
        else:
            x = item.get("x", item.get("center_x", 0))
            y = item.get("y", item.get("center_y", 0))
            w = item.get("w", 0)
            h = item.get("h", 0)
    elif isinstance(item, (list, tuple)) and len(item) >= 2:
        box = item[0]
        text_info = item[1]
        if isinstance(text_info, (list, tuple)):
            text = str(text_info[0])
        else:
            text = str(text_info)
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        x, y = int(sum(xs)/len(xs)), int(sum(ys)/len(ys))
        w, h = max(xs) - min(xs), max(ys) - min(ys)
    else:
        text = str(item)
        x = y = w = h = 0
    output.append({"text": text, "x": x, "y": y, "w": w, "h": h})

print("OCR_START")
print(json.dumps(output, ensure_ascii=False))
print("OCR_END")
'''
    out = await run_on_phone(session, code, log_sec=20)
    log = out['log']

    s = log.find("OCR_START")
    e = log.find("OCR_END")
    if s >= 0 and e > s:
        try:
            results = json.loads(log[s+9:e].strip())
            print(f"[OCR] 识别成功！共识别到 {len(results)} 个文字区域\n")
            print("=" * 70)
            print(f"{'文字内容':<30} {'x':>6} {'y':>6} {'w':>5} {'h':>5}")
            print("-" * 70)
            for r in results:
                text = r.get("text", "")
                x = r.get("x", 0)
                y = r.get("y", 0)
                w = r.get("w", 0)
                h = r.get("h", 0)
                # 截断过长的文字
                display_text = text[:28] + "..." if len(text) > 30 else text
                print(f"{display_text:<30} {x:>6} {y:>6} {w:>5} {h:>5}")
            print("=" * 70)
            return results
        except Exception as ex:
            print(f"[OCR] JSON 解析失败: {ex}")
            print(f"[OCR] 原始日志:\n{log}")
    else:
        print("[OCR] 未在日志中找到 OCR 结果标记")
        print(f"[OCR] 原始日志:\n{log}")
    return []


async def main():
    sp = StdioServerParameters(command="python", args=["-m", "ascript_mcp.local"])
    async with stdio_client(sp) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("[MCP] 服务端已启动\n")

            if not await connect_device_auto(session):
                print("[✗] 未找到设备")
                return

            results = await test_ocr_fullscreen(session)

            if results:
                print(f"\n[完成] OCR 测试成功，共 {len(results)} 条结果")
                # 额外统计
                nums = [r for r in results if re.match(r'^[\d\.]+[万w]?$', r.get("text", ""))]
                if nums:
                    print(f"[统计] 识别到 {len(nums)} 个数字/计数: {', '.join(n['text'] for n in nums[:10])}")
            else:
                print("\n[✗] OCR 测试失败，请检查 ascript OCR 模块是否正常")


if __name__ == "__main__":
    asyncio.run(main())

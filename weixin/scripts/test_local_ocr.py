"""
本地 PaddleOCR 测试脚本（v3：修复截图 + PaddleX 缓存权限）
功能：
  1. 通过 AScript screen.capture_cv() 截图
  2. 使用本地 zscq 环境中的 paddleocr 识别截图文字
用法: python test_local_ocr.py
"""
import asyncio, base64, json, os, re, sys, time

# PaddlePaddle 2.6.2 + ir_optim=False 避免 OneDNN fused_conv2d bug

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.stdout.reconfigure(encoding='utf-8')

PHONE_IP = "172.16.1.216"
PHONE_PORT = 9096
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEST_IMG = os.path.join(BASE_DIR, "screenshots", "test_for_ocr.png")


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
        print("[连接] 直连成功\n")
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
                    print(f"[连接] 扫描发现设备 {ip2}:{port2}\n")
                    return True
    return False


async def capture_via_screencap(session, local_path):
    """截图：写入文件 + 读取，避免日志混合"""
    print("[截图] 使用 AScript screen.capture_cv() 截图...")
    stamp = str(int(time.time()))

    # Step 1: 截图 + 写文件
    code1 = f'''
import cv2, base64, os, time
from ascript.android import screen

img = None
for _ in range(5):
    img = screen.capture_cv()
    if img is not None:
        break
    time.sleep(1)
if img is None:
    print("[ERR] capture_cv None")
else:
    _, buf = cv2.imencode(".png", img)
    b64 = base64.b64encode(buf.tobytes()).decode("utf-8")
    with open(os.path.join(os.environ["HOME"], "zscq_tmp_{stamp}.txt"), "w") as f:
        f.write(b64)
    print("[OK] saved")
'''
    await session.call_tool("deploy_and_run", {
        "project_name": f"zscqTmp_{stamp}", "code": code1, "log_seconds": 10,
    })

    # Step 2: 读文件
    code2 = f'''
import os
with open(os.path.join(os.environ["HOME"], "zscq_tmp_{stamp}.txt"), "r") as f:
    print(f.read().strip())
'''
    r2 = await session.call_tool("deploy_and_run", {
        "project_name": f"zscqTmp_{stamp}2", "code": code2, "log_seconds": 10,
    })

    log_text = ""
    for item in r2.content:
        if item.type == "text":
            log_text += item.text + "\n"

    # 每行格式 [INFO] YYYY-MM-DD HH:MM:SS:mmm 后跟实际内容
    # 切掉固定前缀 "[INFO] YYYY-MM-DD HH:MM:SS:mmm " = 31 字符
    lines = log_text.splitlines()
    b64_chunks = []
    for ln in lines:
        if ln.startswith("[") and len(ln) > 31:
            ln = ln[31:]
        b64_chunks.append(ln)
    b64_data = "".join(b64_chunks)

    # 定位 PNG 头
    png_header = "iVBORw0KGgo"
    hpos = b64_data.find(png_header)
    if hpos >= 0:
        b64_data = b64_data[hpos:]
        # 调试：去掉前缀后，前100字符什么样子
        print(f"[调试] 去前缀后前100: {b64_data[:100]}")
        print(f"[调试] 长度={len(b64_data)}, 模4={len(b64_data)%4}")
        b64_data = re.sub(r'[^A-Za-z0-9+/]', '', b64_data)
        print(f"[调试] 过滤后长度={len(b64_data)}, 模4={len(b64_data)%4}")
        while len(b64_data) % 4 != 0:
            b64_data += "="
        data = base64.b64decode(b64_data)
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, "wb") as f:
            f.write(data)
        print(f"[截图] 已保存到 {local_path} ({len(data):,} bytes)\n")
        return True
    else:
        print(f"[截图] 失败，日志前200字: {log_text[:200]}")
        return False


def test_local_paddleocr(image_path):
    """使用本地 paddleocr 识别图片"""
    print("=" * 60)
    print("【本地 PaddleOCR 识别】")
    print("=" * 60)

    try:
        from paddleocr import PaddleOCR
    except ImportError:
        print("[✗] 本地未安装 paddleocr，请运行: pip install paddleocr")
        return []

    print("[OCR] 正在初始化 PaddleOCR（首次加载模型可能需要几十秒）...")
    ocr = PaddleOCR(use_angle_cls=True, lang="ch", ir_optim=False)

    print(f"[OCR] 开始识别图片: {image_path}")
    result = ocr.ocr(image_path, cls=True)

    if not result or not result[0]:
        print("[OCR] 未识别到任何文字")
        return []

    print(f"[OCR] 识别成功！共 {len(result[0])} 个文字区域\n")
    print(f"{'文字内容':<30} {'置信度':>8}")
    print("-" * 60)

    outputs = []
    for line in result[0]:
        box = line[0]
        text_info = line[1]
        text = text_info[0]
        confidence = text_info[1]
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        cx, cy = int(sum(xs)/len(xs)), int(sum(ys)/len(ys))
        display_text = text[:28] + "..." if len(text) > 30 else text
        print(f"{display_text:<30} {confidence:>8.3f}")
        outputs.append({"text": text, "confidence": confidence, "x": cx, "y": cy})

    print("=" * 60)
    return outputs


async def main():
    sp = StdioServerParameters(command="python", args=["-m", "ascript_mcp.local"])
    async with stdio_client(sp) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("[MCP] 服务端已启动\n")

            if not await connect_device_auto(session):
                print("[✗] 未找到设备")
                return

            ok = await capture_via_screencap(session, TEST_IMG)
            if not ok:
                return

    results = test_local_paddleocr(TEST_IMG)

    if results:
        print(f"\n[完成] 共识别 {len(results)} 条文字")
        nums = [r for r in results if re.match(r'^[\d\.]+[万w]?$', r["text"])]
        if nums:
            print(f"[统计] 数字/计数: {', '.join(n['text'] for n in nums[:10])}")
    else:
        print("\n[✗] 识别失败或无结果")


if __name__ == "__main__":
    asyncio.run(main())

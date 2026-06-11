"""
单步测试：在视频播放页使用 OCR 读取信息 → 截图 → 可选进入博主主页 OCR
用法: python test_read_video_info.py
"""
import asyncio, base64, json, os, re, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.stdout.reconfigure(encoding='utf-8')

PHONE_IP = "172.16.1.216"
PHONE_PORT = 9096
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCREENSHOT_DIR = os.path.join(BASE_DIR, "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)


async def run_on_phone(session, code, log_sec=15):
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


async def ocr_recognize(session, engine="paddle"):
    """在手机端执行 OCR 全屏识别"""
    code = f'''
from ascript.android.screen import Ocr
import json

Ocr.set_engine("{engine}")
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
    output.append({{"text": text, "x": x, "y": y, "w": w, "h": h}})

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
            return json.loads(log[s+9:e].strip())
        except Exception:
            pass
    return []


def parse_video_info(ocr_results):
    """从 OCR 结果解析视频号播放页信息"""
    info = {
        "作者名": "",
        "发布时间": "",
        "播放量": "",
        "喜欢数": "",
        "评论数": "",
        "收藏数": "",
        "分享数": "",
    }
    blogger_name = ""

    if not ocr_results:
        return info, blogger_name

    sorted_results = sorted(ocr_results, key=lambda r: r.get("y", 0))

    # 作者名
    for r in sorted_results:
        text = r.get("text", "").strip()
        y = r.get("y", 0)
        if 100 < y < 500 and 2 <= len(text) <= 20:
            if not re.match(r'^[\d\.]+[万w]?$', text) and text not in {"微信", "返回"}:
                info["作者名"] = text
                blogger_name = text
                break

    # 右侧互动数字
    right_nums = []
    for r in ocr_results:
        text = r.get("text", "").strip()
        x = r.get("x", 0)
        y = r.get("y", 0)
        if x > 800 and 800 < y < 2200:
            if re.match(r'^[\d\.]+[万w]?$', text):
                right_nums.append({"text": text, "y": y})

    right_nums.sort(key=lambda n: n["y"])
    labels = ["喜欢数", "评论数", "分享数", "收藏数"]
    for i, item in enumerate(right_nums[:4]):
        info[labels[i]] = item["text"]

    # 发布时间
    for r in sorted_results:
        text = r.get("text", "")
        if re.search(r'(小时前|天前|分钟前|昨天|刚刚|\d{4}-\d{2}-\d{2})', text):
            info["发布时间"] = text
            break

    # 播放量
    for r in ocr_results:
        text = r.get("text", "")
        if "播放" in text or re.match(r'^[\d\.]+[万w]?次$', text):
            info["播放量"] = text
            break

    return info, blogger_name


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


async def main():
    sp = StdioServerParameters(command="python", args=["-m", "ascript_mcp.local"])
    async with stdio_client(sp) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("[MCP] 服务端已启动\n")

            if not await connect_device_auto(session):
                print("[✗] 未找到设备")
                return

            # 第一步：OCR 读取播放页信息
            print("=" * 60)
            print("【步骤 1】OCR 读取视频播放页信息...")
            print("=" * 60)
            ocr_results = await ocr_recognize(session)
            print(f"\n[OCR] 共识别到 {len(ocr_results)} 个文字区域")

            info_data, blogger_name = parse_video_info(ocr_results)
            print("\n[解析] 视频信息:")
            for k, v in info_data.items():
                print(f"  {k}: {v}")
            print(f"\n[推断] 博主名称: {blogger_name!r}")

            # 第二步：截图
            print("\n" + "=" * 60)
            print("【步骤 2】截取当前播放页...")
            print("=" * 60)
            shot = await session.call_tool("screen_capture", {})
            for item in shot.content:
                if item.type == "image":
                    data = base64.b64decode(item.data)
                    ts = int(asyncio.get_event_loop().time() * 1000) % 10000
                    filename = f"test_video_info_{ts}.png"
                    path = os.path.join(SCREENSHOT_DIR, filename)
                    with open(path, "wb") as f:
                        f.write(data)
                    print(f"      已保存 {filename} ({len(data):,} bytes)")
                    break

            # 第三步：点击博主头像区（左上角）
            print("\n" + "=" * 60)
            print("【步骤 3】点击博主区域进入主页...")
            print("=" * 60)
            ux, uy = 160, 460
            print(f"[点击] 使用兜底坐标: ({ux}, {uy})")

            out = await run_on_phone(session, f"""
import time
from ascript.android import action
action.click({ux}, {uy})
time.sleep(1.0)
print("[OK] PROFILE_CLICKED")
""", log_sec=3)
            print(f"      日志: {out['log'].strip()}")
            await asyncio.sleep(2.0)

            # 第四步：OCR 读取博主主页
            print("\n" + "=" * 60)
            print("【步骤 4】OCR 读取博主主页信息...")
            print("=" * 60)
            ocr_results2 = await ocr_recognize(session)
            print(f"[OCR] 共识别到 {len(ocr_results2)} 个文字区域")

            sorted_results = sorted(ocr_results2, key=lambda r: r.get("y", 0))
            skip_words = {"微信", "返回", "关注", "粉丝", "获赞", "视频", "作品", "动态"}
            valid = [r for r in sorted_results
                     if len(r.get("text", "").strip()) >= 2
                     and r.get("text") not in skip_words]

            if valid:
                p_name = valid[0].get("text", "")
                print(f"\n  [推断] 博主名称: {p_name}")
                if len(valid) > 1:
                    p_id = valid[1].get("text", "")
                    print(f"  [推断] 账号: {p_id}")
            else:
                print("  [判断] 未识别到博主主页信息")

            print("\n[完成] 测试结束")


if __name__ == "__main__":
    asyncio.run(main())

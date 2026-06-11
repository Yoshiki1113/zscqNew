"""
单步测试：在视频播放页读取信息（鲁棒版）→ 截图 → 点击博主 ID → 判断页面并输出 UI 树
用法: python test_read_video_info.py
"""
import asyncio, base64, json, os, re, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.stdout.reconfigure(encoding='utf-8')

PHONE_IP = "172.16.1.139"
PHONE_PORT = 9096
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCREENSHOT_DIR = os.path.join(BASE_DIR, "screenshots")
JSONS_DIR = os.path.join(BASE_DIR, "jsons")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)
os.makedirs(JSONS_DIR, exist_ok=True)

# 快手播放页数字为 0 时的提示语文本
ZERO_HINTS = {"鼓励一下", "收藏", "分享", "抢首评"}


def safe_filename(text):
    """清理文件名中的非法字符"""
    if not text:
        return "unknown"
    text = text.replace(" ", "_").replace("/", "_").replace("\\", "_")
    text = text.replace(":", "_").replace("*", "_").replace("?", "_")
    text = text.replace('"', "_").replace("<", "_").replace(">", "_").replace("|", "_")
    return text[:50]


async def run_on_phone(session, code, log_sec=5):
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


async def get_ui_tree(session):
    r = await session.call_tool("dump_ui_tree", {"mode": 0})
    for item in r.content:
        if item.type == "text":
            return json.loads(item.text)
    return {}


def find_visible_by_id(nodes, target_id, min_y=500, max_y=2800):
    """按 id 子串查找节点，只返回 y 在可见范围内的第一个匹配"""
    def walk(nlist):
        for n in nlist:
            nid = n.get("id", "") or ""
            cy = n.get("center_y")
            if target_id in nid and cy is not None and min_y <= cy <= max_y:
                return n
            childs = n.get("childs", [])
            if childs:
                r = walk(childs)
                if r:
                    return r
        return None
    return walk(nodes)


def parse_count(text):
    """解析数字字段，0 时显示提示语则返回 0"""
    if not text or text in ZERO_HINTS:
        return "0"
    return text


def print_ui_tree(nodes, max_depth=5, max_nodes=200):
    printed = [0]
    def _print(n, d=0):
        if d > max_depth or printed[0] >= max_nodes:
            return
        printed[0] += 1
        indent = "  " * d
        t = n.get("text", "") or ""
        i = n.get("id", "") or ""
        ty = n.get("type", "") or ""
        c = n.get("clickable", False)
        cx = n.get("center_x")
        cy = n.get("center_y")
        info = []
        if t: info.append(f'text="{t}"')
        if i: info.append(f'id="{i}"')
        if ty: info.append(f'type={ty}')
        info.append(f'clickable={c}')
        if cx is not None: info.append(f'x={cx},y={cy}')
        print(f"{indent}|- {' | '.join(info)}")
        for child in n.get("childs", []):
            _print(child, d + 1)
    for node in nodes:
        _print(node)


async def capture_to_local(session, prefix="capture"):
    shot = await session.call_tool("screen_capture", {})
    for item in shot.content:
        if item.type == "image":
            data = base64.b64decode(item.data)
            ts = int(asyncio.get_event_loop().time() * 1000) % 10000
            filename = f"{prefix}_{ts}.png"
            path = os.path.join(SCREENSHOT_DIR, filename)
            with open(path, "wb") as f:
                f.write(data)
            print(f"[截图] 已保存 {filename} ({len(data):,} bytes)")
            return filename
    print("[截图] 未收到图片数据")
    return None


async def capture_series(session, keyword, blogger_name, count=10, interval=1.0):
    """连续截图 count 张，按命名规则保存"""
    safe_kw = safe_filename(keyword)
    safe_name = safe_filename(blogger_name)
    saved = []
    print(f"\n[截图] 开始连续截图 {count} 张，间隔 {interval}s")
    for i in range(1, count + 1):
        await asyncio.sleep(interval)
        shot = await session.call_tool("screen_capture", {})
        for item in shot.content:
            if item.type == "image":
                data = base64.b64decode(item.data)
                ts = int(asyncio.get_event_loop().time() * 1000)
                filename = f"vedio_{safe_kw}_{safe_name}_{i:02d}_{ts}_kuaishou.png"
                path = os.path.join(SCREENSHOT_DIR, filename)
                with open(path, "wb") as f:
                    f.write(data)
                saved.append(filename)
                print(f"  [{i}/{count}] {filename} ({len(data):,} bytes)")
                break
        else:
            print(f"  [{i}/{count}] 未收到图片数据，跳过")
    print(f"[截图] 共保存 {len(saved)} 张 → {SCREENSHOT_DIR}")
    return saved


def save_video_info(keyword, record):
    """将视频信息追加到 jsons/关键词_kuaishou.json（JSON 数组）"""
    safe_kw = safe_filename(keyword)
    json_path = os.path.join(JSONS_DIR, f"{safe_kw}_kuaishou.json")
    data = []
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                data = []
        except Exception:
            data = []
    data.append(record)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[JSON] 已保存到 {json_path} (共 {len(data)} 条记录)")
    return json_path


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


async def main():
    # 从命令行获取搜索关键词
    keyword = sys.argv[1] if len(sys.argv) > 1 else "闪婚后被大佬宠上天"

    sp = StdioServerParameters(command="python", args=["-m", "ascript_mcp.local"])
    async with stdio_client(sp) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("[MCP] 服务端已启动\n")

            if not await connect_device_auto(session):
                print("[✗] 未找到设备")
                return

            # ========== 第一步：获取 UI 树并判断页面 ==========
            print("\n" + "=" * 60)
            print("【步骤 1】获取页面并判断是否在播放页")
            print("=" * 60)
            ui = await get_ui_tree(session)
            views = ui.get('data', {}).get('views', [])
            # print_ui_tree(views, max_depth=5, max_nodes=200)  # UI 树输出已注释
            # print("=" * 60)

            user_node = find_visible_by_id(views, "user_name_text_view")
            if user_node:
                print(f"\n[判断] 当前在视频播放页，博主: {user_node.get('text','')!r}")
            else:
                print("\n[判断] 未识别到播放页特征节点")

            # ========== 第二步：采集信息 ==========
            print("\n" + "=" * 50)
            print("【步骤 2】采集视频信息：")
            print("=" * 50)
            fields = {
                "ID名称": "user_name_text_view",
                "发布时间": "create_date_tv",
                "播放量": "information_tube_description",
                "喜欢数": "like_count_view",
                "评论数": "comment_count_view2",
                "收藏数": "collect_text",
                "分享数": "forward_count",
            }
            info_data = {}
            for label, id_sub in fields.items():
                node = find_visible_by_id(views, id_sub)
                if node:
                    text = node.get("text", "")
                    if label in ("喜欢数", "评论数", "收藏数", "分享数"):
                        text = parse_count(text)
                    info_data[label] = text
                    print(f"  {label}: {text}")
                else:
                    info_data[label] = "[未找到]"
                    print(f"  {label}: [未找到]")
            print("=" * 50)

            # ========== 第三步：原单张截图已移除，改为返回后连续截图 ==========

            # ========== 第四步：点击博主 ID ==========
            print("\n【步骤 4】点击博主 ID...")
            if user_node and user_node.get("center_x") and user_node.get("center_y"):
                ux, uy = user_node["center_x"], user_node["center_y"]
                print(f"[点击] 博主 ID 坐标: ({ux}, {uy}) text={user_node.get('text','')!r}")
                out = await run_on_phone(session, f"""
import time
from ascript.android import action
action.click({ux}, {uy})
time.sleep(0.8)
print("[OK] USER_ID_CLICKED")
""", log_sec=3)
                print(f"[点击] 日志: {out['log'].strip()}")
            else:
                print("[✗] 未找到博主 ID 节点")

            print("[点击] 等待页面加载...")
            await asyncio.sleep(2.0)

            # ========== 第五步：判断页面是否在博主主页 ==========
            print("\n" + "=" * 60)
            print("【步骤 5】判断是否在博主主页")
            print("=" * 60)
            ui2 = await get_ui_tree(session)
            views2 = ui2.get('data', {}).get('views', [])
            # print_ui_tree(views2, max_depth=5, max_nodes=200)  # UI 树输出已注释
            # print("=" * 60)

            profile_name = find_visible_by_id(views2, "user_name_tv")
            kwai_id = find_visible_by_id(views2, "profile_user_kwai_id")
            user_name2 = find_visible_by_id(views2, "user_name_text_view")

            blogger_name = "unknown"
            p_name = ""
            p_id = ""
            if profile_name or kwai_id:
                p_name = profile_name.get('text','') if profile_name else '[未找到]'
                p_id = kwai_id.get('text','').replace('快手号：','') if kwai_id else '[未找到]'
                blogger_name = p_name
                print(f"\n[判断] 已进入博主主页")
                print(f"       博主名称: {p_name}")
                print(f"       快手号: {p_id}")
            elif user_name2:
                blogger_name = user_name2.get('text','')
                print(f"\n[判断] 仍在视频播放页，博主: {blogger_name!r}")
            else:
                print("\n[判断] 页面已变化，未识别到特征节点")

            # ========== 第六步：返回上一页 ==========
            print("\n" + "=" * 60)
            print("【步骤 6】点击左上角返回按钮...")
            print("=" * 60)

            bx, by = 109, 212
            out = await run_on_phone(session, f"""
import time
from ascript.android import action
action.click({bx}, {by})
time.sleep(1.0)
print("[OK] BACK_CLICKED")
""", log_sec=3)
            print(f"[返回] 日志: {out['log'].strip()}")
            print("[返回] 等待页面切换...")
            await asyncio.sleep(1.5)

            # 确认是否回到播放页（UI 树输出已注释）
            print("\n【步骤 6-2】确认返回后页面状态")
            # print("=" * 60)
            ui3 = await get_ui_tree(session)
            views3 = ui3.get('data', {}).get('views', [])
            # print_ui_tree(views3, max_depth=4, max_nodes=100)
            # print("=" * 60)

            user_name3 = find_visible_by_id(views3, "user_name_text_view")
            profile_name3 = find_visible_by_id(views3, "user_name_tv")
            if user_name3:
                print(f"\n[判断] 已回到视频播放页，博主: {user_name3.get('text','')!r}")
            elif profile_name3:
                print(f"\n[判断] 仍在博主主页: {profile_name3.get('text','')!r}")
            else:
                print("\n[判断] 页面状态不明")

            # ========== 第七步：返回后连续截图 10 张 ==========
            print("\n" + "=" * 60)
            print("【步骤 7】连续截图 10 张（间隔 1 秒）")
            print("=" * 60)
            screenshots = await capture_series(
                session, keyword=keyword, blogger_name=blogger_name,
                count=10, interval=1.0
            )

            # ========== 第八步：保存 JSON 信息 ==========
            from datetime import datetime
            p_name_val = p_name if profile_name or kwai_id else ""
            p_id_val = p_id if profile_name or kwai_id else ""
            record = {
                "search_keyword": keyword,
                "capture_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "blogger_name": blogger_name,
                "kwai_id": p_id_val,
                "video_info": {
                    "blogger_name": info_data.get("ID名称", ""),
                    "publish_time": info_data.get("发布时间", ""),
                    "play_count": info_data.get("播放量", ""),
                    "like_count": info_data.get("喜欢数", ""),
                    "comment_count": info_data.get("评论数", ""),
                    "collect_count": info_data.get("收藏数", ""),
                    "share_count": info_data.get("分享数", ""),
                },
                "profile_info": {
                    "blogger_name": p_name_val,
                    "kwai_id": p_id_val,
                },
                "screenshots": screenshots,
            }
            json_path = save_video_info(keyword, record)

            print("\n[完成] 测试结束")
            print(f"[完成] 截图保存目录: {SCREENSHOT_DIR}")
            print(f"[完成] JSON 文件: {json_path}")


if __name__ == "__main__":
    asyncio.run(main())

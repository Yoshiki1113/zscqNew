"""
AScript MCP 截图+搜索管线
功能：PC 连接手机 → 搜索关键词 → 截图 → 保存到本地 screenshots/
用法：
  python main.py                     # 纯截图 5 张
  python main.py search <关键词>      # 搜索关键词后截图
  python main.py search <关键词> <张数>
"""
import asyncio, base64, json, os, re, sys, time
from datetime import datetime
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.stdout.reconfigure(encoding='utf-8')

# ========== 配置 ==========
PHONE_IP = "172.16.0.181"
PHONE_PORT = 9096
KUAISHOU_PACKAGE = "com.kuaishou.nebula/com.yxcorp.gifshow.HomeActivity"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCREENSHOT_DIR = os.path.join(BASE_DIR, "screenshots")
JSONS_DIR = os.path.join(BASE_DIR, "jsons")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)
os.makedirs(JSONS_DIR, exist_ok=True)

ZERO_HINTS = {"鼓励一下", "收藏", "分享", "抢首评"}


# ========== MCP 辅助函数 ==========

async def run_on_phone(session, code, log_sec=10):
    """通过 deploy_and_run 在手机端执行代码，返回 {log, images}"""
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
    """获取当前界面的 UI 树"""
    r = await session.call_tool("dump_ui_tree", {"mode": 0})
    for item in r.content:
        if item.type == "text":
            return json.loads(item.text)
    return {}


def walk_ui(data, keyword=None, id_sub=None, clickable=None):
    """遍历 UI 树，按条件查找节点"""
    views = data.get("data", {}).get("views", [])
    res = []
    def walk(nodes, depth=0):
        for n in nodes:
            t = n.get("text", "") or ""
            i = n.get("id", "") or ""
            c = n.get("clickable", False)
            if depth > 0 or (t or i):
                ok = True
                if keyword and keyword not in t:
                    ok = False
                if id_sub and id_sub not in i:
                    ok = False
                if clickable is not None and c != clickable:
                    ok = False
                if ok and (t or i):
                    res.append({
                        "text": t, "id": i, "clickable": c,
                        "x": n.get("center_x"), "y": n.get("center_y"),
                        "type": n.get("type", ""),
                    })
            walk(n.get("childs", []), depth + 1)
    walk([{"childs": views}])
    return res


def find_tabs_container(data):
    """递归查找顶部 Tab 栏容器（id 包含 tabs 的 ScrollView / ViewGroup）"""
    views = data.get("data", {}).get("views", [])
    def walk(nodes):
        for n in nodes:
            nid = (n.get("id", "") or "").lower()
            ntype = n.get("type", "") or ""
            if "tabs" in nid and ("scroll" in ntype.lower() or "viewgroup" in ntype.lower() or ntype == "View"):
                return n
            childs = n.get("childs", [])
            if childs:
                r = walk(childs)
                if r:
                    return r
        return None
    return walk(views)


def get_clickable_children_by_parent(node):
    """获取某个节点下所有 clickable=True 的直接子节点（按 x 坐标排序）"""
    res = []
    for c in node.get("childs", []):
        if c.get("clickable", False):
            res.append(c)
    res.sort(key=lambda n: n.get("center_x", 0))
    return res


# ========== 设备连接 ==========

async def connect_device_auto(session):
    """先尝试指定 IP 直连，失败则 scan_devices 自动扫描发现"""
    print(f"[连接] 尝试直连 {PHONE_IP}:{PHONE_PORT} ...")
    r = await session.call_tool("connect_device", {
        "ip": PHONE_IP,
        "port": PHONE_PORT,
        "connection_mode": "LocalIP",
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


# ========== 快手操作 ==========

async def go_home(session):
    """通过 am start 强制跳回快手主页"""
    print("[导航] 跳转快手主页...")
    out = await run_on_phone(session, f"""
import subprocess, time
subprocess.run(['am', 'start', '-n', '{KUAISHOU_PACKAGE}'], timeout=5)
time.sleep(1.5)
print("[OK] HOME")
""", log_sec=3)
    print(f"[导航] {out['log'].strip()}")


async def search_keyword(session, keyword):
    """
    在快手搜索关键词：
    1. dump_ui_tree 找搜索按钮坐标
    2. 点击搜索按钮
    3. dump_ui_tree 找输入框坐标
    4. deploy_and_run：点击输入框 → 输入关键词 → 点键盘搜索 → 等待结果
    """
    print(f"\n[搜索] 关键词: {keyword}")

    # Step 1: 找搜索按钮
    ui = await get_ui_tree(session)
    search_btns = (
        walk_ui(ui, id_sub="top_search", clickable=True) or
        walk_ui(ui, id_sub="edit_btn", clickable=True) or
        walk_ui(ui, id_sub="thanos_home", clickable=True)
    )
    if search_btns:
        sx, sy = search_btns[0]['x'], search_btns[0]['y']
        print(f"[搜索] 找到搜索按钮: ({sx}, {sy}) id={search_btns[0]['id']}")
    else:
        sx, sy = 1158, 207
        print(f"[搜索] 未找到搜索按钮，使用兜底坐标: ({sx}, {sy})")

    # Step 2: 点击搜索按钮，进入搜索页
    await run_on_phone(session, f"""
import time
from ascript.android import action
action.click({sx}, {sy})
time.sleep(0.8)
print("[OK] SEARCH_BTN_CLICKED")
""", log_sec=2)

    # Step 3: 找输入框
    ui2 = await get_ui_tree(session)
    input_x, input_y = 400, 400  # 兜底
    views = ui2.get("data", {}).get("views", [])

    def find_edittext(nodes):
        for n in nodes:
            if n.get("type") == "EditText" and n.get("editable"):
                return n
            for c in n.get("childs", []):
                r = find_edittext([c])
                if r:
                    return r
        return None

    input_node = find_edittext(views)
    if input_node:
        input_x = input_node.get("center_x", input_x)
        input_y = input_node.get("center_y", input_y)
        print(f"[搜索] 找到输入框: ({input_x}, {input_y})")
    else:
        print(f"[搜索] 未找到输入框，使用兜底坐标: ({input_x}, {input_y})")

    # Step 4: 合并操作 —— 点输入框 → 输入关键词 → 多策略点搜索 → 等结果
    escaped_keyword = keyword.replace("'", "\\'")
    out = await run_on_phone(session, f"""
import time
from ascript.android import action
from ascript.android.node import Selector

# 点击输入框
action.click({input_x}, {input_y})
time.sleep(0.3)

# 输入关键词
action.input('{escaped_keyword}')
time.sleep(0.3)

# 策略1: 用 Selector 查找"搜索"按钮并点击（最可靠）
search_clicked = False
try:
    node = Selector().text("搜索").find()
    if node:
        node.click()
        search_clicked = True
        print("[OK] SEARCH_BY_SELECTOR")
except Exception as e:
    print(f"[~] Selector搜索失败: {{e}}")

if not search_clicked:
    # 策略2: 点击键盘右下角搜索键区域（常见布局）
    action.click(950, 2550)
    time.sleep(0.3)
    print("[~] SEARCH_BY_KEYBOARD_COORD")

# 等待搜索结果加载
time.sleep(2.0)
print("[OK] SEARCH_DONE")
""", log_sec=8)
    log_text = out['log'].strip()
    print(f"[搜索] 日志: {log_text}")
    if "SEARCH_BY_SELECTOR" in log_text:
        print("[搜索] 通过 Selector 成功点击搜索按钮")
    elif "SEARCH_BY_KEYBOARD_COORD" in log_text:
        print("[搜索] Selector 未找到搜索按钮，使用了键盘坐标兜底")

    # Step 5: 确认搜索结果已加载
    await asyncio.sleep(0.5)
    ui3 = await get_ui_tree(session)
    result_nodes = walk_ui(ui3, keyword=keyword)
    if result_nodes:
        print(f"[搜索] 搜索结果已加载，找到 {len(result_nodes)} 个含关键词的节点")
    else:
        print("[搜索] 未检测到搜索结果，可能仍在加载中")


async def switch_to_video_tab(session):
    """搜索完成后点击顶部'视频'Tab，切换至视频筛选页"""
    print("\n[视频Tab] 尝试切换到'视频'筛选页...")

    # Step 1: 通过 UI 树定位 tabs 容器，按索引取第 2 个 clickable 子节点（视频）
    ui = await get_ui_tree(session)
    tabs_node = find_tabs_container(ui)
    if tabs_node:
        children = get_clickable_children_by_parent(tabs_node)
        # print(f"[视频Tab] tabs 容器下 clickable 子节点共 {len(children)} 个")
        # for idx, c in enumerate(children, 1):
        #     cx, cy = c.get("center_x"), c.get("center_y")
        #     print(f"      [{idx}] ({cx}, {cy})")
        if len(children) >= 2:
            target = children[1]  # 第 2 个是"视频"
            tx, ty = target.get("center_x"), target.get("center_y")
            print(f"[视频Tab] 取第 2 个节点（视频）: ({tx}, {ty})")
        else:
            tx, ty = 364, 366
            print(f"[视频Tab] 节点不足，使用兜底坐标: ({tx}, {ty})")
    else:
        tx, ty = 364, 366
        print(f"[视频Tab] 未找到 tabs 容器，使用兜底坐标: ({tx}, {ty})")

    # Step 2: 点击视频Tab
    await run_on_phone(session, f"""
import time
from ascript.android import action
action.click({tx}, {ty})
time.sleep(0.8)
print("[OK] VIDEO_TAB_CLICKED")
""", log_sec=3)
    print("[视频Tab] 已点击，等待页面切换...")
    await asyncio.sleep(1.0)


async def click_first_video(session):
    """在视频列表页点击第一个视频卡片"""
    print("\n[视频] 尝试点击第一个视频...")

    ui = await get_ui_tree(session)
    views = ui.get("data", {}).get("views", [])

    # 精确找视频卡片：id 包含 container + type=RelativeLayout + x>100 + y 在合理范围
    candidates = []
    def walk(nodes):
        for n in nodes:
            if n.get("clickable", False):
                nid = n.get("id", "") or ""
                ntype = n.get("type", "") or ""
                cx = n.get("center_x")
                cy = n.get("center_y")
                if "container" in nid and ntype == "RelativeLayout" and cx and cx > 100 and cy and 500 < cy < 2500:
                    candidates.append(n)
            walk(n.get("childs", []))
    walk(views)

    # 按 y 升序，取最靠上的（第一个视频）
    candidates.sort(key=lambda n: n.get("center_y", 9999))
    if candidates:
        target = candidates[0]
        vx, vy = target.get("center_x"), target.get("center_y")
        print(f"[视频] 找到第一个视频卡片: ({vx}, {vy})")
    else:
        vx, vy = 319, 1086
        print(f"[视频] 未找到候选节点，使用兜底坐标: ({vx}, {vy})")

    await run_on_phone(session, f"""
import time
from ascript.android import action
action.click({vx}, {vy})
time.sleep(0.5)
print("[OK] FIRST_VIDEO_CLICKED")
""", log_sec=3)
    print("[视频] 已点击，等待播放页加载...")
    await asyncio.sleep(2.0)


# ========== 读信息辅助函数 ==========

def safe_filename(text):
    if not text:
        return "unknown"
    text = text.replace(" ", "_").replace("/", "_").replace("\\", "_")
    text = text.replace(":", "_").replace("*", "_").replace("?", "_")
    text = text.replace('"', "_").replace("<", "_").replace(">", "_").replace("|", "_")
    return text[:50]


def find_visible_by_id(nodes, target_id, min_y=500, max_y=2800):
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
    if not text or text in ZERO_HINTS:
        return "0"
    return text


def save_video_info(keyword, record):
    safe_kw = safe_filename(keyword)
    keyword_json_dir = os.path.join(JSONS_DIR, safe_kw)
    os.makedirs(keyword_json_dir, exist_ok=True)
    json_path = os.path.join(keyword_json_dir, f"{safe_kw}_kuaishou.json")
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


async def capture_series(session, keyword, blogger_name, screenshot_dir, count=10, interval=1.0):
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
                path = os.path.join(screenshot_dir, filename)
                with open(path, "wb") as f:
                    f.write(data)
                saved.append(filename)
                print(f"  [{i}/{count}] {filename} ({len(data):,} bytes)")
                break
        else:
            print(f"  [{i}/{count}] 未收到图片数据，跳过")
    print(f"[截图] 共保存 {len(saved)} 张 → {screenshot_dir}")
    return saved


# ========== 截图 ==========

async def capture_to_local(session, count=5, interval=0.8, prefix="capture"):
    """循环截图 count 张，base64 解码后保存到 screenshots/ 目录"""
    print(f"\n[截图] 开始，计划截图 {count} 张，间隔 {interval}s\n")
    saved = []
    for i in range(1, count + 1):
        await asyncio.sleep(interval)
        shot = await session.call_tool("screen_capture", {})
        for item in shot.content:
            if item.type == "image":
                data = base64.b64decode(item.data)
                ts = int(asyncio.get_event_loop().time() * 1000) % 10000
                filename = f"{prefix}_{i:02d}_{ts}.png"
                path = os.path.join(SCREENSHOT_DIR, filename)
                with open(path, "wb") as f:
                    f.write(data)
                saved.append((filename, len(data)))
                print(f"  [{i}/{count}] {filename} ({len(data):,} bytes)")
                break
        else:
            print(f"  [{i}/{count}] 未收到图片数据，跳过")

    print(f"\n[完成] 共保存 {len(saved)} 张截图 → {SCREENSHOT_DIR}")
    return saved


# ========== 主流程 ==========

async def run():
    sp = StdioServerParameters(command="python", args=["-m", "ascript_mcp.local"])

    print("=" * 50)
    print("  AScript MCP 截图+搜索管线")
    print("=" * 50)

    # 解析命令行
    mode = sys.argv[1] if len(sys.argv) > 1 else "capture"
    keyword = sys.argv[2] if len(sys.argv) > 2 else "闪婚后被大佬宠上天"
    count = int(sys.argv[3]) if len(sys.argv) > 3 else 5

    async with stdio_client(sp) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("[MCP] 服务端已启动\n")

            if not await connect_device_auto(session):
                print("[✗] 未找到可用设备，请确认：")
                print("      1. 手机 AScript App 已开启无障碍模式")
                print("      2. 手机与 PC 在同一 WiFi")
                return

            if mode == "search":
                # 搜索 + 循环采集 + 截图 完整流程
                print(f"\n模式: 搜索+循环采集+截图  关键词=\"{keyword}\"")

                # 按关键词创建截图目录
                safe_kw = safe_filename(keyword)
                keyword_screenshot_dir = os.path.join(SCREENSHOT_DIR, safe_kw)
                os.makedirs(keyword_screenshot_dir, exist_ok=True)

                # 1. 跳转快手主页
                await go_home(session)

                # 2. 搜索关键词
                await search_keyword(session, keyword)

                # 3. 切换到"视频"Tab
                await switch_to_video_tab(session)

                # 4. 点击第一个视频，进入播放页
                await click_first_video(session)

                # 循环采集每一个视频
                consecutive_no_change = 0  # 连续未变化计数
                prev_blogger_name = None
                video_index = 0

                while True:
                    video_index += 1
                    print(f"\n{'=' * 60}")
                    print(f"【第 {video_index} 个视频】")
                    print(f"{'=' * 60}")

                    # 5. 播放页读取信息
                    print("\n[采集] 读取视频信息...")
                    ui = await get_ui_tree(session)
                    views = ui.get("data", {}).get("views", [])
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

                    user_node = find_visible_by_id(views, "user_name_text_view")
                    current_blogger = user_node.get('text', '') if user_node else ''

                    # 判定是否上滑不动（连续3次无变化）
                    if current_blogger == prev_blogger_name:
                        consecutive_no_change += 1
                        print(f"[判定] 博主未变化: {current_blogger!r} (连续 {consecutive_no_change} 次)")
                        if consecutive_no_change >= 3:
                            print(f"\n[结束] 连续 3 次上滑无新视频，停止采集")
                            break
                    else:
                        consecutive_no_change = 0
                        print(f"[判定] 新视频博主: {current_blogger!r}")

                    prev_blogger_name = current_blogger

                    # 6. 点击博主 ID 进入主页（先尝试 UI 树定位，兜底固定坐标）
                    print("\n[操作] 尝试进入博主主页...")
                    ui_click = await get_ui_tree(session)
                    views_click = ui_click.get("data", {}).get("views", [])
                    avatar_node = find_visible_by_id(views_click, "slide_play_avatar_click_area")
                    if avatar_node:
                        ux, uy = avatar_node.get("center_x", 1159), avatar_node.get("center_y", 1055)
                        print(f"[点击] UI树找到头像点击区: ({ux}, {uy})")
                    else:
                        ux, uy = 1159, 1055
                        print(f"[点击] UI树未找到头像点击区，使用兜底坐标: ({ux}, {uy})")

                    out = await run_on_phone(session, f"""
import time
from ascript.android import action
action.click({ux}, {uy})
time.sleep(0.8)
print("[OK] USER_ID_CLICKED")
""", log_sec=3)
                    print(f"[点击] 日志: {out['log'].strip()}")

                    print("[点击] 等待页面加载...")
                    await asyncio.sleep(2.0)

                    # 检查是否成功进入博主页
                    ui_check = await get_ui_tree(session)
                    views_check = ui_check.get("data", {}).get("views", [])
                    profile_name_check = find_visible_by_id(views_check, "user_name_tv")
                    kwai_id_check = find_visible_by_id(views_check, "profile_user_kwai_id")
                    if not profile_name_check and not kwai_id_check:
                        print("[点击] 未识别到博主主页特征，再次尝试固定坐标 (1159, 1055)...")
                        out2 = await run_on_phone(session, """
import time
from ascript.android import action
action.click(1159, 1055)
time.sleep(0.8)
print("[OK] USER_ID_CLICKED_RETRY")
""", log_sec=3)
                        print(f"[点击] 二次点击日志: {out2['log'].strip()}")
                        await asyncio.sleep(2.0)
                    else:
                        print("[点击] 已成功进入博主主页")

                    # 7. 读取博主主页信息
                    print("\n[采集] 读取博主主页信息...")
                    ui2 = await get_ui_tree(session)
                    views2 = ui2.get("data", {}).get("views", [])

                    profile_name = find_visible_by_id(views2, "user_name_tv")
                    kwai_id = find_visible_by_id(views2, "profile_user_kwai_id")

                    blogger_name = current_blogger
                    p_name = ""
                    p_id = ""
                    if profile_name or kwai_id:
                        p_name = profile_name.get('text','') if profile_name else '[未找到]'
                        p_id = kwai_id.get('text','').replace('快手号：','') if kwai_id else '[未找到]'
                        blogger_name = p_name
                        print(f"  博主名称: {p_name}")
                        print(f"  快手号: {p_id}")
                    else:
                        print("  [判断] 未识别到博主主页特征节点")

                    # 8. 返回播放页
                    print("\n[操作] 返回播放页...")
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

                    # 9. 返回后连续截图 10 张
                    print(f"\n[截图] 第 {video_index} 个视频连续截图 10 张...")
                    screenshots = await capture_series(
                        session, keyword=keyword, blogger_name=blogger_name,
                        screenshot_dir=keyword_screenshot_dir,
                        count=10, interval=1.0
                    )

                    # 10. 保存 JSON
                    p_name_val = p_name if profile_name or kwai_id else current_blogger
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

                    # 11. 上滑加载下一个视频
                    print(f"\n[上滑] 加载第 {video_index + 1} 个视频...")
                    out = await run_on_phone(session, """
import time
from ascript.android import action
action.slide(600, 2200, 600, 800, 300)
time.sleep(2.0)
print("[OK] SWIPE_UP_DONE")
""", log_sec=5)
                    print(f"[上滑] 日志: {out['log'].strip()}")
                    print("[上滑] 等待页面切换...")
                    await asyncio.sleep(2.0)

                print("\n[完成] 完整流程结束")
                print(f"[完成] 截图目录: {keyword_screenshot_dir}")
                print(f"[完成] JSON 文件: {json_path}")

            else:
                # 纯截图模式（保持原有功能）
                print(f"\n模式: 纯截图  张数={count}")

                # 预热
                print("[截图] 预热截图 1 张...")
                warmup = await session.call_tool("screen_capture", {})
                for item in warmup.content:
                    if item.type == "image":
                        data = base64.b64decode(item.data)
                        path = os.path.join(SCREENSHOT_DIR, "capture_warmup.png")
                        with open(path, "wb") as f:
                            f.write(data)
                        print(f"      预热 OK ({len(data):,} bytes)\n")
                        break

                # 正式截图
                await capture_to_local(session, count=count)


if __name__ == "__main__":
    asyncio.run(run())

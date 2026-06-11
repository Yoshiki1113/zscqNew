"""
快手短剧筛查 v3 - 去掉了自动启动快手，由用户提前打开
"""
import asyncio, json, re, sys, base64, os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.stdout.reconfigure(encoding='utf-8')

DRAMA_LIST = ["闪婚后被大佬宠上天", "我的医妃不好惹"]

async def run(session, code, log_sec=12):
    r = await session.call_tool("deploy_and_run", {
        "project_name": "zscqAndroid",
        "code": code,
        "log_seconds": log_sec
    })
    out = {"log": "", "images": []}
    for item in r.content:
        if item.type == "text":
            out["log"] += item.text + "\n"
        elif item.type == "image":
            out["images"].append(item.data)
    return out

async def ui_tree(session):
    r = await session.call_tool("dump_ui_tree", {"mode": 0})
    for item in r.content:
        if item.type == "text":
            return json.loads(item.text)
    return {}

def walk_ui(data, keyword=None, id_sub=None, clickable=None):
    views = data.get("data", {}).get("views", [])
    res = []
    def walk(nodes, depth=0):
        for n in nodes:
            t = n.get("text", "") or ""
            i = n.get("id", "") or ""
            c = n.get("clickable", False)
            if depth > 0 or (t or i):
                ok = True
                if keyword and keyword not in t: ok = False
                if id_sub and id_sub not in i: ok = False
                if clickable is not None and c != clickable: ok = False
                if ok and (t or i):
                    res.append({
                        "text": t, "id": i, "clickable": c,
                        "x": n.get("center_x"), "y": n.get("center_y"),
                        "type": n.get("type", "")
                    })
            walk(n.get("childs", []), depth + 1)
    walk([{"childs": views}])
    return res

def tap(x, y, s=1):
    return f"""
import time
from ascript.android import action
action.click({x}, {y})
time.sleep({s})
"""

async def main():
    sp = StdioServerParameters(command="python", args=["-m", "ascript_mcp.local"])
    async with stdio_client(sp) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await session.call_tool("connect_device", {"ip": "172.16.1.139", "port": 9096, "connection_mode": "LocalIP"})

            print("=== 快手已打开，开始筛查 ===")

            for drama in DRAMA_LIST:
                print(f"\n{'='*50}")
                print(f"=== {drama} ===")

                # 1. 回到主页（用 am start 强制跳转，干净利落）
                print("[1] 回到主页")
                await run(session, """
import subprocess, time
subprocess.run(['am', 'start', '-n', 'com.kuaishou.nebula/com.yxcorp.gifshow.HomeActivity'], timeout=10)
time.sleep(4)
print("[OK] HOME")
""", 6)

                # 2. 点击搜索按钮
                print("[2] 点击搜索")
                ui = await ui_tree(session)
                # 搜索按钮的ID可能是 thanos_home_top_search 或 edit_btn
                search_btns = walk_ui(ui, id_sub="top_search", clickable=True) or \
                             walk_ui(ui, id_sub="edit_btn", clickable=True) or \
                             walk_ui(ui, id_sub="thanos_home", clickable=True)
                if search_btns:
                    btn = search_btns[0]
                    print(f"  搜索按钮: ({btn['x']}, {btn['y']})")
                    await run(session, tap(btn['x'], btn['y'], 3), 5)
                else:
                    print("  未找到搜索按钮，用坐标")
                    await run(session, tap(1158, 207, 3), 5)

                # 3. 输入搜索词
                print(f"[3] 输入: {drama}")
                await run(session, f"""
import time
from ascript.android import action
action.click(400, 400)
time.sleep(0.5)
action.input('{drama}')
time.sleep(1)
print("[OK] INPUT")
""", 8)

                # 4. 执行搜索（键盘搜索按钮）
                print("[4] 搜索")
                await run(session, tap(900, 500, 5), 8)

                # 5. 下拉刷新
                print("[5] 下拉刷新")
                await run(session, """
import time
from ascript.android import action
action.swipe(632, 400, 632, 1000, 60)
time.sleep(3)
print("[OK] REFRESH")
""")

                # 6. 在搜索结果中找第一个视频封面
                print("[6] 查找视频...")
                ui = await ui_tree(session)
                containers = walk_ui(ui, id_sub="container", clickable=True)
                covers = walk_ui(ui, id_sub="cover")
                thumbs = walk_ui(ui, id_sub="thumb")
                candidates = containers + covers + thumbs
                valid = [c for c in candidates if c['y'] > 400 and c['y'] < 2500]

                if valid:
                    v = valid[0]
                    print(f"  点击视频: ({v['x']}, {v['y']})")
                    await run(session, tap(v['x'], v['y'], 4), 8)
                else:
                    print("  未找到视频封面，点默认位置")
                    await run(session, tap(319, 1079, 4), 8)

                # 7. 截图（直接回传到PC）
                print("[7] 截图")
                await asyncio.sleep(2)
                shot = await session.call_tool("screen_capture", {})
                os.makedirs("D:/code/vscodeWorkDir/zscqNew/test1/screenshots", exist_ok=True)
                safe_name = drama.replace(" ", "").replace("/", "_")
                for item in shot.content:
                    if item.type == "image":
                        data = base64.b64decode(item.data)
                        path = f"D:/code/vscodeWorkDir/zscqNew/test1/screenshots/{safe_name}.png"
                        with open(path, "wb") as f:
                            f.write(data)
                        print(f"  截图已保存: {path} ({len(data)} bytes)")
                    elif item.type == "text":
                        print(f"  {item.text[:100]}")

                # 8. 分析页面，找作者信息
                print("[8] 分析页面...")
                ui = await ui_tree(session)
                nodes = walk_ui(ui)
                author_name = None
                author_pos = None
                for n in nodes:
                    if '@' in n['text'] or 'user_name' in n['id']:
                        author_name = n['text']
                        author_pos = (n['x'], n['y'])
                        break
                if not author_pos:
                    # 兜底：找左下角区域的控件
                    for n in nodes:
                        if n['y'] > 2000 and n['clickable']:
                            author_name = n['text']
                            author_pos = (n['x'], n['y'])
                            break

                if author_pos:
                    print(f"  作者: '{author_name}' at {author_pos}")
                    await run(session, tap(author_pos[0], author_pos[1], 3), 8)

                    # 9. 提取快手号
                    print("  [9] 提取快手号...")
                    ui = await ui_tree(session)
                    kw_nodes = walk_ui(ui, keyword="快手号")
                    pf_nodes = walk_ui(ui, id_sub="profile")
                    found_id = "N/A"
                    for n in kw_nodes + pf_nodes:
                        m = re.search(r'[：:]\s*(\S+)', n['text'])
                        if m:
                            found_id = m.group(1).strip()
                            break
                        txt = n['text'].strip()
                        if txt and len(txt) < 30 and txt not in ["快手号"]:
                            found_id = txt
                    print(f"  >>> 快手号: {found_id}")

                    # 10. 返回
                    print("  [10] 返回")
                    await run(session, tap(50, 200, 2), 5)
                else:
                    print("  [9] 未找到作者信息")
                    ui2 = await ui_tree(session)
                    nodes2 = walk_ui(ui2)
                    for n in nodes2[:15]:
                        print(f"    [{n['type']}] '{n['text'][:30]}' id={n['id'][:40]} ({n['x']},{n['y']})")

            print(f"\n=== 完成 ===")

if __name__ == "__main__":
    asyncio.run(main())

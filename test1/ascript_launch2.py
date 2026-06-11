"""
两步走：1. 启动快手  2. 看界面UI树
"""
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    server_params = StdioServerParameters(
        command="python",
        args=["-m", "ascript_mcp.local"]
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await session.call_tool("connect_device", {"ip": "172.16.1.139", "port": 9096, "connection_mode": "LocalIP"})

            # Step 1: 启动快手
            print("[Step 1] 启动快手...")
            r = await session.call_tool("deploy_and_run", {
                "project_name": "zscqAndroid",
                "code": """
import subprocess, time
subprocess.run(['am', 'start', '-n', 'com.kuaishou.nebula/com.yxcorp.gifshow.HomeActivity'], timeout=10)
time.sleep(8)
print("KWAI LAUNCHED")
""",
                "log_seconds": 12.0
            })
            for item in r.content:
                if item.type == "text":
                    print(f"  {item.text[:200]}")
                elif item.type == "image":
                    print(f"  [截图: {len(item.data)} bytes]")

            # Step 2: 用 MCP dump_ui_tree 看当前界面
            print("\n[Step 2] 获取UI树...")
            r = await session.call_tool("dump_ui_tree", {"mode": 0})
            import json
            for item in r.content:
                if item.type == "text":
                    data = json.loads(item.text)
                    views = data.get("data", {}).get("views", [])
                    print(f"  顶层控件: {len(views)}")

                    def find_all(node, depth=0):
                        res = []
                        text = node.get("text", "") or ""
                        rid = node.get("id", "") or ""
                        clk = node.get("clickable", False)
                        desc = node.get("contentDescription", "") or ""
                        if text or rid:
                            res.append({
                                "text": text[:50],
                                "id": rid[:60],
                                "clickable": clk,
                                "desc": desc[:40],
                                "depth": depth,
                                "type": node.get("type", ""),
                                "center": (node.get("center_x"), node.get("center_y"))
                            })
                        for c in node.get("childs", []):
                            res.extend(find_all(c, depth+1))
                        return res

                    nodes = find_all({"childs": views})
                    print(f"  含文本控件: {len(nodes)}")
                    for n in nodes[:60]:
                        click = " [click]" if n["clickable"] else ""
                        print(f"  {'  ' * n['depth']}[{n['type']}] '{n['text']}'{click}")
                        print(f"  {'  ' * n['depth']}   id={n['id']}, pos={n['center']}")

            # Step 3: 截图
            print("\n[Step 3] 截图...")
            r = await session.call_tool("screen_capture", {})
            for item in r.content:
                if item.type == "image":
                    print(f"  [截图: {len(item.data)} bytes]")

if __name__ == "__main__":
    asyncio.run(main())

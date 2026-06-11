"""
通过 AScript MCP 远程控制手机 - 查看当前界面
"""
import asyncio, json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import base64

async def call(session, tool, args=None):
    result = await session.call_tool(tool, args or {})
    texts = []
    for item in result.content:
        if item.type == "text":
            texts.append(item.text)
        elif item.type == "image":
            # 保存图片
            data = base64.b64decode(item.data)
            fname = f"screen_{tool}.png"
            with open(fname, "wb") as f:
                f.write(data)
            texts.append(f"[Image saved: {fname}, {len(data)} bytes]")
    return "\n".join(texts)

async def main():
    server_params = StdioServerParameters(
        command="python",
        args=["-m", "ascript_mcp.local"]
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("[OK] 已连接")

            # 连接设备
            r = await call(session, "connect_device", {"ip": "172.16.1.139", "port": 9096, "connection_mode": "LocalIP"})
            print(f"[设备] {r}")

            # 获取设备状态
            r = await call(session, "get_device_status")
            print(f"\n[设备状态] {r[:1000]}")

            # 获取完整UI树，分析所有可点击元素
            print("\n[UI树] 正在获取控件树...")
            r = await call(session, "dump_ui_tree", {"mode": 0})
            # 保存完整UI树
            with open("ui_tree_full.txt", "w", encoding="utf-8") as f:
                f.write(r)
            print(f"[UI树] 已保存 ({len(r)} chars)")

            # 解析并列出所有可点击/有文本的控件
            try:
                data = json.loads(r)
                views = data.get("data", {}).get("views", [])
                print(f"\n[控件列表] 共 {len(views)} 个顶层控件")
                # 递归查找有文本的节点
                def find_text_nodes(node, depth=0):
                    results = []
                    text = node.get("text", "")
                    desc = node.get("contentDescription", "") or ""
                    if text or desc:
                        results.append({
                            "text": text or desc,
                            "clickable": node.get("clickable", False),
                            "center": (node.get("center_x"), node.get("center_y")),
                            "id": node.get("id", ""),
                            "type": node.get("type", ""),
                            "rect": node.get("rect", {}),
                            "depth": depth
                        })
                    for child in node.get("childs", []):
                        results.extend(find_text_nodes(child, depth + 1))
                    return results

                all_nodes = find_text_nodes({"childs": views, "text": ""})
                print(f"\n[文本控件] 共 {len(all_nodes)} 个含文本的控件:")
                for n in all_nodes[:50]:
                    click = " [可点击]" if n["clickable"] else ""
                    print(f"  [{n['type']}] '{n['text'][:50]}'{click}")
                    print(f"    坐标: {n['center']}, ID: {n['id']}")
            except Exception as e:
                print(f"[解析错误] {e}")

if __name__ == "__main__":
    asyncio.run(main())

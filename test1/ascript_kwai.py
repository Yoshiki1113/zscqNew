"""
部署脚本：启动快手并获取UI结构
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

            code = """
import subprocess, json, time
from ascript.android import action

# 启动快手
subprocess.run(['am', 'start', '-n', 'com.kuaishou.nebula/com.yxcorp.gifshow.HomeActivity'], timeout=10)
time.sleep(5)

# 获取当前界面UI树
from ascript.android.node import Selector, Node
s = Selector(0)
root = s.find()

def dump_tree(node, depth=0, max_depth=5):
    if depth > max_depth:
        return []
    results = []
    text = node.text if hasattr(node, 'text') else ''
    rid = node.id if hasattr(node, 'id') else ''
    clk = 'click' if node.clickable else ''
    cd = node.contentDescription if hasattr(node, 'contentDescription') else ''
    rect = ''
    if hasattr(node, 'rect'):
        r = node.rect
        rect = f'[{r.left},{r.top},{r.right},{r.bottom}]'

    info = {
        'text': str(text or '')[:60],
        'id': str(rid or '')[:80],
        'clickable': node.clickable if hasattr(node, 'clickable') else False,
        'desc': str(cd or '')[:60],
        'rect': rect,
        'depth': depth,
        'type': str(type(node).__name__)[:30]
    }
    if text or rid or cd:
        results.append(info)

    if hasattr(node, 'children'):
        for child in node.children:
            results.extend(dump_tree(child, depth+1, max_depth))
    return results

all_nodes = dump_tree(root)
print(f"FOUND {len(all_nodes)} TEXT NODES")
for n in all_nodes[:80]:
    print(json.dumps(n, ensure_ascii=False))
"""
            result = await session.call_tool("deploy_and_run", {
                "project_name": "zscqAndroid",
                "code": code,
                "log_seconds": 15.0
            })
            for item in result.content:
                if item.type == "text":
                    print(f"[输出] {item.text[:5000]}")
                elif item.type == "image":
                    print(f"[截图] {len(item.data)} bytes")

if __name__ == "__main__":
    asyncio.run(main())

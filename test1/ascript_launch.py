"""
通过 AScript eval_python 启动快手并查看界面
"""
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def call(session, tool, args=None):
    result = await session.call_tool(tool, args or {})
    texts = []
    for item in result.content:
        if item.type == "text":
            texts.append(item.text)
    return "\n".join(texts)

async def main():
    server_params = StdioServerParameters(
        command="python",
        args=["-m", "ascript_mcp.local"]
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 连接设备
            await call(session, "connect_device", {"ip": "172.16.1.139", "port": 9096, "connection_mode": "LocalIP"})

            # 1. 查一下快手的包名
            print("[1] 查找快手应用...")
            r = await call(session, "eval_python", {"code": """
import subprocess
result = subprocess.run(['pm', 'list', 'packages', 'kuaishou'], capture_output=True, text=True, timeout=5)
result.stdout.strip()
"""})
            print(f"  结果: {r[:500]}")

            # 也找找 快手
            r2 = await call(session, "eval_python", {"code": """
import subprocess
result = subprocess.run(['pm', 'list', 'packages', 'kwai'], capture_output=True, text=True, timeout=5)
result.stdout.strip()
"""})
            print(f"  kwai: {r2[:500]}")

            # 找 com.kuaishou
            r3 = await call(session, "eval_python", {"code": """
import subprocess
result = subprocess.run(['pm', 'list', 'packages', 'kuaishou'], capture_output=True, text=True, timeout=5)
lines = [l for l in result.stdout.strip().split('\\n') if l]
lines
"""})
            print(f"  packages: {r3[:500]}")

if __name__ == "__main__":
    asyncio.run(main())

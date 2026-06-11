"""
调试 AScript eval_python - 找快手并启动
"""
import asyncio, json
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

            # 简单测试
            r = await session.call_tool("eval_python", {"code": "1+1"})
            print("1+1:", r.content)

            # 找 kuaishou package
            for kw in ["kuaishou", "kwai", "shortvideo", "video"]:
                r = await session.call_tool("eval_python", {"code": f"""
import subprocess, json
p = subprocess.run(['sh', '-c', "pm list packages | grep -i '{kw}' || echo not_found"], capture_output=True, text=True, timeout=10)
json.dumps({{"kw": "{kw}", "stdout": p.stdout.strip(), "stderr": p.stderr.strip(), "rc": p.returncode}})
"""})
                text = r.content[0].text if hasattr(r.content[0], 'text') else str(r.content)
                print(f"search '{kw}':", str(text)[:300])

if __name__ == "__main__":
    asyncio.run(main())

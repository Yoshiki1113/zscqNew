"""
部署脚本到手机运行 - 查找并启动快手
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

            # 部署并运行一个脚本
            code = """
import subprocess, json

# 查找快手相关包
result = subprocess.run(['sh', '-c', 'pm list packages | grep -iE "kwai|kuaishou|short"'], capture_output=True, text=True, timeout=10)
pkgs = result.stdout.strip().split('\\n') if result.stdout.strip() else []

# 也试试用 dumpsys
result2 = subprocess.run(['sh', '-c', 'dumpsys package | grep -iE "kwai|kuaishou" | head -20'], capture_output=True, text=True, timeout=10)

output = {
    "packages": pkgs,
    "dumpsys": result2.stdout.strip()[:500],
    "error": result2.stderr.strip()[:200]
}

# 保存到文件以便查看
with open("/sdcard/kwai_result.json", "w") as f:
    json.dump(output, f, ensure_ascii=False)

print(json.dumps(output, ensure_ascii=False))
"""
            print("[部署] 运行脚本查找快手包名...")
            result = await session.call_tool("deploy_and_run", {
                "project_name": "zscqAndroid",
                "code": code,
                "log_seconds": 10.0
            })

            for item in result.content:
                if item.type == "text":
                    print(f"[输出] {item.text}")
                elif item.type == "image":
                    print(f"[截图] {len(item.data)} bytes")

if __name__ == "__main__":
    asyncio.run(main())

"""
AScript 连接设备并截图
"""
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import base64

async def main():
    server_params = StdioServerParameters(
        command="python",
        args=["-m", "ascript_mcp.local"]
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("[OK] MCP 连接成功")

            # 连接设备 (WiFi局域网方式)
            print("[连接] 正在连接设备 172.16.1.139:9096 ...")
            result = await session.call_tool("connect_device", {
                "ip": "172.16.1.139",
                "port": 9096,
                "connection_mode": "LocalIP"
            })
            print(f"[连接结果] {result.content}")

            # 走 observe_device 一步到位: 截图 + UI层级树
            print("[截图] 正在截取屏幕...")
            result = await session.call_tool("observe_device", {})

            if result.content:
                for item in result.content:
                    if item.type == "image":
                        # 保存截图
                        img_data = base64.b64decode(item.data)
                        with open("kuaishou_screenshot.png", "wb") as f:
                            f.write(img_data)
                        print(f"[OK] 截图已保存: kuaishou_screenshot.png ({len(img_data)} bytes)")
                    elif item.type == "text":
                        # 保存UI层级树
                        with open("ui_tree.txt", "w", encoding="utf-8") as f:
                            f.write(item.text)
                        print(f"[OK] UI层级树已保存: ui_tree.txt ({len(item.text)} chars)")
                        # 打印前2000个字符
                        print(f"\n[UI层级树预览]:\n{item.text[:2000]}")

            print("\n[完成] 截图 + UI层级树获取完毕")

if __name__ == "__main__":
    asyncio.run(main())

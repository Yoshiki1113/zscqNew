"""
通过 mcp Python 库连接 AScript 进行设备扫描和截图
"""
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    # 启动 AScript MCP 服务器
    server_params = StdioServerParameters(
        command="python",
        args=["-m", "ascript_mcp.local"]
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # 初始化
            await session.initialize()
            print("[OK] MCP 连接成功")

            # 列举工具
            tools = await session.list_tools()
            print(f"\n[工具] 可用工具 ({len(tools.tools)}):")
            for t in tools.tools:
                print(f"   - {t.name}")

            # 扫描设备
            print("\n[扫描] 正在扫描局域网设备...")
            result = await session.call_tool("scan_devices", {"port": 9096})
            print(f"扫描结果: {result.content}")

            # 如果扫描到设备，尝试连接第一个
            devices_text = str(result.content)
            if devices_text and len(devices_text) > 20:
                print(f"  设备数据: {devices_text[:500]}")
            else:
                print("  ⚠️ 未发现设备，请确保:")
                print("   1. 手机已安装 AScript App 并打开")
                print("   2. 手机和电脑在同一个 WiFi 下")
                print("   3. 手机 AScript 已开启无障碍服务")

if __name__ == "__main__":
    asyncio.run(main())

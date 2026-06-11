"""
查询 AScript 操作相关 API
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

            # 查询 action 模块 API
            result = await session.call_tool("get_module_apis", {
                "platform": "android",
                "module": "action"
            })
            for item in result.content:
                if item.type == "text":
                    print("[ACTION API]")
                    print(item.text[:3000])

            # 查询 node 模块 API (控件选择相关)
            result2 = await session.call_tool("get_module_apis", {
                "platform": "android",
                "module": "node"
            })
            for item in result2.content:
                if item.type == "text":
                    print("\n[NODE API]")
                    print(item.text[:3000])

            # 查询 app 模块 API (应用管理)
            result3 = await session.call_tool("get_module_apis", {
                "platform": "android",
                "module": "app"
            })
            for item in result3.content:
                if item.type == "text":
                    print("\n[APP API]")
                    print(item.text[:2000])

            # 获取代码示例
            result4 = await session.call_tool("get_code_example", {
                "task": "点击",
                "platform": "android"
            })
            for item in result4.content:
                if item.type == "text":
                    print("\n[点击示例]")
                    print(item.text[:2000])

if __name__ == "__main__":
    asyncio.run(main())

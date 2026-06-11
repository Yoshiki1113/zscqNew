"""
获取手机屏幕截图并保存到PC
"""
import asyncio, base64
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    sp = StdioServerParameters(command="python", args=["-m", "ascript_mcp.local"])
    async with stdio_client(sp) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await session.call_tool("connect_device", {"ip": "172.16.1.139", "port": 9096, "connection_mode": "LocalIP"})

            # 获取屏幕截图
            print("截取当前屏幕...")
            result = await session.call_tool("screen_capture", {})
            for item in result.content:
                if item.type == "image":
                    data = base64.b64decode(item.data)
                    path = "D:/code/vscodeWorkDir/zscqNew/test1/phone_screen.png"
                    with open(path, "wb") as f:
                        f.write(data)
                    print(f"OK: {path} ({len(data)} bytes)")

            # 也试一下从设备读取之前保存的文件
            print("尝试读取手机上之前的截图...")
            r = await session.call_tool("deploy_and_run", {
                "project_name": "zscqAndroid",
                "code": """
import os, json
files = []
for f in ["/sdcard/kuaishou_video_screenshot.png", "/sdcard/kuaishou_screenshot.png"]:
    if os.path.exists(f):
        files.append({"name": f, "size": os.path.getsize(f)})
print(json.dumps(files, ensure_ascii=False))
""",
                "log_seconds": 5
            })
            for item in r.content:
                if item.type == "text":
                    print(f"手机文件: {item.text}")

if __name__ == "__main__":
    asyncio.run(main())

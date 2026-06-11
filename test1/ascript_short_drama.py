"""
快手短剧筛查 - 完整脚本（在手机上运行）
"""
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# 要筛查的短剧列表
DRAMA_LIST = [
    "闪婚后被大佬宠上天",
    "我的医妃不好惹",
    "我在80年代当后妈",
]

async def main():
    server_params = StdioServerParameters(
        command="python",
        args=["-m", "ascript_mcp.local"]
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await session.call_tool("connect_device", {"ip": "172.16.1.139", "port": 9096, "connection_mode": "LocalIP"})

            # 将短剧列表嵌入到部署的代码中
            dramas_json = str(DRAMA_LIST)

            code = f"""
import subprocess, time, json, os
from ascript.android import action
from ascript.android.node import Selector, Node

def log(msg):
    print(f"[AUTO] {{msg}}")

def find_and_click(selector, timeout=5):
    \"\"\"找到控件并点击\"\"\"
    for i in range(timeout):
        el = selector.find()
        if el:
            el.click()
            return True
        time.sleep(0.5)
    return False

def find_text(text, timeout=3):
    \"\"\"等待文本出现\"\"\"
    s = Selector(0)
    for i in range(timeout):
        el = s.find_by_text(text)
        if el:
            return el
        time.sleep(0.5)
    return None

# 启动快手
log("启动快手...")
subprocess.run(['am', 'start', '-n', 'com.kuaishou.nebula/com.yxcorp.gifshow.HomeActivity'], timeout=10)
time.sleep(6)

dramas = {dramas_json}
results = []

for drama_name in dramas:
    log(f"===== 开始筛查: {{drama_name}} =====")

    # 点击搜索按钮
    s = Selector(0)
    search_btn = s.find_by_id('com.kuaishou.nebula:id/thanos_home_top_search')
    if not search_btn:
        # 也可能是 edit_btn
        search_btn = s.find_by_id('com.kuaishou.nebula:id/edit_btn')

    if search_btn:
        search_btn.click()
        time.sleep(2)
        log("已点击搜索按钮")
    else:
        log("未找到搜索按钮，尝试坐标点击")
        action.click(1159, 208)
        time.sleep(2)

    # 输入搜索词
    s = Selector(0)
    edit = s.find_by_id('com.kuaishou.nebula:id/search_edit_text')
    if edit:
        edit.click()
        time.sleep(0.5)
        edit.input(drama_name)
        log(f"已输入: {{drama_name}}")
    else:
        log("未找到搜索输入框")

    time.sleep(1)

    # 点击搜索按钮（键盘或界面搜索按钮）
    search_btn2 = s.find_by_text("搜索")
    if search_btn2:
        search_btn2.click()
        log("点击了搜索按钮")
    else:
        # 尝试回车
        action.click(632, 500)
        log("通过坐标点击搜索")

    time.sleep(4)

    # 下拉刷新
    log("下拉刷新...")
    action.swipe(632, 400, 632, 1000, 50)
    time.sleep(3)

    # 点击第一个视频结果
    s = Selector(0)
    # 找第一个可点击的视频条目
    first_video = s.find_by_id('com.kuaishou.nebula:id/cover')
    if not first_video:
        first_video = s.find_by_id('com.kuaishou.nebula:id/thumbnail')
    if not first_video:
        # 找搜索结果的第一个可点击元素
        log("尝试找搜索结果列表...")
        for _ in range(3):
            items = s.find_all()
            # 找第一个有宽高比较大的控件
            best = None
            # 直接用坐标点击屏幕中间偏上
            action.click(632, 600)
            time.sleep(2)
            break
    else:
        first_video.click()
        time.sleep(2)
    log("已进入视频")

    # 截图
    from ascript.android import screen
    time.sleep(1)
    img = screen.capture()
    # 保存到手机存储
    fname = f"/sdcard/{{drama_name}}_video.png"
    img.save(fname)
    log(f"截图已保存: {{fname}}")

    # 获取视频页作者信息
    s = Selector(0)
    author_name = s.find_by_id('com.kuaishou.nebula:id/user_name_text_view')
    author_id = "N/A"
    if author_name:
        author_text = author_name.text if hasattr(author_name, 'text') else ''
        author_name.click()
        time.sleep(3)
        log(f"进入作者主页: {{author_text}}")

        # 在作者主页找快手号
        s2 = Selector(0)
        profile_id = s2.find_by_id('com.kuaishou.nebula:id/profile_id')
        if profile_id:
            author_id = profile_id.text if hasattr(profile_id, 'text') else ''
            log(f"找到快手号: {{author_id}}")
        else:
            # 遍历查找包含"快手号"的文本
            texts = s2.find_all()
            log(f"未直接找到profile_id，尝试查找快手号文本...")
            # 兜底：用坐标点方式找
            for el in [s2.find_by_text("关注")]:
                if el:
                    log(f"找到关注按钮，说明在作者主页")

    results.append({{
        "drama": drama_name,
        "author_id": author_id,
        "screenshot": fname
    }})
    log(f"作者ID: {{author_id}}")

    # 返回
    action.click(50, 200)  # 左上角返回
    time.sleep(2)
    action.click(50, 200)  # 再返回搜索页
    time.sleep(2)

log("===== 筛查完成 =====")
for r in results:
    log(json.dumps(r, ensure_ascii=False))
"""
            print("[部署] 运行快手短剧筛查脚本...")
            result = await session.call_tool("deploy_and_run", {
                "project_name": "zscqAndroid",
                "code": code,
                "log_seconds": 60.0
            })

            for item in result.content:
                if item.type == "text":
                    # 只打印含 [AUTO] 的行和结果
                    for line in item.text.split("\n"):
                        if "[AUTO]" in line or "FOUND" in line or "=====" in line or "筛查" in line:
                            print(f"  {line}")
                        elif line.strip() and len(line.strip()) > 10:
                            print(f"  {line[:200]}")
                elif item.type == "image":
                    print(f"  [截图: {len(item.data)} bytes]")

if __name__ == "__main__":
    asyncio.run(main())

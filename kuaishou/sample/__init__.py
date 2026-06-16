"""
AScript 工程入口文件（部分模板会执行 __init__.py）。
这里统一转发到 kuaishou_collect.run_cli，避免入口行为不一致。
"""

import sys

try:
    # 包方式加载时（AScript 常见）
    from .kuaishou_collect import run_cli
except ImportError:
    # 兜底：脚本方式直接运行目录下文件
    from kuaishou_collect import run_cli

print("[zscqAndroid] __init__ entry")
if len(sys.argv) > 1:
    run_cli(sys.argv[1:])
else:
    # AScript 点击“运行”通常无参数，默认触发一条可见的业务流程
    run_cli(["少爷当腻了只想好好打工"])

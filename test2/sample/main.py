"""
AScript IDE 本地运行入口（Ctrl+Shift+R / AScript:运行）。

默认策略：
- 有命令行参数：透传给 kuaishou_collect.run_cli()
- 无参数：直接跑一条知识产权业务流程示例（可自行改关键词）
"""

import sys

try:
    # 包方式加载时（AScript 常见）
    from .kuaishou_collect import run_cli
except ImportError:
    # 兜底：脚本方式直接运行目录下文件
    from kuaishou_collect import run_cli


if __name__ == "__main__":
    if len(sys.argv) > 1:
        raise SystemExit(run_cli(sys.argv[1:]))

    # AScript IDE 通常无额外参数，默认跑业务流程示例
    # 精简版入口只需要关键词
    raise SystemExit(run_cli(["少爷当腻了只想好好打工"]))

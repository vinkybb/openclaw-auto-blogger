#!/usr/bin/env python3
"""
OpenClaw 集成冒烟测试：需运行中的 Gateway + OPENCLAW_GATEWAY_TOKEN。
未设置 token 时退出 0 并跳过（便于 CI）。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.openclaw_client import create_client


def test_openclaw_connection():
    print("=" * 50)
    print("测试 OpenClaw Gateway（POST /tools/invoke → sessions_spawn）")
    print("=" * 50)

    client = create_client(
        {
            "gateway_url": os.environ.get("OPENCLAW_GATEWAY_URL", "http://127.0.0.1:18789"),
        }
    )

    result = client.spawn_agent(
        "请回复：OpenClaw 连接成功！",
        timeout_seconds=30,
        min_chars_early_exit=12,
    )
    if isinstance(result, dict) and result.get("success"):
        print("\n✓ 调用成功")
        print(f"响应: {client._extract_result(result)}")
        return True
    err = result.get("error") if isinstance(result, dict) else str(result)
    print(f"\n✗ 调用失败: {err}")
    print("\n请检查：")
    print("  - Gateway 已启动，且地址与 OPENCLAW_GATEWAY_URL 一致")
    print("  - 已设置 OPENCLAW_GATEWAY_TOKEN")
    print("  - gateway.tools 已允许 HTTP 调用 sessions_spawn（默认可能被 deny）")
    print("  文档: https://docs.openclaw.ai/gateway/tools-invoke-http-api")
    print("  排错: https://docs.openclaw.ai/help/troubleshooting")
    return False


def test_summarize():
    print("\n" + "=" * 50)
    print("测试摘要生成")
    print("=" * 50)

    from modules.summarizer import RSSSummarizer

    summarizer = RSSSummarizer(
        {
            "openclaw": {
                "gateway_url": os.environ.get(
                    "OPENCLAW_GATEWAY_URL", "http://127.0.0.1:18789"
                ),
            }
        }
    )

    test_content = """
    人工智能技术正在快速发展，特别是大语言模型的出现，
    使得自然语言处理能力得到了质的飞跃。
    """

    result = summarizer.summarize("AI技术发展", test_content, style="简洁")
    if result.get("success"):
        print("\n✓ 摘要生成成功")
        print(f"摘要: {result['summary'][:200]}...")
        return True
    print(f"\n✗ 摘要生成失败: {result.get('error')}")
    return False


def test_expand():
    print("\n" + "=" * 50)
    print("测试文章扩写")
    print("=" * 50)

    from modules.expander import ArticleExpander

    expander = ArticleExpander(
        {
            "openclaw": {
                "gateway_url": os.environ.get(
                    "OPENCLAW_GATEWAY_URL", "http://127.0.0.1:18789"
                ),
            },
            "content": {"article_length": 500},
        }
    )

    test_summary = "大语言模型推动自然语言处理发展。"

    result = expander.expand(
        title="AI趋势",
        summary=test_summary,
        word_count=500,
    )

    if result.get("success"):
        print("\n✓ 扩写成功")
        print(f"标题: {result['title']}")
        print(f"内容预览:\n{result['content'][:300]}...")
        return True
    print(f"\n✗ 扩写失败: {result.get('error')}")
    return False


def main():
    print("\n博客流水线 - OpenClaw 集成测试\n")

    if not os.environ.get("OPENCLAW_GATEWAY_TOKEN"):
        print("未设置 OPENCLAW_GATEWAY_TOKEN，跳过实时 Gateway 测试。")
        print("设置 token 后重新运行: python tests/test_openclaw.py\n")
        return 0

    results = []
    results.append(("OpenClaw 调用", test_openclaw_connection()))

    if results[0][1]:
        results.append(("摘要生成", test_summarize()))
        results.append(("文章扩写", test_expand()))

    print("\n" + "=" * 50)
    print("测试结果汇总")
    print("=" * 50)

    for name, passed in results:
        status = "✓ 通过" if passed else "✗ 失败"
        print(f"  {name}: {status}")

    all_passed = all(r[1] for r in results)
    print("\n" + ("所有测试通过！" if all_passed else "部分测试失败，请检查配置"))
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
测试脚本 - 验证 OpenClaw 集成
"""

import sys
import os

# 添加模块路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.openclaw_client import OpenClawClient, create_client


def test_openclaw_connection():
    """测试 OpenClaw 连接"""
    print("=" * 50)
    print("测试 OpenClaw 连接")
    print("=" * 50)
    
    client = create_client({'base_url': 'http://localhost:3000'})
    
    try:
        # 简单测试
        result = client.spawn_agent("请回复：OpenClaw 连接成功！", timeout_seconds=30)
        print(f"\n✓ 连接成功")
        print(f"响应: {client._extract_result(result)}")
        return True
    except Exception as e:
        print(f"\n✗ 连接失败: {e}")
        print("\n请确保 OpenClaw Gateway 正在运行:")
        print("  openclaw gateway status")
        print("  openclaw gateway start")
        return False


def test_summarize():
    """测试摘要功能"""
    print("\n" + "=" * 50)
    print("测试摘要生成")
    print("=" * 50)
    
    from modules.summarizer import RSSSummarizer
    
    summarizer = RSSSummarizer({'openclaw': {'base_url': 'http://localhost:3000'}})
    
    test_content = """
    人工智能技术正在快速发展，特别是大语言模型的出现，
    使得自然语言处理能力得到了质的飞跃。
    这些模型能够理解和生成人类语言，被广泛应用于聊天机器人、
    内容创作、代码生成等领域。然而，随之而来的也有对AI安全、
    伦理问题的担忧，需要社会各界共同关注和解决。
    """
    
    try:
        result = summarizer.summarize("AI技术发展", test_content, style="简洁")
        if result.get('success'):
            print(f"\n✓ 摘要生成成功")
            print(f"摘要: {result['summary']}")
            print(f"字数: {result['word_count']}")
            return True
        else:
            print(f"\n✗ 摘要生成失败: {result.get('error')}")
            return False
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        return False


def test_expand():
    """测试扩写功能"""
    print("\n" + "=" * 50)
    print("测试文章扩写")
    print("=" * 50)
    
    from modules.expander import ArticleExpander
    
    expander = ArticleExpander({'openclaw': {'base_url': 'http://localhost:3000'}})
    
    test_summary = "人工智能技术快速发展，大语言模型使自然语言处理能力飞跃，" \
                   "应用于聊天机器人、内容创作、代码生成等领域。" \
                   "同时也引发AI安全与伦理问题的担忧。"
    
    try:
        result = expander.expand(
            title="AI技术发展趋势",
            summary=test_summary,
            word_count=500  # 测试用短文章
        )
        
        if result.get('success'):
            print(f"\n✓ 扩写成功")
            print(f"标题: {result['title']}")
            print(f"字数: {result.get('word_count', 0)}")
            print(f"标签: {result.get('tags', [])}")
            print(f"\n内容预览:\n{result['content'][:300]}...")
            return True
        else:
            print(f"\n✗ 扩写失败: {result.get('error')}")
            return False
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        return False


def main():
    """运行所有测试"""
    print("\n博客流水线 - OpenClaw 集成测试\n")
    
    results = []
    
    # 测试连接
    results.append(("OpenClaw连接", test_openclaw_connection()))
    
    # 只有连接成功才继续其他测试
    if results[0][1]:
        results.append(("摘要生成", test_summarize()))
        results.append(("文章扩写", test_expand()))
    
    # 汇总
    print("\n" + "=" * 50)
    print("测试结果汇总")
    print("=" * 50)
    
    for name, passed in results:
        status = "✓ 通过" if passed else "✗ 失败"
        print(f"  {name}: {status}")
    
    all_passed = all(r[1] for r in results)
    
    print("\n" + ("所有测试通过！" if all_passed else "部分测试失败，请检查配置"))
    
    return 0 if all_passed else 1


if __name__ == '__main__':
    sys.exit(main())
"""
摘要生成模块 - 使用 OpenClaw 进行内容摘要
"""

from typing import Dict, Any, Optional, List
from .openclaw_client import OpenClawClient


class RSSSummarizer:
    """RSS 内容摘要生成器"""
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化摘要生成器
        
        Args:
            config: 配置字典，包含 OpenClaw 连接信息
        """
        self.config = config or {}
        self.client = OpenClawClient(self.config.get('openclaw', {}))
    
    def summarize(self, title: str, content: str, style: str = "简洁") -> Dict[str, Any]:
        """
        生成内容摘要
        
        Args:
            title: 文章标题
            content: 文章内容
            style: 摘要风格 (简洁/详细/专业)
            
        Returns:
            包含 title, summary, word_count 的字典
        """
        # 构建摘要提示词
        prompt = f"""请对以下文章进行{style}摘要：

标题：{title}

内容：
{content[:4000]}

要求：
1. 保持客观，不添加个人观点
2. 突出最重要的信息
3. 语言流畅，逻辑清晰
4. {"控制在 150-200 字" if style == "简洁" else "控制在 300-500 字"}

请直接输出摘要内容。"""

        try:
            raw = self.client.spawn_agent(
                prompt,
                timeout_seconds=self.client.timeout,
                min_chars_early_exit=80,
            )
            if isinstance(raw, dict) and raw.get("success") is False:
                err = raw.get("error") or "OpenClaw 调用失败"
                return {
                    "title": title,
                    "summary": "",
                    "word_count": 0,
                    "style": style,
                    "success": False,
                    "error": err,
                }
            text = self.client._extract_result(raw)
            if text.startswith("错误:"):
                return {
                    "title": title,
                    "summary": "",
                    "word_count": 0,
                    "style": style,
                    "success": False,
                    "error": text,
                }

            return {
                "title": title,
                "summary": text,
                "word_count": len(text),
                "style": style,
                "success": True,
            }
        except Exception as e:
            return {
                "title": title,
                "summary": f"摘要生成失败: {str(e)}",
                "word_count": 0,
                "style": style,
                "success": False,
                "error": str(e)
            }
    
    def summarize_batch(self, articles: List[Dict[str, Any]], style: str = "简洁") -> List[Dict[str, Any]]:
        """
        批量生成摘要
        
        Args:
            articles: 文章列表，每项包含 title 和 content
            style: 摘要风格
            
        Returns:
            摘要结果列表
        """
        results = []
        for article in articles:
            result = self.summarize(
                title=article.get('title', ''),
                content=article.get('content', ''),
                style=style
            )
            result['source_url'] = article.get('url', '')
            result['source_title'] = article.get('title', '')
            results.append(result)
        
        return results
    
    def extract_key_points(self, content: str) -> List[str]:
        """
        提取关键要点
        
        Args:
            content: 文章内容
            
        Returns:
            关键要点列表
        """
        prompt = f"""请从以下内容中提取 5-7 个关键要点，每个要点一行：

{content[:3000]}

只输出要点列表，每行一个要点，不要编号。"""

        try:
            raw = self.client.spawn_agent(
                prompt,
                timeout_seconds=self.client.timeout,
                min_chars_early_exit=50,
            )
            if isinstance(raw, dict) and raw.get("success") is False:
                return [f"提取失败: {raw.get('error', 'unknown')}"]
            text = self.client._extract_result(raw)
            if text.startswith("错误:"):
                return [text]
            points = [p.strip() for p in text.split("\n") if p.strip()]
            return points[:7]

        except Exception as e:
            return [f"提取失败: {str(e)}"]


# 便捷函数
def summarize_content(title: str, content: str, style: str = "简洁", 
                      config: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    便捷函数：生成内容摘要
    
    Args:
        title: 文章标题
        content: 文章内容
        style: 摘要风格
        config: OpenClaw 配置
        
    Returns:
        摘要结果字典
    """
    summarizer = RSSSummarizer(config)
    return summarizer.summarize(title, content, style)
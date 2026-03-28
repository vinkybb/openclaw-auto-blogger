"""
内容扩写模块 - 使用 OpenClaw 将摘要扩写为完整文章
"""

from typing import Dict, Any, List, Optional
from .openclaw_client import OpenClawClient


class ArticleExpander:
    """文章扩写器"""
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化扩写器
        
        Args:
            config: 配置字典，包含 OpenClaw 连接信息和扩写参数
        """
        self.config = config or {}
        self.client = OpenClawClient(self.config.get('openclaw', {}))
        
        # 扩写配置
        self.default_style = self.config.get('style', '深度分析')
        self.default_word_count = self.config.get('word_count', 1500)
    
    def expand(self, title: str, summary: str, source_url: str = None,
               style: str = None, word_count: int = None) -> Dict[str, Any]:
        """
        将摘要扩写为完整文章
        
        Args:
            title: 文章标题
            summary: 内容摘要
            source_url: 来源链接 (可选)
            style: 写作风格 (默认使用配置)
            word_count: 目标字数 (默认使用配置)
            
        Returns:
            包含 title, content, tags, word_count 的字典
        """
        style = style or self.default_style
        word_count = word_count or self.default_word_count
        
        source_info = f"\n\n参考来源：{source_url}" if source_url else ""
        
        prompt = f"""请基于以下摘要扩写为一篇完整的博客文章。

原标题：{title}

摘要：
{summary}
{source_info}

写作要求：
1. 风格：{style}
2. 目标字数：{word_count} 字左右
3. 结构要求：
   - 引言：简要介绍主题背景
   - 正文：深入分析，逻辑清晰，分段明确
   - 结论：总结观点，给出见解
4. 语言要求：生动有趣，适合阅读，避免生硬翻译腔
5. 格式要求：使用 Markdown 格式，适当使用标题层级

文章要求原创，不要直接复制摘要内容。

请按以下格式输出：

# 文章标题

正文内容...

---
标签: 标签1, 标签2, 标签3"""

        try:
            result = self.client.spawn_agent(prompt, timeout_seconds=120)
            text = self.client._extract_result(result)
            
            # 解析文章
            article = self._parse_article(text, title)
            article['source_url'] = source_url
            article['source_summary'] = summary
            article['style'] = style
            article['target_word_count'] = word_count
            article['success'] = True
            
            return article
            
        except Exception as e:
            return {
                'title': title,
                'content': f"扩写失败: {str(e)}",
                'tags': [],
                'source_url': source_url,
                'success': False,
                'error': str(e)
            }
    
    def expand_with_context(self, title: str, summary: str, 
                           context: str = None, source_url: str = None,
                           style: str = None, word_count: int = None) -> Dict[str, Any]:
        """
        带上下文的扩写，可以参考额外信息
        
        Args:
            title: 文章标题
            summary: 内容摘要
            context: 额外上下文信息
            source_url: 来源链接
            style: 写作风格
            word_count: 目标字数
            
        Returns:
            扩写结果
        """
        style = style or self.default_style
        word_count = word_count or self.default_word_count
        
        context_section = f"\n\n参考信息：\n{context}" if context else ""
        source_section = f"\n\n来源：{source_url}" if source_url else ""
        
        prompt = f"""请基于以下信息扩写一篇完整的博客文章。

标题：{title}

核心摘要：
{summary}
{context_section}
{source_section}

写作要求：
1. 风格：{style}
2. 目标字数：{word_count} 字
3. 结合核心摘要和参考信息进行创作
4. 保持观点客观，论述有据
5. 使用 Markdown 格式

输出格式：
# 文章标题

正文...

---
标签: 标签1, 标签2"""

        try:
            result = self.client.spawn_agent(prompt, timeout_seconds=120)
            text = self.client._extract_result(result)
            
            article = self._parse_article(text, title)
            article['source_url'] = source_url
            article['success'] = True
            
            return article
            
        except Exception as e:
            return {
                'title': title,
                'content': f"扩写失败: {str(e)}",
                'tags': [],
                'success': False,
                'error': str(e)
            }
    
    def rewrite(self, content: str, style: str = "更生动有趣") -> Dict[str, Any]:
        """
        重写文章，调整风格
        
        Args:
            content: 原文章内容
            style: 目标风格描述
            
        Returns:
            重写后的文章
        """
        prompt = f"""请将以下文章重写得{style}：

{content}

要求：
1. 保持核心观点不变
2. 调整语言风格
3. 优化结构
4. 使用 Markdown 格式

输出格式：
# 文章标题

正文...

---
标签: 标签1, 标签2"""

        try:
            result = self.client.spawn_agent(prompt, timeout_seconds=90)
            text = self.client._extract_result(result)
            
            article = self._parse_article(text, "重写文章")
            article['original_content'] = content
            article['style'] = style
            article['success'] = True
            
            return article
            
        except Exception as e:
            return {
                'title': '重写失败',
                'content': str(e),
                'success': False,
                'error': str(e)
            }
    
    def generate_outline(self, title: str, summary: str) -> List[str]:
        """
        生成文章大纲
        
        Args:
            title: 文章标题
            summary: 内容摘要
            
        Returns:
            大纲列表
        """
        prompt = f"""请为以下文章生成一个详细大纲：

标题：{title}
摘要：{summary}

输出格式：
1. 第一部分标题
   - 要点一
   - 要点二
2. 第二部分标题
   ...

只输出大纲，不要其他内容。"""

        try:
            result = self.client.spawn_agent(prompt, timeout_seconds=30)
            text = self.client._extract_result(result)
            
            # 解析大纲
            outline = [line.strip() for line in text.split('\n') if line.strip()]
            return outline
            
        except Exception as e:
            return [f"大纲生成失败: {str(e)}"]
    
    def _parse_article(self, text: str, default_title: str) -> Dict[str, Any]:
        """解析生成的文章"""
        lines = text.strip().split('\n')
        
        title = default_title
        content = text
        tags = []
        
        # 尝试提取标题（第一个 # 开头的行）
        for i, line in enumerate(lines):
            if line.startswith('# '):
                title = line[2:].strip()
                # 移除标题行后的内容作为正文
                remaining = '\n'.join(lines[i+1:])
                content = remaining
                break
        
        # 尝试提取标签（以 --- 分隔）
        if '---' in text:
            parts = text.split('---')
            if len(parts) >= 2:
                content = parts[0].strip()
                # 移除标题
                if content.startswith('# '):
                    first_newline = content.find('\n')
                    if first_newline > 0:
                        title = content[2:first_newline].strip()
                        content = content[first_newline:].strip()
                
                # 提取标签
                if len(parts) >= 2:
                    tag_part = parts[-1].strip()
                    if tag_part.startswith('标签'):
                        tag_text = tag_part.split(':', 1)[-1].strip() if ':' in tag_part else tag_part
                        tags = [t.strip() for t in tag_text.replace('，', ',').split(',') if t.strip()]
        
        # 计算字数
        word_count = len(content.replace('\n', '').replace(' ', ''))
        
        return {
            'title': title,
            'content': content,
            'tags': tags,
            'word_count': word_count
        }


# 便捷函数
def expand_article(title: str, summary: str, source_url: str = None,
                  style: str = "深度分析", word_count: int = 1500,
                  config: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    便捷函数：扩写文章
    
    Args:
        title: 文章标题
        summary: 内容摘要
        source_url: 来源链接
        style: 写作风格
        word_count: 目标字数
        config: OpenClaw 配置
        
    Returns:
        扩写结果
    """
    expander = ArticleExpander(config)
    return expander.expand(title, summary, source_url, style, word_count)
#!/usr/bin/env python3
"""
博客自动生成与发布流水线
基于 OpenClaw 框架构建

功能：
1. 从 RSS 源获取内容
2. 使用 OpenClaw 进行信息摘要
3. 使用 OpenClaw 进行深度扩写
4. 格式化为 Markdown
5. 自动发布到指定平台
"""

import os
import sys
import json
import yaml
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

# 添加模块路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.rss_fetcher import RSSFetcher
from modules.summarizer import RSSSummarizer
from modules.expander import ArticleExpander
from modules.publisher import Publisher

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BlogPipeline:
    """博客自动生成流水线"""
    
    def __init__(self, config_path: str = "config.yaml"):
        """
        初始化流水线
        
        Args:
            config_path: 配置文件路径
        """
        self.config = self._load_config(config_path)
        self.output_dir = Path(self.config.get('publish', {}).get('local', {}).get('content_dir', './output'))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化各模块
        # sources 在顶层配置，而非 rss 键下
        rss_config = {'sources': self.config.get('sources', [])}
        self.rss_fetcher = RSSFetcher(config=rss_config)
        self.summarizer = RSSSummarizer(self.config)
        self.expander = ArticleExpander(self.config)
        self.publisher = Publisher(self.config.get('publish', {}))
        
        logger.info("博客流水线初始化完成")
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """加载配置文件"""
        config_file = Path(config_path)
        if not config_file.exists():
            logger.warning(f"配置文件 {config_path} 不存在，使用默认配置")
            return self._default_config()
        
        with open(config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        return config or self._default_config()
    
    def _default_config(self) -> Dict[str, Any]:
        """默认配置"""
        return {
            'rss': {'sources': []},
            'openclaw': {'gateway_url': 'http://127.0.0.1:18789', 'timeout': 300},
            'publish': {'local': {'enabled': True, 'content_dir': './output'}},
            'content': {'summary_length': 200, 'article_length': 1500}
        }
    
    def fetch_articles(self) -> List[Dict[str, Any]]:
        """获取 RSS 文章"""
        logger.info("开始获取 RSS 文章...")
        articles = self.rss_fetcher.fetch_all()
        logger.info(f"获取到 {len(articles)} 篇文章")
        return articles
    
    def process_article(self, article: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理单篇文章：摘要 -> 扩写 -> 格式化
        
        Args:
            article: 原始文章数据
            
        Returns:
            处理后的文章数据
        """
        title = article.get('title', '无标题')
        content = article.get('content', article.get('summary', ''))
        source_url = article.get('link', article.get('url', ''))
        
        logger.info(f"处理文章: {title}")
        
        result = {
            'original': article,
            'title': title,
            'source_url': source_url,
            'processed_at': datetime.now().isoformat()
        }
        
        # Step 1: 生成摘要
        logger.info(f"生成摘要: {title}")
        # 构造 article dict 传递给 summarizer
        article_dict = {'title': title, 'content': content, 'description': content}
        summary_result = self.summarizer.summarize(article_dict)
        result['summary'] = summary_result
        
        if not summary_result.get('success'):
            logger.error(f"摘要生成失败: {summary_result.get('error', 'Unknown error')}")
            # 摘要失败不中断流程，使用原始内容继续
            summary_result['summary'] = content[:500] if content else title
        
        # Step 2: 扩写为完整文章
        logger.info(f"扩写文章: {title}")
        expand_result = self.expander.expand(
            title=title,
            summary=summary_result['summary'],
            source_url=source_url,
            style=self.config.get('content', {}).get('style', '深度分析'),
            word_count=self.config.get('content', {}).get('article_length', 1500)
        )
        result['article'] = expand_result
        
        if not expand_result.get('success'):
            logger.error(f"文章扩写失败: {expand_result.get('error')}")
            return result
        
        # Step 3: 格式化为 Markdown
        result['markdown'] = self._format_markdown(
            title=expand_result.get('title', title),
            content=expand_result.get('content', ''),
            tags=expand_result.get('tags', []),
            source_url=source_url
        )
        
        logger.info(f"文章处理完成: {title}")
        return result
    
    def _format_markdown(self, title: str, content: str, tags: List[str], 
                         source_url: str = None) -> str:
        """格式化为 Markdown 文件"""
        front_matter = {
            'title': title,
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'tags': tags,
            'draft': False
        }
        
        if source_url and self.config.get('content', {}).get('include_source', True):
            front_matter['source'] = source_url
        
        # YAML front matter
        yaml_fm = yaml.dump(front_matter, allow_unicode=True, default_flow_style=False)
        
        markdown = f"---\n{yaml_fm}---\n\n{content}\n"
        
        # 添加来源链接
        if source_url and self.config.get('content', {}).get('include_source', True):
            markdown += f"\n\n---\n\n> 原文链接：{source_url}\n"
        
        return markdown
    
    def save_article(self, result: Dict[str, Any]) -> str:
        """
        保存文章到本地
        
        Args:
            result: 处理结果
            
        Returns:
            保存的文件路径
        """
        if 'markdown' not in result:
            logger.warning(f"文章没有 Markdown 内容，跳过保存: {result.get('title')}")
            return None
        
        # 生成文件名
        title = result.get('article', {}).get('title', result.get('title', 'untitled'))
        date_prefix = datetime.now().strftime('%Y-%m-%d')
        # 清理标题作为文件名
        safe_title = "".join(c if c.isalnum() or c in (' ', '-', '_') else '' for c in title)
        safe_title = safe_title.strip().replace(' ', '-')[:50]
        filename = f"{date_prefix}-{safe_title}.md"
        
        filepath = self.output_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(result['markdown'])
        
        logger.info(f"文章已保存: {filepath}")
        return str(filepath)
    
    def run(
        self, max_articles: int = None, dry_run: bool = False
    ) -> List[Dict[str, Any]]:
        """
        运行完整流水线

        Args:
            max_articles: 最大处理文章数 (None 表示不限制)
            dry_run: 为 True 时不写入 Markdown、不写报告、不调用远程发布
        """
        logger.info("=== 博客流水线开始运行 ===")
        if dry_run:
            logger.info("dry-run: 跳过保存文件与发布")

        articles = self.fetch_articles()

        if max_articles:
            articles = articles[:max_articles]

        results = []
        for i, article in enumerate(articles, 1):
            logger.info(f"处理进度: {i}/{len(articles)}")

            try:
                result = self.process_article(article)
                ar = result.get("article") or {}

                if dry_run:
                    result["filepath"] = None
                else:
                    filepath = self.save_article(result)
                    result["filepath"] = filepath

                    pub_cfg = self.config.get("publish") or {}
                    remote_on = (
                        pub_cfg.get("github", {}).get("enabled")
                        or pub_cfg.get("wordpress", {}).get("enabled")
                        or pub_cfg.get("webhook", {}).get("enabled")
                    )
                    if ar.get("success") and remote_on:
                        body = ar.get("content", "")
                        result["publish_results"] = self.publisher.publish(
                            title=ar.get("title", result.get("title", "")),
                            content=body,
                            tags=ar.get("tags") or [],
                            image_url=None,
                            apply_local=False,
                        )
                    if result.get("filepath") and pub_cfg.get("local", {}).get(
                        "enabled", True
                    ):
                        result["published"] = True

                results.append(result)

            except Exception as e:
                logger.error(f"处理文章失败: {e}")
                results.append(
                    {"original": article, "error": str(e), "success": False}
                )

        logger.info(f"=== 流水线运行完成，处理 {len(results)} 篇文章 ===")

        if not dry_run:
            self._save_report(results)

        return results
    
    def _save_report(self, results: List[Dict[str, Any]]):
        """保存运行报告"""
        report_path = self.output_dir / f"report-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        
        # 简化报告内容
        simplified = []
        for r in results:
            simplified.append({
                'title': r.get('title') or r.get('original', {}).get('title'),
                'source_url': r.get('source_url'),
                'filepath': r.get('filepath'),
                'success': 'article' in r and r['article'].get('success', False),
                'error': r.get('error') or r.get('article', {}).get('error')
            })
        
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(simplified, f, ensure_ascii=False, indent=2)
        
        logger.info(f"运行报告已保存: {report_path}")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='博客自动生成流水线')
    parser.add_argument('-c', '--config', default='config.yaml', help='配置文件路径')
    parser.add_argument('-n', '--number', type=int, help='处理文章数量')
    parser.add_argument('--fetch-only', action='store_true', help='仅获取文章不处理')
    parser.add_argument('--dry-run', action='store_true', help='试运行，不保存文件')
    
    args = parser.parse_args()
    
    pipeline = BlogPipeline(config_path=args.config)
    
    if args.fetch_only:
        articles = pipeline.fetch_articles()
        print(f"\n获取到 {len(articles)} 篇文章:")
        for a in articles[:10]:
            print(f"  - {a.get('title')}")
    else:
        results = pipeline.run(max_articles=args.number, dry_run=args.dry_run)
        
        success_count = sum(1 for r in results if r.get('article', {}).get('success', False))
        print(f"\n处理完成: {success_count}/{len(results)} 篇文章成功")
        
        for r in results:
            if r.get('filepath'):
                print(f"  ✓ {r.get('title')} -> {r.get('filepath')}")
            elif r.get('error'):
                print(f"  ✗ {r.get('title')}: {r.get('error')}")


if __name__ == '__main__':
    main()
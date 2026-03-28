# 博客流水线模块

from .rss_fetcher import RSSFetcher
from .summarizer import RSSSummarizer, summarize_content
from .expander import ArticleExpander, expand_article
from .openclaw_client import OpenClawClient, DirectSpawnClient, create_client
from .publisher import Publisher

# 别名，保持兼容
OpenClawExecutor = OpenClawClient

__all__ = [
    'RSSFetcher',
    'RSSSummarizer', 
    'summarize_content',
    'ArticleExpander',
    'expand_article',
    'OpenClawClient',
    'OpenClawExecutor',  # 兼容别名
    'DirectSpawnClient',
    'create_client',
    'Publisher'
]
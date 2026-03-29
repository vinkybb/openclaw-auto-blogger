# 博客流水线模块（延迟导入，避免仅使用 gateway 子模块时拉取 feedparser 等依赖）

__all__ = [
    "RSSFetcher",
    "RSSSummarizer",
    "summarize_content",
    "ArticleExpander",
    "expand_article",
    "OpenClawClient",
    "OpenClawExecutor",
    "DirectSpawnClient",
    "create_client",
    "Publisher",
]


def __getattr__(name: str):
    if name == "RSSFetcher":
        from .rss_fetcher import RSSFetcher

        return RSSFetcher
    if name == "RSSSummarizer":
        from .summarizer import RSSSummarizer

        return RSSSummarizer
    if name == "summarize_content":
        from .summarizer import summarize_content

        return summarize_content
    if name == "ArticleExpander":
        from .expander import ArticleExpander

        return ArticleExpander
    if name == "expand_article":
        from .expander import expand_article

        return expand_article
    if name == "OpenClawClient":
        from .openclaw_client import OpenClawClient

        return OpenClawClient
    if name == "OpenClawExecutor":
        from .openclaw_client import OpenClawClient

        return OpenClawClient
    if name == "DirectSpawnClient":
        from .openclaw_client import DirectSpawnClient

        return DirectSpawnClient
    if name == "create_client":
        from .openclaw_client import create_client

        return create_client
    if name == "Publisher":
        from .publisher import Publisher

        return Publisher
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

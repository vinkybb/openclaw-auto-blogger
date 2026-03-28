#!/usr/bin/env python3
"""
RSS Feed Fetcher Module
使用 requests + feedparser 实现带超时的 RSS 抓取
"""
import json
import sys
import argparse
import requests
import feedparser
from io import BytesIO


class RSSFetcher:
    """RSS Feed Fetcher 类（保持兼容性）"""
    
    def __init__(self, timeout=30):
        self.timeout = timeout
    
    def fetch(self, source_url, name=None, max_articles=10):
        """抓取 RSS feed 并返回文章列表"""
        return fetch_rss(source_url, name, max_articles, self.timeout)


def fetch_rss(source_url, name=None, max_articles=10, timeout=30):
    """抓取 RSS feed 并返回文章列表"""
    articles = []
    
    try:
        # 使用 requests 设置超时
        response = requests.get(source_url, timeout=timeout)
        response.raise_for_status()
        
        # 使用 feedparser 解析内容
        feed = feedparser.parse(BytesIO(response.content))
        
        if feed.bozo and feed.bozo_exception:
            print(f"RSS parse warning: {feed.bozo_exception}", file=sys.stderr)
        
        for entry in feed.entries[:max_articles]:
            article = {
                'title': entry.title or 'Untitled',
                'link': entry.link,
                'summary': entry.get('summary', entry.get('description', '')),
                'source': name or feed.feed.get('title', 'Unknown'),
                'published': entry.get('published', entry.get('updated', ''))
            }
            articles.append(article)
        
    except requests.Timeout:
        print(f"RSS fetch timeout: {source_url}", file=sys.stderr)
    except requests.RequestException as e:
        print(f"RSS fetch error: {e}", file=sys.stderr)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
    
    return articles


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True, help='RSS feed URL')
    parser.add_argument('--name', default='', help='Feed name')
    parser.add_argument('--max', type=int, default=10, help='Max articles')
    parser.add_argument('--timeout', type=int, default=30, help='Request timeout')
    
    args = parser.parse_args()
    
    articles = fetch_rss(args.source, args.name, args.max, args.timeout)
    
    # 输出 JSON 到 stdout
    print(json.dumps(articles, ensure_ascii=False))
#!/usr/bin/env python3
"""
RSS Feed Fetcher Module
使用 requests + feedparser 实现带超时的 RSS 抓取
"""
import json
import sys
import argparse
import time
import hashlib
import requests
import feedparser
from io import BytesIO
from datetime import datetime
from typing import List, Dict


class RSSFetcher:
    """RSS Feed Fetcher 类"""
    
    def __init__(self, timeout=30, config=None):
        self.timeout = timeout
        self.sources = []
        if config:
            if isinstance(config, dict):
                self.sources = config.get('sources', [])
            elif isinstance(config, list):
                self.sources = config
    
    def fetch_feed(self, url: str, name: str = "", max_articles=10) -> List[Dict]:
        """抓取单个RSS源，返回标准格式"""
        items = []
        
        try:
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            
            feed = feedparser.parse(BytesIO(response.content))
            
            for entry in feed.entries[:max_articles]:
                # 生成唯一ID
                item_id = hashlib.md5(entry.get('link', entry.get('title', '')).encode()).hexdigest()[:12]
                
                # 解析内容
                content = entry.get('content', [{}])[0].get('value', '')
                if not content:
                    content = entry.get('summary', entry.get('description', ''))
                
                # 解析日期
                published = entry.get('published_parsed') or entry.get('updated_parsed')
                if published and hasattr(published, '__len__') and len(published) >= 6:
                    try:
                        pub_date = datetime.fromtimestamp(time.mktime(published)).isoformat()
                    except (TypeError, ValueError, OSError):
                        pub_date = datetime.now().isoformat()
                else:
                    pub_date = datetime.now().isoformat()
                
                items.append({
                    'id': item_id,
                    'title': entry.get('title', '无标题'),
                    'link': entry.get('link', ''),
                    'content': content,
                    'summary': entry.get('summary', ''),
                    'author': entry.get('author', ''),
                    'published': pub_date,
                    'source_name': name,
                    'source_url': url,
                    'source_type': 'rss'
                })
                
        except requests.Timeout:
            print(f"[RSS] 抓取超时: {url}", file=sys.stderr)
        except requests.RequestException as e:
            print(f"[RSS] 抓取失败 {name} ({url}): {e}", file=sys.stderr)
        except Exception as e:
            print(f"[RSS] 异常: {e}", file=sys.stderr)
        
        return items
    
    def fetch(self, source_url, name=None, max_articles=10):
        """兼容旧接口"""
        return self.fetch_feed(source_url, name or "", max_articles)
    
    def fetch_all(self) -> List[Dict]:
        """抓取所有配置的 RSS 源"""
        all_items = []
        
        for source in self.sources:
            if not source.get('enabled', True):
                continue
            
            url = source.get('url', '')
            name = source.get('name', '')
            count = source.get('count', 10)
            
            if url:
                items = self.fetch_feed(url, name, count)
                all_items.extend(items)
                print(f"[RSS] {name}: {len(items)} 篇文章", file=sys.stderr)
        
        return all_items


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--rss', '--source', required=True, help='RSS feed URL')
    parser.add_argument('--name', default='', help='Feed name')
    parser.add_argument('--count', '--max', type=int, default=10, help='Max articles')
    parser.add_argument('--timeout', type=int, default=30, help='Request timeout')
    
    args = parser.parse_args()
    
    fetcher = RSSFetcher(timeout=args.timeout)
    articles = fetcher.fetch_feed(args.rss, args.name, args.count)
    
    # 输出 JSON 到 stdout
    print(json.dumps(articles, ensure_ascii=False, indent=2))
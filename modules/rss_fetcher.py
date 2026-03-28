"""
RSS订阅获取模块
"""

import feedparser
from datetime import datetime
from typing import List, Dict
import hashlib


class RSSFetcher:
    def __init__(self, config: dict):
        self.sources = config.get('sources', [])
        self.fetch_interval = config.get('fetch_interval', 3600)
    
    def fetch_feed(self, url: str, name: str = "") -> List[Dict]:
        """抓取单个RSS源"""
        items = []
        
        try:
            feed = feedparser.parse(url)
            
            for entry in feed.entries:
                # 生成唯一ID
                item_id = hashlib.md5(entry.get('link', entry.get('title', '')).encode()).hexdigest()[:12]
                
                # 解析内容
                content = entry.get('content', [{}])[0].get('value', '')
                if not content:
                    content = entry.get('summary', entry.get('description', ''))
                
                # 解析日期
                published = entry.get('published_parsed') or entry.get('updated_parsed')
                if published:
                    pub_date = datetime(*published[:6]).isoformat()
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
                    'source_url': url
                })
                
        except Exception as e:
            print(f"[RSS] 抓取失败 {name} ({url}): {e}")
        
        return items
    
    def fetch_all(self) -> List[Dict]:
        """抓取所有启用的RSS源"""
        all_items = []
        
        for source in self.sources:
            if source.get('enabled', True):
                items = self.fetch_feed(source['url'], source.get('name', ''))
                all_items.extend(items)
                print(f"[RSS] {source.get('name', source['url'])}: {len(items)} 条")
        
        # 按日期排序
        all_items.sort(key=lambda x: x['published'], reverse=True)
        
        return all_items
    
    def add_source(self, name: str, url: str, config: dict) -> dict:
        """添加新的RSS源"""
        sources = config.get('rss', {}).get('sources', [])
        sources.append({
            'name': name,
            'url': url,
            'enabled': True
        })
        return config
    
    def remove_source(self, url: str, config: dict) -> dict:
        """移除RSS源"""
        sources = config.get('rss', {}).get('sources', [])
        config['rss']['sources'] = [s for s in sources if s['url'] != url]
        return config
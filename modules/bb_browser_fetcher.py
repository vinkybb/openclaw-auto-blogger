#!/usr/bin/env python3
"""
BB-Browser Fetcher Module
使用 bb-browser 抓取网站内容，替代传统 RSS fetcher
支持：bb-browser 站点命令 + 自定义 RSS URL
"""
import json
import subprocess
import hashlib
import time
import feedparser
import requests
from datetime import datetime
from typing import List, Dict, Optional
from io import BytesIO


class BBBrowserFetcher:
    """BB-Browser 抓取器"""
    
    # bb-browser 支持的站点命令映射
    SITE_COMMANDS = {
        # 新闻类
        'hackernews_top': 'hackernews/top',
        'hackernews_best': 'hackernews/best',
        'hackernews_new': 'hackernews/new',
        'bbc_news': 'bbc/news',
        'reuters_world': 'reuters/world',
        '36kr_newsflash': '36kr/newsflash',
        
        # 社交/社区
        'reddit_hot': 'reddit/hot',
        'v2ex_hot': 'v2ex/hot',
        'v2ex_latest': 'v2ex/latest',
        'weibo_hot': 'weibo/hot',
        
        # 视频/媒体
        'bilibili_popular': 'bilibili/popular',
        'bilibili_trending': 'bilibili/trending',
        'youtube_trending': 'youtube/trending',
        
        # 财经
        'xueqiu_hot': 'xueqiu/hot',
        'xueqiu_hot-stock': 'xueqiu/hot-stock',
        
        # 搜索
        'baidu_search': 'baidu/search',
        'bing_search': 'bing/search',
        'google_search': 'google/search',
    }
    
    def __init__(self, cdp_port: int = 9222, timeout: int = 30):
        self.cdp_port = cdp_port
        self.timeout = timeout
        self._check_chrome()
    
    def _check_chrome(self) -> bool:
        """检查 Chrome CDP 是否可用"""
        try:
            result = subprocess.run(
                ['curl', '-s', f'http://localhost:{self.cdp_port}/json/version'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout:
                return True
        except:
            pass
        
        # 尝试启动 Chrome
        print(f"[BB-Browser] Chrome not running on port {self.cdp_port}, starting...")
        subprocess.Popen(
            ['google-chrome', '--headless', '--no-sandbox', '--disable-gpu',
             f'--remote-debugging-port={self.cdp_port}'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        time.sleep(3)
        return True
    
    def fetch_by_command(self, site_command: str, count: int = 10) -> List[Dict]:
        """使用 bb-browser 站点命令抓取"""
        items = []
        
        try:
            cmd = [
                'bb-browser', '--port', str(self.cdp_port),
                'site', site_command, str(count)
            ]
            
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self.timeout
            )
            
            if result.returncode != 0:
                print(f"[BB-Browser] Error: {result.stderr}")
                return items
            
            # 解析 JSON 输出
            data = json.loads(result.stdout)
            
            # 处理不同格式的输出
            if isinstance(data, list):
                for entry in data:
                    item_id = hashlib.md5(
                        (entry.get('url', '') or entry.get('link', '') or 
                         entry.get('title', '')).encode()
                    ).hexdigest()[:12]
                    
                    items.append({
                        'id': item_id,
                        'title': entry.get('title', '无标题'),
                        'link': entry.get('url', entry.get('link', '')),
                        'content': entry.get('content', entry.get('text', '')),
                        'summary': entry.get('summary', entry.get('text', '')),
                        'author': entry.get('author', entry.get('by', '')),
                        'published': entry.get('time', entry.get('published', datetime.now().isoformat())),
                        'source_name': site_command,
                        'source_type': 'bb-browser'
                    })
            elif isinstance(data, dict):
                # 处理嵌套结构 (如 {items: [...]} 或 {data: [...]})
                entries = data.get('items', data.get('data', data.get('results', [])))
                for entry in entries:
                    item_id = hashlib.md5(
                        (entry.get('url', '') or entry.get('link', '')).encode()
                    ).hexdigest()[:12]
                    items.append(self._parse_entry(entry, item_id, site_command))
                    
        except subprocess.TimeoutExpired:
            print(f"[BB-Browser] Timeout: {site_command}")
        except json.JSONDecodeError as e:
            print(f"[BB-Browser] JSON parse error: {e}")
        except Exception as e:
            print(f"[BB-Browser] Error: {e}")
        
        return items
    
    def _parse_entry(self, entry: dict, item_id: str, source: str) -> Dict:
        """解析单个 entry"""
        return {
            'id': item_id,
            'title': entry.get('title', '无标题'),
            'link': entry.get('url', entry.get('link', '')),
            'content': entry.get('content', entry.get('text', entry.get('description', ''))),
            'summary': entry.get('summary', entry.get('text', '')),
            'author': entry.get('author', entry.get('by', entry.get('user', ''))),
            'published': entry.get('time', entry.get('published', entry.get('date', datetime.now().isoformat()))),
            'source_name': source,
            'source_type': 'bb-browser'
        }
    
    def fetch_rss(self, url: str, name: str = "", max_articles: int = 10) -> List[Dict]:
        """传统 RSS 抓取（后备方案）"""
        items = []
        
        try:
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            
            feed = feedparser.parse(BytesIO(response.content))
            
            for entry in feed.entries[:max_articles]:
                item_id = hashlib.md5(entry.get('link', '').encode()).hexdigest()[:12]
                
                content = entry.get('content', [{}])[0].get('value', '')
                if not content:
                    content = entry.get('summary', entry.get('description', ''))
                
                published = entry.get('published_parsed') or entry.get('updated_parsed')
                if published:
                    try:
                        pub_date = datetime.fromtimestamp(time.mktime(published)).isoformat()
                    except:
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
                    'source_name': name or feed.feed.get('title', 'RSS'),
                    'source_url': url,
                    'source_type': 'rss'
                })
                
        except Exception as e:
            print(f"[RSS] 抓取失败 {name} ({url}): {e}")
        
        return items
    
    def fetch(self, source: dict) -> List[Dict]:
        """统一抓取接口，支持多种源类型"""
        source_type = source.get('type', 'rss')
        
        if source_type == 'bb-browser':
            # bb-browser 站点命令
            command = source.get('command')
            if command in self.SITE_COMMANDS:
                command = self.SITE_COMMANDS[command]
            count = source.get('count', 10)
            return self.fetch_by_command(command, count)
        
        elif source_type == 'rss':
            # 传统 RSS
            url = source.get('url')
            name = source.get('name', '')
            max_articles = source.get('count', 10)
            return self.fetch_rss(url, name, max_articles)
        
        elif source_type == 'custom':
            # 自定义 bb-browser 命令
            command = source.get('command')
            count = source.get('count', 10)
            return self.fetch_by_command(command, count)
        
        else:
            print(f"[Fetcher] Unknown source type: {source_type}")
            return []
    
    def fetch_all(self, sources: List[dict]) -> List[Dict]:
        """批量抓取多个源"""
        all_items = []
        
        for source in sources:
            items = self.fetch(source)
            all_items.extend(items)
            print(f"[Fetcher] {source.get('name', source.get('command', 'unknown'))}: {len(items)} items")
        
        return all_items


def main():
    """CLI 入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='BB-Browser RSS Fetcher')
    parser.add_argument('--command', help='bb-browser site command (e.g. hackernews/top)')
    parser.add_argument('--rss', help='RSS URL (fallback)')
    parser.add_argument('--name', default='', help='Source name')
    parser.add_argument('--count', type=int, default=10, help='Max items')
    parser.add_argument('--port', type=int, default=9222, help='Chrome CDP port')
    parser.add_argument('--timeout', type=int, default=30, help='Timeout seconds')
    
    args = parser.parse_args()
    
    fetcher = BBBrowserFetcher(cdp_port=args.port, timeout=args.timeout)
    
    if args.command:
        items = fetcher.fetch_by_command(args.command, args.count)
    elif args.rss:
        items = fetcher.fetch_rss(args.rss, args.name, args.count)
    else:
        print("Error: need --command or --rss")
        return
    
    print(json.dumps(items, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
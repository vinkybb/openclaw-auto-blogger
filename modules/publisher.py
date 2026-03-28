"""
内容发布模块
支持多种发布目标：本地文件、GitHub Pages、WordPress、Webhook
"""

import os
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
import requests


class Publisher:
    def __init__(self, config: dict):
        self.config = config or {}
    
    def publish(self, title: str, content: str, tags: list = None, image_url: str = None) -> Dict:
        """
        发布内容到配置的目标
        
        Args:
            title: 文章标题
            content: Markdown内容
            tags: 标签列表
            image_url: 封面图URL
        
        Returns:
            发布结果
        """
        results = {}
        tags = tags or []
        
        # 1. 本地静态博客
        if self.config.get('local', {}).get('enabled', True):
            results['local'] = self._publish_local(title, content, tags, image_url)
        
        # 2. GitHub Pages
        if self.config.get('github', {}).get('enabled', False):
            results['github'] = self._publish_github(title, content, tags, image_url)
        
        # 3. WordPress
        if self.config.get('wordpress', {}).get('enabled', False):
            results['wordpress'] = self._publish_wordpress(title, content, tags, image_url)
        
        # 4. 自定义Webhook
        if self.config.get('webhook', {}).get('enabled', False):
            results['webhook'] = self._publish_webhook(title, content, tags, image_url)
        
        return results
    
    def _publish_local(self, title: str, content: str, tags: list, image_url: str = None) -> Dict:
        """发布到本地静态博客"""
        local_config = self.config.get('local', {})
        blog_type = local_config.get('type', 'hugo')
        content_dir = Path(local_config.get('content_dir', './output/posts'))
        
        # 确保目录存在
        content_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成文件名
        safe_title = self._safe_filename(title)
        date_prefix = datetime.now().strftime('%Y-%m-%d')
        filename = f"{date_prefix}-{safe_title}.md"
        filepath = content_dir / filename
        
        # 生成front matter
        if blog_type == 'hugo':
            front_matter = self._create_hugo_front_matter(title, tags, image_url)
        elif blog_type == 'hexo':
            front_matter = self._create_hexo_front_matter(title, tags, image_url)
        elif blog_type == 'jekyll':
            front_matter = self._create_jekyll_front_matter(title, tags, image_url)
        else:
            front_matter = self._create_hugo_front_matter(title, tags, image_url)
        
        # 写入文件
        full_content = front_matter + "\n" + content
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(full_content)
        
        print(f"[发布] 本地文件已保存: {filepath}")
        
        return {
            'success': True,
            'path': str(filepath),
            'filename': filename,
            'url': f"file://{filepath}"
        }
    
    def _create_hugo_front_matter(self, title: str, tags: list, image_url: str = None) -> str:
        """创建Hugo格式的front matter"""
        import yaml
        
        meta = {
            'title': title,
            'date': datetime.now().isoformat(),
            'draft': False,
            'tags': tags,
        }
        
        if image_url:
            meta['cover'] = image_url
        
        return "---\n" + yaml.dump(meta, allow_unicode=True, default_flow_style=False) + "---"
    
    def _create_hexo_front_matter(self, title: str, tags: list, image_url: str = None) -> str:
        """创建Hexo格式的front matter"""
        import yaml
        
        meta = {
            'title': title,
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'tags': tags,
        }
        
        if image_url:
            meta['photos'] = [image_url]
        
        return "---\n" + yaml.dump(meta, allow_unicode=True, default_flow_style=False) + "---"
    
    def _create_jekyll_front_matter(self, title: str, tags: list, image_url: str = None) -> str:
        """创建Jekyll格式的front matter"""
        import yaml
        
        meta = {
            'layout': 'post',
            'title': title,
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S %z'),
            'categories': tags[:1] if tags else [],
            'tags': tags[1:] if len(tags) > 1 else []
        }
        
        if image_url:
            meta['image'] = image_url
        
        return "---\n" + yaml.dump(meta, allow_unicode=True, default_flow_style=False) + "---"
    
    def _publish_github(self, title: str, content: str, tags: list, image_url: str = None) -> Dict:
        """发布到GitHub Pages"""
        github_config = self.config.get('github', {})
        repo = github_config.get('repo', '')
        branch = github_config.get('branch', 'main')
        token = github_config.get('token', '')
        commit_msg = github_config.get('commit_message', 'Auto publish: {title}')
        
        if not all([repo, token]):
            return {'success': False, 'error': 'GitHub配置不完整'}
        
        try:
            # 首先保存到本地
            local_result = self._publish_local(title, content, tags, image_url)
            filepath = Path(local_result['path'])
            
            # 使用Git API推送
            import base64
            
            # 读取文件内容
            with open(filepath, 'rb') as f:
                file_content = base64.b64encode(f.read()).decode()
            
            # GitHub API
            api_url = f"https://api.github.com/repos/{repo}/contents/posts/{filepath.name}"
            
            headers = {
                'Authorization': f'token {token}',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            # 检查文件是否存在
            get_response = requests.get(api_url, headers=headers)
            sha = None
            if get_response.status_code == 200:
                sha = get_response.json()['sha']
            
            # 创建或更新文件
            data = {
                'message': commit_msg.format(title=title),
                'content': file_content,
                'branch': branch
            }
            if sha:
                data['sha'] = sha
            
            response = requests.put(api_url, headers=headers, json=data)
            
            if response.status_code in [200, 201]:
                result = response.json()
                return {
                    'success': True,
                    'url': result['content']['html_url'],
                    'sha': result['content']['sha']
                }
            else:
                return {
                    'success': False,
                    'error': f"GitHub API错误: {response.status_code}"
                }
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _publish_wordpress(self, title: str, content: str, tags: list, image_url: str = None) -> Dict:
        """发布到WordPress"""
        wp_config = self.config.get('wordpress', {})
        url = wp_config.get('url', '').rstrip('/')
        username = wp_config.get('username', '')
        password = wp_config.get('password', '')
        
        if not all([url, username, password]):
            return {'success': False, 'error': 'WordPress配置不完整'}
        
        try:
            # 转换Markdown为HTML
            import markdown
            html_content = markdown.markdown(content, extensions=['tables', 'fenced_code'])
            
            # 创建文章
            post_data = {
                'title': title,
                'content': html_content,
                'status': 'publish',
                'tags': tags
            }
            
            response = requests.post(
                f"{url}/posts",
                auth=(username, password),
                json=post_data,
                timeout=30
            )
            
            if response.status_code == 201:
                result = response.json()
                return {
                    'success': True,
                    'id': result['id'],
                    'url': result['link']
                }
            else:
                return {
                    'success': False,
                    'error': f"WordPress API错误: {response.status_code}"
                }
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _publish_webhook(self, title: str, content: str, tags: list, image_url: str = None) -> Dict:
        """通过Webhook发布"""
        webhook_config = self.config.get('webhook', {})
        url = webhook_config.get('url', '')
        method = webhook_config.get('method', 'POST')
        headers = webhook_config.get('headers', {})
        
        if not url:
            return {'success': False, 'error': 'Webhook URL未配置'}
        
        payload = {
            'title': title,
            'content': content,
            'tags': tags,
            'image_url': image_url,
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            response = requests.request(
                method,
                url,
                json=payload,
                headers=headers,
                timeout=30
            )
            
            return {
                'success': response.status_code < 400,
                'status_code': response.status_code,
                'response': response.text[:500]  # 截取前500字符
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _safe_filename(self, title: str) -> str:
        """生成安全的文件名"""
        import re
        
        # 移除特殊字符
        safe = re.sub(r'[^\w\s-]', '', title)
        safe = re.sub(r'[-\s]+', '-', safe)
        
        return safe.lower()[:50]
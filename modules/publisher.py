"""
内容发布模块
支持多种发布目标：本地文件、GitHub Pages、WordPress、Webhook

GitHub Pages 支持两种方式：
1. API Token 方式：使用 GitHub Personal Access Token
2. SSH/Deploy Key 方式：使用 Git 命令行 + SSH 密钥
"""

import os
import json
import subprocess
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import urlparse
import requests


class Publisher:
    def __init__(self, config: dict):
        self.config = config or {}
    
    def publish(
        self,
        title: str,
        content: str,
        tags: list = None,
        image_url: str = None,
        apply_local: bool = True,
    ) -> Dict:
        """
        发布内容到配置的目标

        Args:
            apply_local: 为 False 时跳过本地写入（例如 CLI 已由 save_article 落盘时避免重复文件）。
        """
        results = {}
        tags = tags or []

        if apply_local and self.config.get('local', {}).get('enabled', True):
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
        """
        发布到GitHub Pages
        支持两种方式：
        1. SSH/Deploy Key 方式（推荐）：设置 use_ssh: true，无需 token
        2. API Token 方式：设置 token
        """
        github_config = self.config.get('github', {})
        use_ssh = github_config.get('use_ssh', False)
        
        # 优先使用 SSH 方式
        if use_ssh:
            return self._publish_github_ssh(title, content, tags, image_url)
        
        # 回退到 API Token 方式
        return self._publish_github_api(title, content, tags, image_url)
    
    def _publish_github_ssh(self, title: str, content: str, tags: list, image_url: str = None) -> Dict:
        """
        通过 SSH + Deploy Key 发布到 GitHub Pages
        
        配置示例：
        github:
          enabled: true
          use_ssh: true
          repo: "your-username/your-blog"
          branch: "main"
          posts_dir: "posts"  # 可选，默认 posts
          commit_message: "Auto publish: {title}"
        
        前提条件：
        1. 已配置 SSH Deploy Key（GitHub 仓库 Settings → Deploy keys）
        2. 服务器上已安装 git 并配置了 SSH 密钥
        """
        github_config = self.config.get('github', {})
        repo = github_config.get('repo', '')
        branch = github_config.get('branch', 'main')
        posts_dir = github_config.get('posts_dir', 'posts')
        commit_msg = github_config.get('commit_message', 'Auto publish: {title}')
        ssh_key_path = github_config.get('ssh_key_path')  # 可选：指定 SSH 密钥路径
        
        if not repo:
            return {'success': False, 'error': 'GitHub repo 未配置（格式: username/repo）'}
        
        try:
            # 首先保存到本地
            local_result = self._publish_local(title, content, tags, image_url)
            filepath = Path(local_result['path'])
            
            # 构建 SSH URL
            ssh_url = f"git@github.com:{repo}.git"
            
            # 创建临时工作目录
            with tempfile.TemporaryDirectory() as tmpdir:
                work_dir = Path(tmpdir) / "repo"
                
                # 设置 Git 环境变量
                git_env = os.environ.copy()
                if ssh_key_path:
                    git_env['GIT_SSH_COMMAND'] = f'ssh -i {ssh_key_path} -o IdentitiesOnly=yes -o StrictHostKeyChecking=no'
                else:
                    git_env['GIT_SSH_COMMAND'] = 'ssh -o StrictHostKeyChecking=no'
                
                # 配置 git 用户信息
                git_config = ['git', '-C', str(work_dir)]
                
                def run_git(args, check=True):
                    """执行 git 命令"""
                    cmd = ['git', '-C', str(work_dir)] + args
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        env=git_env,
                        timeout=180
                    )
                    if check and result.returncode != 0:
                        raise Exception(f"Git 命令失败: {result.stderr}")
                    return result
                
                # 克隆仓库（浅克隆，只取最新提交）
                print(f"[GitHub SSH] 克隆仓库: {repo}")
                clone_result = subprocess.run(
                    ['git', 'clone', '--depth', '1', '-b', branch, ssh_url, str(work_dir)],
                    capture_output=True,
                    text=True,
                    env=git_env,
                    timeout=300
                )
                if clone_result.returncode != 0:
                    # 如果分支不存在，尝试克隆默认分支
                    clone_result = subprocess.run(
                        ['git', 'clone', '--depth', '1', ssh_url, str(work_dir)],
                        capture_output=True,
                        text=True,
                        env=git_env,
                        timeout=300
                    )
                    if clone_result.returncode != 0:
                        return {'success': False, 'error': f"克隆仓库失败: {clone_result.stderr}"}
                
                # 配置 git 用户
                run_git(['config', 'user.email', 'blog-pipeline@openclaw.ai'])
                run_git(['config', 'user.name', 'Blog Pipeline'])
                
                # 确保文章目录存在
                posts_path = work_dir / posts_dir
                posts_path.mkdir(parents=True, exist_ok=True)
                
                # 复制文件到仓库
                dest_file = posts_path / filepath.name
                shutil.copy(filepath, dest_file)
                
                # 检查是否有变更
                run_git(['add', str(dest_file.relative_to(work_dir))])
                status_result = run_git(['status', '--porcelain'])
                
                if not status_result.stdout.strip():
                    return {
                        'success': True,
                        'url': f"https://github.com/{repo}/blob/{branch}/{posts_dir}/{filepath.name}",
                        'message': '文件无变更，跳过提交'
                    }
                
                # 提交并推送
                run_git(['commit', '-m', commit_msg.format(title=title)])
                push_result = run_git(['push', 'origin', branch], check=False)
                
                if push_result.returncode != 0:
                    return {'success': False, 'error': f"推送失败: {push_result.stderr}"}
                
                print(f"[GitHub SSH] 推送成功: {filepath.name}")
                
                return {
                    'success': True,
                    'url': f"https://github.com/{repo}/blob/{branch}/{posts_dir}/{filepath.name}",
                    'filename': filepath.name
                }
                
        except subprocess.TimeoutExpired:
            return {'success': False, 'error': 'Git 操作超时'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _publish_github_api(self, title: str, content: str, tags: list, image_url: str = None) -> Dict:
        """通过 GitHub API Token 发布（传统方式）"""
        github_config = self.config.get('github', {})
        repo = github_config.get('repo', '')
        branch = github_config.get('branch', 'main')
        token = github_config.get('token', '') or os.environ.get('GITHUB_TOKEN', '')
        commit_msg = github_config.get('commit_message', 'Auto publish: {title}')
        
        if not repo:
            return {'success': False, 'error': 'GitHub repo 未配置（格式: username/repo）'}
        if not token:
            return {'success': False, 'error': 'GitHub token 未配置（设置 token 或环境变量 GITHUB_TOKEN）'}
        
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
    
    def _wordpress_rest_posts_url(self, wp_config: dict) -> str:
        """
        解析 WordPress REST 文章端点。
        支持：站点根 URL、完整 .../wp-json/...、或旧的 xmlrpc.php（将替换为 /wp-json/wp/v2/posts）。
        """
        raw = (wp_config.get("url") or "").strip().rstrip("/")
        if not raw:
            return ""
        if "/wp-json/" in raw:
            if raw.endswith("/posts"):
                return raw
            return raw.rstrip("/") + "/posts"
        if "xmlrpc.php" in raw:
            base = raw.split("/xmlrpc.php")[0].rstrip("/")
            return f"{base}/wp-json/wp/v2/posts"
        return f"{raw}/wp-json/wp/v2/posts"

    def _publish_wordpress(self, title: str, content: str, tags: list, image_url: str = None) -> Dict:
        """通过 WordPress REST API 发布（Application Password 基本认证）。"""
        wp_config = self.config.get("wordpress", {})
        posts_url = self._wordpress_rest_posts_url(wp_config)
        username = wp_config.get("username", "")
        password = wp_config.get("password", "")

        if not all([posts_url, username, password]):
            return {"success": False, "error": "WordPress 配置不完整（需 url、username、password）"}

        try:
            import markdown

            html_content = markdown.markdown(
                content, extensions=["tables", "fenced_code"]
            )

            post_data = {
                "title": title,
                "content": html_content,
                "status": "publish",
            }

            response = requests.post(
                posts_url,
                auth=(username, password),
                json=post_data,
                timeout=30,
            )

            if response.status_code == 201:
                result = response.json()
                return {
                    "success": True,
                    "id": result.get("id"),
                    "url": result.get("link", ""),
                }
            err_body = response.text[:500]
            return {
                "success": False,
                "error": f"WordPress REST 错误 HTTP {response.status_code}: {err_body}",
            }

        except Exception as e:
            return {"success": False, "error": str(e)}
    
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

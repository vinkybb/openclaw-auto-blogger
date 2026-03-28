"""
配图生成模块
支持DALL-E、Stability AI、Unsplash随机图
"""

import requests
import os
import random
from typing import Optional
from pathlib import Path


class ImageGenerator:
    def __init__(self, config: dict):
        self.enabled = config.get('enabled', False)
        self.provider = config.get('provider', 'dalle')
        self.api_key = config.get('api_key', '')
        self.base_url = config.get('base_url', 'https://api.openai.com/v1')
        self.output_dir = Path(__file__).parent.parent / 'output' / 'images'
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate(self, title: str, description: str = None) -> Optional[str]:
        """
        生成配图
        
        Args:
            title: 文章标题，用于生成图像
            description: 可选的详细描述
        
        Returns:
            图像URL或本地路径
        """
        if not self.enabled:
            return None
        
        if self.provider == 'dalle':
            return self._generate_dalle(title, description)
        elif self.provider == 'stability':
            return self._generate_stability(title, description)
        elif self.provider == 'unsplash':
            return self._get_unsplash(title)
        else:
            print(f"[配图] 未知的提供商: {self.provider}")
            return None
    
    def _generate_dalle(self, title: str, description: str = None) -> Optional[str]:
        """使用DALL-E生成图像"""
        if not self.api_key:
            print("[配图] DALL-E未配置API密钥")
            return None
        
        prompt = f"A professional blog header image for an article titled: {title}"
        if description:
            prompt += f". {description[:100]}"
        
        try:
            response = requests.post(
                f"{self.base_url}/images/generations",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "dall-e-3",
                    "prompt": prompt,
                    "n": 1,
                    "size": "1792x1024",  # 博客封面常用比例
                    "quality": "standard"
                },
                timeout=60
            )
            
            if response.status_code == 200:
                result = response.json()
                image_url = result['data'][0]['url']
                
                # 下载图片到本地
                return self._download_image(image_url, title)
            else:
                print(f"[配图] DALL-E错误: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"[配图] DALL-E生成失败: {e}")
            return None
    
    def _generate_stability(self, title: str, description: str = None) -> Optional[str]:
        """使用Stability AI生成图像"""
        if not self.api_key:
            print("[配图] Stability AI未配置API密钥")
            return None
        
        prompt = f"Blog header image, professional style: {title}"
        
        try:
            # Stability AI API调用
            response = requests.post(
                "https://api.stability.ai/v1/generation/stable-diffusion-xl-1024-v1-0/text-to-image",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "text_prompts": [{"text": prompt}],
                    "cfg_scale": 7,
                    "height": 1024,
                    "width": 1792,
                    "samples": 1,
                    "steps": 30
                },
                timeout=60
            )
            
            if response.status_code == 200:
                result = response.json()
                # 保存base64图像
                import base64
                image_data = base64.b64decode(result['artifacts'][0]['base64'])
                
                filename = self._safe_filename(title) + '.png'
                filepath = self.output_dir / filename
                
                with open(filepath, 'wb') as f:
                    f.write(image_data)
                
                return str(filepath)
            else:
                print(f"[配图] Stability错误: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"[配图] Stability生成失败: {e}")
            return None
    
    def _get_unsplash(self, title: str) -> Optional[str]:
        """从Unsplash获取相关图片"""
        # 提取关键词
        keywords = title.split()[:3]
        keyword = random.choice(keywords) if keywords else 'technology'
        
        # Unsplash Source API (免费，无需密钥)
        # 注意：此API已逐步废弃，建议使用正式API
        try:
            url = f"https://source.unsplash.com/1792x1024/?{keyword},blog,technology"
            
            # 下载图片
            return self._download_image(url, title)
            
        except Exception as e:
            print(f"[配图] Unsplash获取失败: {e}")
            return None
    
    def _download_image(self, url: str, title: str) -> Optional[str]:
        """下载图片到本地"""
        try:
            response = requests.get(url, timeout=30)
            if response.status_code == 200:
                filename = self._safe_filename(title) + '.jpg'
                filepath = self.output_dir / filename
                
                with open(filepath, 'wb') as f:
                    f.write(response.content)
                
                print(f"[配图] 已保存: {filepath}")
                return str(filepath)
            return None
        except Exception as e:
            print(f"[配图] 下载失败: {e}")
            return None
    
    def _safe_filename(self, title: str) -> str:
        """生成安全的文件名"""
        import re
        from datetime import datetime
        
        # 移除特殊字符
        safe = re.sub(r'[^\w\s-]', '', title)
        safe = re.sub(r'[-\s]+', '-', safe)[:50]
        
        # 添加时间戳
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        
        return f"{safe}-{timestamp}"
"""
OpenClaw 客户端模块
封装对 OpenClaw 框架的调用，使用 sessions_spawn API 来执行 AI 任务

注意：此模块设计为在 OpenClaw 环境外部的 Python 脚本中使用。
如果要在 OpenClaw 内部直接调用，应使用 sessions_spawn 工具。
"""

import os
import json
import subprocess
import tempfile
from typing import Optional, Dict, Any


class OpenClawClient:
    """
    OpenClaw API 客户端
    
    通过 HTTP API 或 CLI 与 OpenClaw Gateway 通信
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化 OpenClaw 客户端
        
        Args:
            config: 配置字典，包含:
                - base_url: OpenClaw Gateway URL (默认 http://localhost:3000)
                - timeout: 请求超时时间 (默认 300秒)
                - model: 使用的模型 (可选)
        """
        self.config = config or {}
        self.base_url = self.config.get('base_url', os.environ.get('OPENCLAW_URL', 'http://localhost:3000'))
        self.timeout = self.config.get('timeout', 300)
        self.default_model = self.config.get('model')
    
    def spawn_agent(self, task: str, model: str = None, timeout_seconds: int = None) -> Dict[str, Any]:
        """
        生成一个 subagent 来执行任务
        
        这是核心方法，用于发送任务给 OpenClaw 的 subagent 执行
        
        Args:
            task: 任务描述/提示词
            model: 使用的模型 (可选)
            timeout_seconds: 超时时间 (可选)
            
        Returns:
            包含执行结果的字典
        """
        # 首先尝试使用 openclaw CLI
        result = self._try_cli_spawn(task, model, timeout_seconds)
        if result is not None:
            return result
        
        # 如果 CLI 失败，尝试 HTTP API
        return self._try_http_spawn(task, model, timeout_seconds)
    
    def _try_cli_spawn(self, task: str, model: str = None, timeout_seconds: int = None) -> Optional[Dict[str, Any]]:
        """尝试使用 openclaw CLI 执行任务"""
        try:
            # 写入临时文件
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                f.write(task)
                task_file = f.name
            
            try:
                # 构建 openclaw exec 命令
                # 注意：实际 CLI 可能不同，需要根据 openclaw 的实际命令调整
                cmd = ['openclaw', 'exec', '--file', task_file]
                if model:
                    cmd.extend(['--model', model])
                if timeout_seconds:
                    cmd.extend(['--timeout', str(timeout_seconds)])
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds or self.timeout
                )
                
                if result.returncode == 0:
                    return {
                        'success': True,
                        'output': result.stdout.strip(),
                        'result': result.stdout.strip()
                    }
                else:
                    # CLI 执行失败，返回 None 让 HTTP 方式尝试
                    return None
                    
            finally:
                os.unlink(task_file)
                
        except Exception:
            return None
    
    def _try_http_spawn(self, task: str, model: str = None, timeout_seconds: int = None) -> Dict[str, Any]:
        """尝试使用 HTTP API 执行任务"""
        try:
            import requests
        except ImportError:
            return {
                'success': False,
                'error': 'requests 库未安装，请运行: pip install requests',
                'output': ''
            }
        
        payload = {
            "task": task,
            "mode": "run",
            "runtime": "subagent"
        }
        
        if model or self.default_model:
            payload["model"] = model or self.default_model
        
        if timeout_seconds:
            payload["timeoutSeconds"] = timeout_seconds
        
        try:
            # 尝试不同的 API 端点
            endpoints = [
                f"{self.base_url}/api/sessions/spawn",
                f"{self.base_url}/spawn",
                f"{self.base_url}/api/spawn"
            ]
            
            for endpoint in endpoints:
                try:
                    response = requests.post(
                        endpoint,
                        json=payload,
                        timeout=timeout_seconds or self.timeout
                    )
                    if response.status_code == 200:
                        data = response.json()
                        return {
                            'success': True,
                            'output': self._extract_text(data),
                            'result': self._extract_text(data)
                        }
                except requests.exceptions.HTTPError:
                    continue
                except requests.exceptions.RequestException:
                    continue
            
            # 所有端点都失败
            return {
                'success': False,
                'error': '无法连接到 OpenClaw Gateway，请确保服务正在运行',
                'output': ''
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'output': ''
            }
    
    def _extract_text(self, data: Any) -> str:
        """从响应数据中提取文本"""
        if isinstance(data, str):
            return data
        if isinstance(data, dict):
            for key in ['result', 'output', 'content', 'text', 'message', 'response']:
                if key in data:
                    return self._extract_text(data[key])
            if 'data' in data:
                return self._extract_text(data['data'])
        return json.dumps(data, ensure_ascii=False)
    
    def summarize(self, content: str, style: str = "简洁") -> str:
        """
        使用 OpenClaw 生成内容摘要
        
        Args:
            content: 需要摘要的内容
            style: 摘要风格 (简洁/详细/专业)
            
        Returns:
            摘要文本
        """
        task = f"""请对以下内容进行{style}摘要，保留核心观点和关键信息：

---
{content}
---

要求：
1. 保持客观，不添加个人观点
2. 突出最重要的信息
3. 语言流畅，逻辑清晰
4. 摘要长度控制在 200-400 字

请直接输出摘要内容，不要添加任何前言或后缀。"""

        result = self.spawn_agent(task, timeout_seconds=60)
        return self._extract_result(result)
    
    def expand(self, title: str, summary: str, source_url: str = None, 
               style: str = "深度分析", word_count: int = 1500) -> Dict[str, Any]:
        """
        使用 OpenClaw 扩写内容为完整文章
        
        Args:
            title: 文章标题
            summary: 内容摘要
            source_url: 来源链接 (可选)
            style: 写作风格
            word_count: 目标字数
            
        Returns:
            包含 title, content, tags 的字典
        """
        source_info = f"\n\n参考来源：{source_url}" if source_url else ""
        
        task = f"""请基于以下摘要扩写为一篇完整的博客文章：

标题：{title}

摘要：
{summary}
{source_info}

要求：
1. 写作风格：{style}
2. 目标字数：{word_count} 字左右
3. 文章结构清晰，包含引言、正文、结论
4. 语言生动有趣，适合阅读
5. 在文末添加 3-5 个相关标签

输出格式：
第一行输出文章标题
然后用 --- 分隔
之后是正文内容
最后用 --- 分隔
在最后一行输出标签，用逗号分隔

示例：
这是文章标题
---
这里是正文内容...
---
标签1, 标签2, 标签3"""

        result = self.spawn_agent(task, timeout_seconds=120)
        text = self._extract_result(result)
        
        return self._parse_article(text, title)
    
    def generate_tags(self, content: str, count: int = 5) -> list:
        """
        为内容生成标签
        
        Args:
            content: 文章内容
            count: 标签数量
            
        Returns:
            标签列表
        """
        task = f"""请为以下文章生成 {count} 个相关标签：

{content[:1000]}...

只输出标签，用逗号分隔。例如：技术, AI, 编程"""

        result = self.spawn_agent(task, timeout_seconds=30)
        text = self._extract_result(result)
        
        # 解析标签
        tags = [t.strip() for t in text.replace('，', ',').split(',') if t.strip()]
        return tags[:count]
    
    def translate(self, content: str, target_lang: str = "中文") -> str:
        """
        翻译内容
        
        Args:
            content: 需要翻译的内容
            target_lang: 目标语言
            
        Returns:
            翻译后的文本
        """
        task = f"""请将以下内容翻译成{target_lang}：

{content}

只输出翻译结果，不要添加任何说明。"""

        result = self.spawn_agent(task, timeout_seconds=60)
        return self._extract_result(result)
    
    def _extract_result(self, result: Dict[str, Any]) -> str:
        """从 spawn 结果中提取文本内容"""
        if isinstance(result, dict):
            for key in ['result', 'output', 'content', 'text', 'message']:
                if key in result:
                    val = result[key]
                    if isinstance(val, str):
                        return val
                    if isinstance(val, dict):
                        return self._extract_result(val)
            if 'error' in result:
                return f"错误: {result['error']}"
        
        if isinstance(result, str):
            return result
            
        return json.dumps(result, ensure_ascii=False, indent=2)
    
    def _parse_article(self, text: str, default_title: str) -> Dict[str, Any]:
        """解析生成的文章"""
        lines = text.strip().split('\n')
        
        title = default_title
        content = text
        tags = []
        
        # 尝试解析格式化输出
        if '---' in text:
            parts = text.split('---')
            if len(parts) >= 2:
                title = parts[0].strip() or default_title
                content = parts[1].strip()
                if len(parts) >= 3:
                    tag_text = parts[2].strip()
                    tags = [t.strip() for t in tag_text.replace('，', ',').split(',') if t.strip()]
        
        return {
            'title': title,
            'content': content,
            'tags': tags
        }


class DirectSpawnClient:
    """
    直接使用 OpenClaw sessions_spawn 的客户端
    
    这个版本在 OpenClaw 内部脚本中使用，直接调用 sessions_spawn 工具
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.default_model = self.config.get('model')
    
    def spawn(self, task: str, model: str = None, timeout_seconds: int = None) -> str:
        """
        直接生成 subagent 执行任务
        
        注意：这个方法需要在 OpenClaw 的 agent 环境中调用，
        使用 sessions_spawn 工具
        
        在外部 Python 脚本中，应使用 OpenClawClient
        """
        # 这里应该调用 sessions_spawn，但这个类
        # 只在 OpenClaw 内部使用时才有意义
        raise NotImplementedError(
            "DirectSpawnClient 只能在 OpenClaw agent 环境中使用。"
            "在外部脚本中请使用 OpenClawClient。"
        )


# 便捷函数
def create_client(config: Dict[str, Any] = None) -> OpenClawClient:
    """创建 OpenClaw 客户端实例"""
    return OpenClawClient(config)
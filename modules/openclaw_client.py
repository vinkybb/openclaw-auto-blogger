"""
OpenClaw 客户端：通过 Gateway HTTP POST /tools/invoke 调用 sessions_spawn。
文档: https://docs.openclaw.ai/gateway/tools-invoke-http-api
"""

import json
import subprocess
import os
from typing import Any, Dict, Optional

from .gateway_invoke import (
    find_child_session_key,
    gateway_base_url,
    gateway_bearer_token,
    invoke_tool,
    wait_for_spawn_transcript,
)


class OpenClawClient:
    """OpenClaw Gateway 客户端（支持 CLI + HTTP 双路径）"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        raw = (
            self.config.get("gateway_url")
            or self.config.get("base_url")
            or os.environ.get("OPENCLAW_GATEWAY_URL")
            or os.environ.get("OPENCLAW_URL")
        )
        self.base_url = gateway_base_url(raw)
        self.timeout = int(self.config.get("timeout", 300))
        self.default_model = self.config.get("model")
        self.gateway_token = self.config.get("gateway_token") or self.config.get("token")

    def spawn_agent(
        self,
        task: str,
        model: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        *,
        min_chars_early_exit: int = 400,
    ) -> Dict[str, Any]:
        """
        通过 tools/invoke 调用 sessions_spawn。
        首先尝试 CLI (openclaw agent --local)，失败则用 HTTP API。
        """
        # 优先 CLI
        result = self._try_cli_spawn(task, model, timeout_seconds)
        if result is not None:
            return result
        
        # 回退 HTTP
        return self._try_http_spawn(task, model, timeout_seconds, min_chars_early_exit)

    def _try_cli_spawn(self, task: str, model: str = None, timeout_seconds: int = None) -> Optional[Dict[str, Any]]:
        """尝试使用 openclaw CLI 执行任务"""
        try:
            cmd = ['openclaw', 'agent', '--local', '-m', task]
            if model:
                cmd.extend(['--agent', model])
            
            timeout_val = timeout_seconds or self.timeout
            cmd.extend(['--timeout', str(timeout_val)])
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_val + 10
            )
            
            if result.returncode == 0:
                return {
                    'success': True,
                    'output': result.stdout.strip(),
                    'result': result.stdout.strip()
                }
            return None  # CLI 失败，回退 HTTP
                
        except subprocess.TimeoutExpired:
            return None
        except Exception:
            return None
    
    def _try_http_spawn(self, task: str, model: str = None, timeout_seconds: int = None, min_chars_early_exit: int = 400) -> Dict[str, Any]:
        """使用 HTTP API 执行任务"""
        tok = gateway_bearer_token(self.gateway_token)
        if not tok:
            return {
                "success": False,
                "error": "缺少 Gateway 凭证：请设置 OPENCLAW_GATEWAY_TOKEN",
                "output": "",
            }

        wait = int(timeout_seconds or self.timeout)
        args: Dict[str, Any] = {"task": task}
        m = model or self.default_model
        if m:
            args["model"] = m
        args["runTimeoutSeconds"] = wait
        args["timeoutSeconds"] = wait

        out = invoke_tool(
            self.base_url,
            "sessions_spawn",
            args,
            bearer_token=tok,
            timeout=float(min(wait + 30, 120)),
        )
        if not out.get("success"):
            return out

        raw = out.get("raw") if isinstance(out.get("raw"), dict) else {}
        payload = raw.get("result") if isinstance(raw, dict) else None
        child_key = find_child_session_key(payload) or find_child_session_key(raw)
        if not child_key:
            return {
                "success": False,
                "output": "",
                "error": "sessions_spawn 未返回 childSessionKey",
                "status_code": out.get("status_code"),
                "raw": raw,
            }

        final_text, poll_err = wait_for_spawn_transcript(
            self.base_url,
            tok,
            child_key,
            float(wait),
            min_chars_early_exit=min_chars_early_exit,
        )
        if poll_err:
            return {
                "success": False,
                "output": "",
                "error": poll_err,
                "status_code": out.get("status_code"),
                "raw": raw,
            }

        return {
            "success": True,
            "output": final_text or "",
            "result": final_text or "",
            "status_code": out.get("status_code"),
            "raw": raw,
        }

    def summarize(self, content: str, style: str = "简洁") -> str:
        task = f"""请对以下内容进行{style}摘要，保留核心观点：

---
{content}
---

要求：
1. 保持客观
2. 突出最重要信息
3. 摘要长度 200-400 字

直接输出摘要，无前言后缀。"""

        result = self.spawn_agent(task, timeout_seconds=60, min_chars_early_exit=80)
        return self._extract_result(result)

    def expand(
        self,
        title: str,
        summary: str,
        source_url: Optional[str] = None,
        style: str = "深度分析",
        word_count: int = 1500,
    ) -> Dict[str, Any]:
        source_info = f"\n参考来源：{source_url}" if source_url else ""

        task = f"""基于摘要扩写博客文章：

标题：{title}

摘要：
{summary}
{source_info}

要求：
1. 风格：{style}
2. 字数：{word_count} 字左右
3. 结构：引言、正文、结论
4. 文末添加 3-5 标签

输出格式：
标题
---
正文
---
标签1, 标签2, 标签3"""

        result = self.spawn_agent(task, timeout_seconds=120)
        text = self._extract_result(result)
        return self._parse_article(text, title)

    def generate_tags(self, content: str, count: int = 5) -> list:
        task = f"""为文章生成 {count} 个标签：

{content[:1000]}...

只输出标签，逗号分隔。"""

        result = self.spawn_agent(task, timeout_seconds=30, min_chars_early_exit=8)
        text = self._extract_result(result)
        tags = [t.strip() for t in text.replace("，", ",").split(",") if t.strip()]
        return tags[:count]

    def translate(self, content: str, target_lang: str = "中文") -> str:
        task = f"""翻译成{target_lang}：

{content}

只输出翻译结果。"""

        result = self.spawn_agent(task, timeout_seconds=60, min_chars_early_exit=20)
        return self._extract_result(result)

    def _extract_result(self, result: Dict[str, Any]) -> str:
        if not isinstance(result, dict):
            return str(result)
        if result.get("success") is False:
            return f"错误: {result.get('error', 'unknown')}"
        for key in ("result", "output", "content", "text"):
            if key in result:
                val = result[key]
                if isinstance(val, str):
                    return val
        return json.dumps(result, ensure_ascii=False)

    def _parse_article(self, text: str, default_title: str) -> Dict[str, Any]:
        title = default_title
        content = text
        tags = []

        if "---" in text:
            parts = text.split("---")
            if len(parts) >= 2:
                title = parts[0].strip() or default_title
                content = parts[1].strip()
                if len(parts) >= 3:
                    tags = [t.strip() for t in parts[2].replace("，", ",").split(",") if t.strip()]

        return {"title": title, "content": content, "tags": tags}


def create_client(config: Optional[Dict[str, Any]] = None) -> OpenClawClient:
    """创建 OpenClaw 客户端"""
    return OpenClawClient(config)


def call_openclaw(messages: list, task_type: str = 'chat', model: str = None, 
                  timeout_seconds: int = 120) -> Dict[str, Any]:
    """
    便捷函数：直接调用 OpenClaw
    
    Args:
        messages: 消息列表 [{"role": "user", "content": "..."}]
        task_type: 任务类型
        model: 使用的模型
        timeout_seconds: 超时时间
    """
    client = OpenClawClient()
    
    if not messages:
        return {'success': False, 'error': '消息列表为空', 'output': ''}
    
    task_content = messages[-1].get('content', '') if isinstance(messages[-1], dict) else str(messages[-1])
    
    if len(messages) > 1:
        context = "\n".join([
            f"[{msg.get('role', 'user')}]: {msg.get('content', '')}" 
            for msg in messages[:-1] if isinstance(msg, dict)
        ])
        task = f"上下文:\n{context}\n\n请处理: {task_content}"
    else:
        task = task_content
    
    return client.spawn_agent(task, model=model, timeout_seconds=timeout_seconds)
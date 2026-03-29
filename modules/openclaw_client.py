"""
OpenClaw 客户端：通过 Gateway HTTP POST /tools/invoke 调用 sessions_spawn。
文档: https://docs.openclaw.ai/gateway/tools-invoke-http-api
注意: sessions_spawn 默认在 HTTP 层被拒绝，需在 gateway.tools 中显式 allow。
"""

import json
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
    """OpenClaw Gateway 客户端（Tools Invoke）"""

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
        self.gateway_token = self.config.get("gateway_token") or self.config.get(
            "token"
        )

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

        min_chars_early_exit: 子会话 transcript 中可提前返回的最小字符数；摘要/标签等可设小（如 40），
        长文扩写保持较大（默认 400）。轮询结束条件还依赖 OpenClaw 助手消息的 ``stopReason``（非 toolUse）。
        """
        tok = gateway_bearer_token(self.gateway_token)
        if not tok:
            return {
                "success": False,
                "error": "缺少 Gateway 凭证：请设置环境变量 OPENCLAW_GATEWAY_TOKEN（或配置 openclaw.gateway_token）。",
                "output": "",
            }

        wait = int(timeout_seconds or self.timeout)
        args: Dict[str, Any] = {"task": task}
        m = model or self.default_model
        if m:
            args["model"] = m
        # OpenClaw docs: runTimeoutSeconds caps the sub-agent run; some builds also accept timeoutSeconds.
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
                "error": "sessions_spawn 未返回 childSessionKey，无法拉取子会话正文（请升级 OpenClaw Gateway）。",
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

    def _extract_text(self, data: Any) -> str:
        if isinstance(data, str):
            return data
        if isinstance(data, dict):
            for key in ("result", "output", "content", "text", "message", "response"):
                if key in data:
                    return self._extract_text(data[key])
            if "data" in data:
                return self._extract_text(data["data"])
        return json.dumps(data, ensure_ascii=False)

    def summarize(self, content: str, style: str = "简洁") -> str:
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

        result = self.spawn_agent(
            task, timeout_seconds=60, min_chars_early_exit=80
        )
        return self._extract_result(result)

    def expand(
        self,
        title: str,
        summary: str,
        source_url: Optional[str] = None,
        style: str = "深度分析",
        word_count: int = 1500,
    ) -> Dict[str, Any]:
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
        task = f"""请为以下文章生成 {count} 个相关标签：

{content[:1000]}...

只输出标签，用逗号分隔。例如：技术, AI, 编程"""

        result = self.spawn_agent(
            task, timeout_seconds=30, min_chars_early_exit=8
        )
        text = self._extract_result(result)

        tags = [t.strip() for t in text.replace("，", ",").split(",") if t.strip()]
        return tags[:count]

    def translate(self, content: str, target_lang: str = "中文") -> str:
        task = f"""请将以下内容翻译成{target_lang}：

{content}

只输出翻译结果，不要添加任何说明。"""

        result = self.spawn_agent(
            task, timeout_seconds=60, min_chars_early_exit=20
        )
        return self._extract_result(result)

    def _extract_result(self, result: Dict[str, Any]) -> str:
        if not isinstance(result, dict):
            return str(result)
        if result.get("success") is False:
            err = result.get("error", "unknown error")
            return f"错误: {err}"
        for key in ("result", "output", "content", "text", "message"):
            if key in result:
                val = result[key]
                if isinstance(val, str):
                    return val
                if isinstance(val, dict):
                    return self._extract_result(val)
        return json.dumps(result, ensure_ascii=False, indent=2)

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
                    tag_text = parts[2].strip()
                    tags = [
                        t.strip()
                        for t in tag_text.replace("，", ",").split(",")
                        if t.strip()
                    ]

        return {
            "title": title,
            "content": content,
            "tags": tags,
        }


class DirectSpawnClient:
    """保留占位：仅在 OpenClaw agent 内通过工具调用时使用。"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.default_model = self.config.get("model")

    def spawn(
        self,
        task: str,
        model: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
    ) -> str:
        raise NotImplementedError(
            "DirectSpawnClient 仅在 OpenClaw agent 环境内有意义；外部请使用 OpenClawClient。"
        )


def create_client(config: Optional[Dict[str, Any]] = None) -> OpenClawClient:
    return OpenClawClient(config)

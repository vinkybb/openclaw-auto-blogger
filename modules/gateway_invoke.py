"""
Shared OpenClaw Gateway HTTP helper: POST /tools/invoke
See https://docs.openclaw.ai/gateway/tools-invoke-http-api
"""

import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, urljoin


def gateway_base_url(config_or_url: Optional[str] = None) -> str:
    """Normalize gateway base URL (no trailing slash)."""
    if config_or_url:
        base = str(config_or_url).rstrip("/")
    else:
        base = (
            os.environ.get("OPENCLAW_GATEWAY_URL")
            or os.environ.get("OPENCLAW_URL")
            or "http://127.0.0.1:18789"
        ).rstrip("/")
    return base


def gateway_bearer_token(config_token: Optional[str] = None) -> Optional[str]:
    return config_token or os.environ.get("OPENCLAW_GATEWAY_TOKEN") or os.environ.get(
        "OPENCLAW_GATEWAY_PASSWORD"
    )


def invoke_tool(
    base_url: str,
    tool: str,
    args: Dict[str, Any],
    *,
    bearer_token: Optional[str] = None,
    session_key: str = "main",
    timeout: float = 310,
) -> Dict[str, Any]:
    """
    POST /tools/invoke. Returns normalized dict:
    success, output (str), error (optional), status_code, raw (optional)
    """
    import requests

    url = urljoin(base_url.rstrip("/") + "/", "tools/invoke")
    headers = {"Content-Type": "application/json"}
    token = gateway_bearer_token(bearer_token)
    if token:
        headers["Authorization"] = f"Bearer {token}"

    body = {
        "tool": tool,
        "action": "json",
        "args": args,
        "sessionKey": session_key,
    }

    try:
        resp = requests.post(url, json=body, headers=headers, timeout=timeout)
    except requests.RequestException as e:
        return {
            "success": False,
            "output": "",
            "error": str(e),
            "status_code": None,
        }

    try:
        data = resp.json()
    except ValueError:
        return {
            "success": False,
            "output": "",
            "error": f"Invalid JSON from gateway (HTTP {resp.status_code})",
            "status_code": resp.status_code,
        }

    if resp.status_code == 401:
        return {
            "success": False,
            "output": "",
            "error": "Gateway returned 401: set OPENCLAW_GATEWAY_TOKEN (or password mode credential per docs).",
            "status_code": resp.status_code,
            "raw": data,
        }

    if resp.status_code == 404:
        err_msg = (
            data.get("error", {}).get("message")
            if isinstance(data.get("error"), dict)
            else data.get("error")
        )
        hint = (
            " Tool may be blocked over HTTP (e.g. sessions_spawn is denied by default); "
            "see gateway.tools allow/deny in OpenClaw docs."
        )
        return {
            "success": False,
            "output": "",
            "error": (err_msg or "Tool not available (HTTP 404)") + hint,
            "status_code": resp.status_code,
            "raw": data,
        }

    if data.get("ok") is True:
        result = data.get("result")
        text = _result_to_text(result)
        return {
            "success": True,
            "output": text,
            "result": text,
            "status_code": resp.status_code,
            "raw": data,
        }

    err = data.get("error")
    if isinstance(err, dict):
        msg = err.get("message", str(err))
    else:
        msg = str(err or f"Gateway error HTTP {resp.status_code}")
    return {
        "success": False,
        "output": "",
        "error": msg,
        "status_code": resp.status_code,
        "raw": data,
    }


def _result_to_text(result: Any) -> str:
    if result is None:
        return ""
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        for key in ("output", "text", "content", "message", "result"):
            if key in result and isinstance(result[key], str):
                return result[key]
        return json.dumps(result, ensure_ascii=False)
    return str(result)


def find_child_session_key(obj: Any) -> Optional[str]:
    """Recursively find childSessionKey in a sessions_spawn tool result (nested JSON)."""
    if isinstance(obj, dict):
        v = obj.get("childSessionKey")
        if isinstance(v, str) and v.strip():
            return v.strip()
        for x in obj.values():
            k = find_child_session_key(x)
            if k:
                return k
    elif isinstance(obj, list):
        for x in obj:
            k = find_child_session_key(x)
            if k:
                return k
    elif isinstance(obj, str):
        s = obj.strip()
        if s.startswith("{") and "childSessionKey" in s:
            try:
                return find_child_session_key(json.loads(s))
            except json.JSONDecodeError:
                pass
    return None


def unwrap_ok_result(invoke_response: Dict[str, Any]) -> Any:
    """Payload from POST /tools/invoke when success is True."""
    if not invoke_response.get("success"):
        return None
    raw = invoke_response.get("raw")
    if isinstance(raw, dict) and raw.get("ok") is True:
        return raw.get("result")
    return None


def messages_from_history_result(result: Any) -> List[Any]:
    """
    Transcript rows from OpenClaw history payloads.

    - ``POST /tools/invoke`` → ``sessions_history`` returns ``result`` with
      ``details.messages`` (see OpenClaw Session Tools).
    - ``GET /sessions/{sessionKey}/history`` JSON uses a top-level ``messages`` array.
    """
    if result is None:
        return []
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            return []
    if isinstance(result, list):
        return result if result and isinstance(result[0], dict) else []
    if not isinstance(result, dict):
        return []
    details = result.get("details")
    if isinstance(details, dict):
        m = details.get("messages")
        if isinstance(m, list) and m and isinstance(m[0], dict):
            return m
    m = result.get("messages")
    if isinstance(m, list) and m and isinstance(m[0], dict):
        return m
    return []


def _message_content_to_str(content: Any) -> Optional[str]:
    """OpenClaw transcript ``content``: string or list of ``{type, text}`` blocks (text only)."""
    if content is None:
        return None
    if isinstance(content, str):
        s = content.strip()
        return s or None
    if isinstance(content, list):
        parts: List[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                t = block.get("text")
                if isinstance(t, str):
                    parts.append(t)
        s = "".join(parts).strip()
        return s or None
    return None


def _message_role(msg: Dict[str, Any]) -> str:
    r = msg.get("role")
    return str(r).lower() if isinstance(r, str) else ""


def last_assistant_text_from_messages(messages: List[Any]) -> Optional[str]:
    """Last OpenClaw transcript row with ``role: assistant``."""
    for msg in reversed(messages):
        if not isinstance(msg, dict):
            continue
        if _message_role(msg) != "assistant":
            continue
        text = _message_content_to_str(msg.get("content"))
        if text:
            return text
    return None


def last_tool_or_assistant_text_from_messages(messages: List[Any]) -> Optional[str]:
    """Prefer ``assistant``; else last ``toolResult`` (e.g. subagent empty reply, see OpenClaw docs)."""
    t = last_assistant_text_from_messages(messages)
    if t:
        return t
    for msg in reversed(messages):
        if not isinstance(msg, dict):
            continue
        if _message_role(msg) != "toolresult":
            continue
        text = _message_content_to_str(msg.get("content"))
        if text:
            return text
    return None


def last_assistant_message(messages: List[Any]) -> Optional[Dict[str, Any]]:
    """Last transcript row with ``role: assistant`` (OpenClaw raw history order)."""
    for msg in reversed(messages):
        if isinstance(msg, dict) and _message_role(msg) == "assistant":
            return msg
    return None


def assistant_awaiting_tool_use(msg: Optional[Dict[str, Any]]) -> bool:
    """
    OpenClaw transcript marks assistant turns with ``stopReason`` (e.g. OpenAI-completions).
    ``toolUse`` means the model turn is not finished (tool call in flight); keep polling.
    See OpenClaw Session Tools (sessions_history raw transcript).
    """
    if not isinstance(msg, dict):
        return False
    if _message_role(msg) != "assistant":
        return False
    sr = msg.get("stopReason")
    if not isinstance(sr, str):
        return False
    return sr.lower() == "tooluse"


def _parse_http_json_body(resp: Any) -> Tuple[Optional[Any], Optional[str]]:
    """
    Parse JSON from a requests Response body.
    Handles BOM/whitespace; surfaces empty body, HTML, and SSE mistaken responses.
    """
    text = resp.text if getattr(resp, "text", None) is not None else ""
    status = getattr(resp, "status_code", None)
    ct = ""
    if hasattr(resp, "headers"):
        ct = (resp.headers.get("Content-Type") or "").lower()
    if "text/event-stream" in ct:
        return None, (
            f"GET history returned SSE (Content-Type text/event-stream), not JSON (HTTP {status}). "
            "Ensure the URL is the OpenClaw Gateway (not a stream endpoint)."
        )
    stripped = text.lstrip("\ufeff\u200b").strip()
    if not stripped:
        return None, (
            f"GET history empty body (HTTP {status}); check openclaw gateway_url points at the Gateway root."
        )
    if stripped[:2] == "<!" or stripped[:5].lower() == "<html":
        return None, (
            f"GET history returned HTML (HTTP {status}), not JSON — wrong gateway URL or a proxy in front."
        )
    try:
        return json.loads(stripped), None
    except json.JSONDecodeError as e:
        preview = stripped[:200].replace("\r\n", " ").replace("\n", " ")
        return None, (
            f"Invalid JSON from GET history (HTTP {status}) at pos {e.pos}: {e.msg!r}; preview: {preview!r}"
        )


def get_session_history_rest(
    base_url: str,
    bearer_token: str,
    session_key: str,
    *,
    limit: int = 80,
    include_tools: bool = False,
    timeout: float = 60.0,
) -> Dict[str, Any]:
    """
    GET /sessions/{sessionKey}/history (see OpenClaw session tools docs).
    Path must encode reserved characters in session keys (e.g. ':').
    """
    import requests

    enc = quote(session_key, safe="")
    path = f"sessions/{enc}/history"
    url = urljoin(base_url.rstrip("/") + "/", path)
    params: Dict[str, Any] = {"limit": limit}
    if include_tools:
        params["includeTools"] = 1
    headers: Dict[str, str] = {"Accept": "application/json"}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=timeout)
    except requests.RequestException as e:
        return {"success": False, "error": str(e), "payload": None, "status_code": None}

    data, parse_err = _parse_http_json_body(resp)
    if parse_err is not None:
        return {
            "success": False,
            "error": parse_err,
            "payload": None,
            "status_code": resp.status_code,
        }

    if resp.status_code == 404:
        return {
            "success": False,
            "error": "session not found (404)",
            "payload": data,
            "status_code": 404,
        }
    if resp.status_code != 200:
        return {
            "success": False,
            "error": f"GET history HTTP {resp.status_code}",
            "payload": data,
            "status_code": resp.status_code,
        }
    return {"success": True, "payload": data, "status_code": resp.status_code}


def _history_messages_union(
    base_url: str,
    bearer_token: str,
    session_key: str,
    *,
    include_tools: bool,
    deadline_abs: float,
) -> Tuple[List[Any], Optional[str]]:
    """Try GET /sessions/.../history first, then tools/invoke sessions_history."""
    last_err: Optional[str] = None
    timeout = min(60.0, max(8.0, deadline_abs - time.monotonic()))

    rest = get_session_history_rest(
        base_url,
        bearer_token,
        session_key,
        limit=120,
        include_tools=include_tools,
        timeout=timeout,
    )
    if rest.get("success"):
        payload = rest.get("payload")
        msgs = messages_from_history_result(payload)
        if msgs:
            return msgs, None
    else:
        last_err = rest.get("error", "GET history failed")

    inv = invoke_tool(
        base_url,
        "sessions_history",
        {
            "sessionKey": session_key,
            "limit": 120,
            "includeTools": include_tools,
        },
        bearer_token=bearer_token,
        timeout=timeout,
    )
    if inv.get("success"):
        payload = unwrap_ok_result(inv) or (
            inv.get("raw", {}).get("result") if isinstance(inv.get("raw"), dict) else None
        )
        msgs = messages_from_history_result(payload)
        if msgs:
            return msgs, None
        extra = "sessions_history 返回空或无法解析为消息列表"
        if payload is not None:
            extra += f"（payload: {type(payload).__name__}）"
        last_err = "；".join(x for x in (last_err, extra) if x)
    else:
        last_err = inv.get("error", last_err or "sessions_history invoke failed")

    return [], last_err


def wait_for_spawn_transcript(
    base_url: str,
    bearer_token: str,
    child_session_key: str,
    deadline_seconds: float,
    *,
    poll_interval: float = 2.0,
    min_chars_early_exit: int = 400,
) -> Tuple[Optional[str], Optional[str]]:
    """
    sessions_spawn returns immediately; poll transcript until assistant output is ready.
    Uses GET /sessions/{key}/history when possible, then POST tools/invoke sessions_history.
    Extra margin is added to deadline_seconds because spawn returns before the subagent runs.

    Completion uses OpenClaw transcript fields on the **last assistant** message:
    ``stopReason == "toolUse"`` means the turn is still in a tool round — keep polling.
    Otherwise, return once extracted text length is at least ``min_chars_early_exit``
    (lower for summaries/tags, higher for long-form).
    """
    margin = min(120.0, max(45.0, float(deadline_seconds) * 0.5))
    deadline = time.monotonic() + max(1.0, float(deadline_seconds) + margin)
    last_text: Optional[str] = None
    last_err: Optional[str] = None
    min_len = 8
    iteration = 0

    time.sleep(1.5)

    while time.monotonic() < deadline:
        iteration += 1
        include_tools = iteration % 2 == 0
        msgs, err = _history_messages_union(
            base_url,
            bearer_token,
            child_session_key,
            include_tools=include_tools,
            deadline_abs=deadline,
        )
        if err:
            last_err = err

        text = None
        if msgs:
            text = last_tool_or_assistant_text_from_messages(msgs)
            if not text:
                text = last_assistant_text_from_messages(msgs)

        if text:
            last_text = text

        last_asst = last_assistant_message(msgs) if msgs else None
        if assistant_awaiting_tool_use(last_asst):
            time.sleep(poll_interval)
            continue

        if text and len(text) >= min_len and len(text) >= min_chars_early_exit:
            return text, None

        time.sleep(poll_interval)

    if last_text:
        return last_text, None
    hint = f" 最后错误: {last_err}" if last_err else ""
    return None, (
        "子会话在超时内未完成或无可读助手回复（sessions_history 为空）。"
        "请确认 Gateway 版本与 `tools.sessions.visibility`，或增大 openclaw.timeout / 摘要超时。"
        + hint
    )

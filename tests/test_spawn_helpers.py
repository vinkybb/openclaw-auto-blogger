#!/usr/bin/env python3
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.gateway_invoke import (
    assistant_awaiting_tool_use,
    find_child_session_key,
    last_assistant_text_from_messages,
    last_tool_or_assistant_text_from_messages,
    messages_from_history_result,
    wait_for_spawn_transcript,
)


class TestSpawnHelpers(unittest.TestCase):
    def test_find_child_session_key_nested(self):
        nested = {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "status": "accepted",
                            "childSessionKey": "agent:main:subagent:test-id",
                            "runId": "r1",
                        }
                    ),
                }
            ],
            "details": {"childSessionKey": "agent:main:subagent:from-details"},
        }
        self.assertEqual(
            find_child_session_key(nested), "agent:main:subagent:test-id"
        )

    def test_messages_and_assistant(self):
        hist = {
            "messages": [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "final answer"},
            ]
        }
        msgs = messages_from_history_result(hist)
        self.assertEqual(len(msgs), 2)
        self.assertEqual(last_assistant_text_from_messages(msgs), "final answer")

    def test_openclaw_sessions_history_details_shape(self):
        """Real Gateway wraps transcript in result.details.messages (not top-level messages)."""
        raw = {
            "content": [{"type": "text", "text": '{"nested": "json"}'}],
            "details": {
                "sessionKey": "agent:main:subagent:x",
                "messages": [
                    {"role": "user", "content": [{"type": "text", "text": "task"}]},
                    {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "final from blocks"}],
                    },
                ],
            },
        }
        msgs = messages_from_history_result(raw)
        self.assertEqual(len(msgs), 2)
        self.assertEqual(
            last_tool_or_assistant_text_from_messages(msgs), "final from blocks"
        )

    def test_assistant_awaiting_tool_use(self):
        self.assertTrue(
            assistant_awaiting_tool_use(
                {"role": "assistant", "stopReason": "toolUse", "content": "x"}
            )
        )
        self.assertFalse(
            assistant_awaiting_tool_use(
                {"role": "assistant", "stopReason": "stop", "content": "x"}
            )
        )
        self.assertFalse(assistant_awaiting_tool_use(None))

    @patch("modules.gateway_invoke.get_session_history_rest")
    @patch("modules.gateway_invoke.invoke_tool")
    @patch("modules.gateway_invoke.time.sleep", lambda *_: None)
    def test_wait_for_spawn_transcript_respects_stop_reason(self, mock_invoke, mock_rest):
        mock_rest.return_value = {"success": False, "error": "skip GET for test"}

        def side_effect(url, tool, args, **kwargs):
            if tool != "sessions_history":
                raise AssertionError(tool)
            return {
                "success": True,
                "raw": {
                    "ok": True,
                    "result": {
                        "details": {
                            "messages": [
                                {"role": "user", "content": "task"},
                                {
                                    "role": "assistant",
                                    "content": "done " * 40,
                                    "stopReason": "stop",
                                },
                            ]
                        }
                    },
                },
            }

        mock_invoke.side_effect = side_effect
        text, err = wait_for_spawn_transcript(
            "http://127.0.0.1:18789",
            "tok",
            "agent:main:subagent:x",
            30.0,
            poll_interval=0.0,
            min_chars_early_exit=40,
        )
        self.assertIsNone(err)
        self.assertIn("done", text or "")

    @patch("modules.gateway_invoke.get_session_history_rest")
    @patch("modules.gateway_invoke.invoke_tool")
    @patch("modules.gateway_invoke.time.sleep", lambda *_: None)
    def test_wait_for_spawn_transcript_waits_while_tool_use(
        self, mock_invoke, mock_rest
    ):
        mock_rest.return_value = {"success": False, "error": "skip GET for test"}
        payloads = [
            {
                "details": {
                    "messages": [
                        {
                            "role": "assistant",
                            "content": "x" * 500,
                            "stopReason": "toolUse",
                        },
                    ]
                }
            },
            {
                "details": {
                    "messages": [
                        {
                            "role": "assistant",
                            "content": "x" * 500,
                            "stopReason": "toolUse",
                        },
                        {"role": "toolResult", "content": [{"type": "text", "text": "{}"}]},
                        {
                            "role": "assistant",
                            "content": "final " * 10,
                            "stopReason": "stop",
                        },
                    ]
                }
            },
        ]
        it = iter(payloads)

        def side_effect(url, tool, args, **kwargs):
            if tool != "sessions_history":
                raise AssertionError(tool)
            return {
                "success": True,
                "raw": {"ok": True, "result": next(it)},
            }

        mock_invoke.side_effect = side_effect
        text, err = wait_for_spawn_transcript(
            "http://127.0.0.1:18789",
            "tok",
            "agent:main:subagent:x",
            30.0,
            poll_interval=0.0,
            min_chars_early_exit=40,
        )
        self.assertIsNone(err)
        self.assertIn("final", text or "")


if __name__ == "__main__":
    unittest.main()

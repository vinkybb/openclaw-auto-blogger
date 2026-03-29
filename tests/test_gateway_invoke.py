#!/usr/bin/env python3
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.gateway_invoke import _parse_http_json_body, invoke_tool


class TestGatewayInvoke(unittest.TestCase):
    @patch("requests.post")
    def test_ok_response(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True, "result": {"text": "done"}}
        mock_post.return_value = mock_resp

        out = invoke_tool(
            "http://127.0.0.1:18789",
            "sessions_spawn",
            {"task": "hi"},
            bearer_token="tok",
            timeout=5,
        )
        self.assertTrue(out["success"])
        self.assertIn("done", out.get("output", ""))

    def test_parse_http_json_body_bom_and_whitespace(self):
        m = MagicMock()
        m.text = "\ufeff  {\"messages\": []}  \n"
        m.status_code = 200
        m.headers = {"Content-Type": "application/json"}
        data, err = _parse_http_json_body(m)
        self.assertIsNone(err)
        self.assertEqual(data, {"messages": []})

    def test_parse_http_json_body_empty(self):
        m = MagicMock()
        m.text = ""
        m.status_code = 200
        m.headers = {}
        data, err = _parse_http_json_body(m)
        self.assertIsNone(data)
        self.assertIn("empty", err.lower())


if __name__ == "__main__":
    unittest.main()

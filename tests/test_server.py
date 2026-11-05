import os
import sys
import unittest
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Add parent directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import (
    format_relative_time,
    get_brain_dir,
    handle_call_tool,
    TOOLS,
    __version__
)


class TestAgyTokenMonitor(unittest.TestCase):

    def test_version_present(self):
        self.assertRegex(__version__, r'^\d+\.\d+\.\d+')

    def test_format_relative_time_future(self):
        future_dt = datetime.now(timezone.utc) + timedelta(hours=3, minutes=15)
        iso_str = future_dt.isoformat().replace("+00:00", "Z")
        rel = format_relative_time(iso_str)
        self.assertTrue(rel.startswith("in "), f"Expected 'in ...', got {rel}")
        self.assertIn("3h", rel)

    def test_format_relative_time_days(self):
        future_dt = datetime.now(timezone.utc) + timedelta(days=4, hours=2)
        iso_str = future_dt.isoformat().replace("+00:00", "Z")
        rel = format_relative_time(iso_str)
        self.assertTrue(rel.startswith("in 4d "), f"Expected 'in 4d ...', got {rel}")

    def test_format_relative_time_past(self):
        past_dt = datetime.now(timezone.utc) - timedelta(minutes=45)
        iso_str = past_dt.isoformat().replace("+00:00", "Z")
        rel = format_relative_time(iso_str)
        self.assertIn("ago (refresh due)", rel)

    def test_format_relative_time_invalid(self):
        self.assertEqual(format_relative_time(""), "N/A")
        self.assertEqual(format_relative_time(None), "N/A")
        self.assertEqual(format_relative_time("invalid-date"), "invalid-date")

    def test_get_brain_dir(self):
        brain_path = get_brain_dir()
        self.assertIsInstance(brain_path, Path)
        self.assertTrue(str(brain_path).endswith("brain"))

    def test_tools_schema_integrity(self):
        self.assertEqual(len(TOOLS), 3)
        tool_names = {t["name"] for t in TOOLS}
        expected = {"get_account_quota", "get_session_token_usage", "get_token_awareness_summary"}
        self.assertEqual(tool_names, expected)

        for t in TOOLS:
            self.assertIn("description", t)
            self.assertIn("inputSchema", t)
            self.assertEqual(t["inputSchema"].get("type"), "object")

    def test_handle_call_tool_unknown(self):
        res = handle_call_tool("nonexistent_tool", {})
        self.assertIn("Unknown tool: nonexistent_tool", res)

    def test_handle_call_tool_json_arg_handling(self):
        # Should gracefully parse JSON string argument without throwing
        res = handle_call_tool("nonexistent_tool", "{}")
        self.assertIn("Unknown tool: nonexistent_tool", res)
        res_malformed = handle_call_tool("nonexistent_tool", "not-a-json")
        self.assertIn("Unknown tool: nonexistent_tool", res_malformed)


if __name__ == "__main__":
    unittest.main()

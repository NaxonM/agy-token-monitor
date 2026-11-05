#!/usr/bin/env python3
"""
agy-token-monitor: Antigravity Self-Aware Token & Quota Monitor (MCP Server + CLI)
Cross-platform, zero-dependency telemetry provider for Antigravity model quotas
(5h rolling & weekly limits) and conversation context token pressure.
"""

import os
import sys
import json
import re
import ssl
import time
import argparse
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Version
__version__ = "1.2.0"

# In-memory discovery cache (TTL 30s)
_CACHE = {
    "pid": None,
    "port": None,
    "csrf_token": None,
    "proto": "https",
    "timestamp": 0
}

def get_brain_dir():
    """Locate the Antigravity brain directory from environment or standard user home."""
    app_data = os.environ.get("ANTIGRAVITY_APP_DATA_DIR")
    if app_data:
        p = Path(app_data) / "brain"
        if p.exists():
            return p
    return Path.home() / ".gemini" / "antigravity" / "brain"


def discover_processes():
    """Discover running Antigravity language_server processes across Windows, macOS, and Linux."""
    platform_name = sys.platform
    procs = []

    if platform_name == "win32":
        ps_cmd = (
            'Get-CimInstance Win32_Process | '
            'Where-Object { $_.Name -like "*language_server*" } | '
            'Select-Object ProcessId, CommandLine | ConvertTo-Json'
        )
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                timeout=5
            )
            raw = json.loads(res.stdout)
            procs = [raw] if isinstance(raw, dict) else raw
        except Exception:
            pass

    elif platform_name in ("darwin", "linux"):
        try:
            res = subprocess.run(
                ["ps", "-eo", "pid,command"],
                capture_output=True,
                text=True,
                timeout=5
            )
            for line in res.stdout.splitlines():
                if "language_server" in line and "server.py" not in line and "grep" not in line:
                    parts = line.strip().split(None, 1)
                    if len(parts) == 2:
                        procs.append({
                            "ProcessId": int(parts[0]),
                            "CommandLine": parts[1]
                        })
        except Exception:
            pass

    return procs


def discover_ports_for_pid(pid):
    """Scan local loopback ports associated with a given PID."""
    platform_name = sys.platform
    ports = []

    if platform_name == "win32":
        try:
            res = subprocess.run(
                ["netstat", "-ano", "-p", "tcp"],
                capture_output=True,
                text=True,
                timeout=3
            )
            for line in res.stdout.splitlines():
                parts = line.strip().split()
                if len(parts) >= 5 and parts[0] == "TCP" and parts[-1] == str(pid):
                    local_addr = parts[1]
                    if any(h in local_addr for h in ["127.0.0.1", "0.0.0.0", "[::]", "[::1]"]):
                        try:
                            port = int(local_addr.rsplit(":", 1)[-1])
                            if port not in ports:
                                ports.append(port)
                        except ValueError:
                            pass
        except Exception:
            pass

    elif platform_name in ("darwin", "linux"):
        try:
            res = subprocess.run(
                ["lsof", "-Pan", "-p", str(pid), "-iTCP"],
                capture_output=True,
                text=True,
                timeout=3
            )
            for line in res.stdout.splitlines():
                if "LISTEN" in line or "ESTABLISHED" in line:
                    m = re.search(r':(\d+)(?:->|\s)', line)
                    if m:
                        port = int(m.group(1))
                        if port not in ports:
                            ports.append(port)
        except Exception:
            pass

        if not ports and platform_name == "linux":
            try:
                res = subprocess.run(
                    ["ss", "-tulpn"],
                    capture_output=True,
                    text=True,
                    timeout=3
                )
                for line in res.stdout.splitlines():
                    if f"pid={pid}" in line:
                        m = re.search(r':(\d+)\s', line)
                        if m:
                            port = int(m.group(1))
                            if port not in ports:
                                ports.append(port)
            except Exception:
                pass

    return ports


def test_endpoint(port, csrf_token, proto):
    """Quick check if the candidate port responds to GetUserStatus."""
    url = f"{proto}://127.0.0.1:{port}/exa.language_server_pb.LanguageServerService/GetUserStatus"
    req = urllib.request.Request(
        url,
        data=b"{}",
        headers={
            "Content-Type": "application/json",
            "X-Codeium-Csrf-Token": csrf_token,
            "Connect-Protocol-Version": "1"
        },
        method="POST"
    )
    ctx = ssl._create_unverified_context() if proto == "https" else None
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=1.2) as resp:
            return resp.status == 200
    except Exception:
        return False


def discover_language_server():
    """Locate active language server PID, dynamic CSRF token, and working loopback port."""
    now = time.time()
    if _CACHE["pid"] and (now - _CACHE["timestamp"] < 30):
        if test_endpoint(_CACHE["port"], _CACHE["csrf_token"], _CACHE["proto"]):
            return _CACHE["port"], _CACHE["csrf_token"], _CACHE["proto"]

    # 1. Direct environment discovery (fastest when invoked from within Antigravity runtime)
    env_addr = os.environ.get("ANTIGRAVITY_LS_ADDRESS")
    env_csrf = os.environ.get("ANTIGRAVITY_CSRF_TOKEN")
    if env_addr and env_csrf:
        host, _, port_str = env_addr.rpartition(":")
        if port_str.isdigit():
            port = int(port_str)
            for proto in ["http", "https"]:
                if test_endpoint(port, env_csrf, proto):
                    _CACHE["pid"] = os.getpid()
                    _CACHE["port"] = port
                    _CACHE["csrf_token"] = env_csrf
                    _CACHE["proto"] = proto
                    _CACHE["timestamp"] = time.time()
                    return port, env_csrf, proto

    procs = discover_processes()
    if not procs:
        raise RuntimeError("No active language_server process found. Ensure Antigravity IDE/App is running.")

    for p in procs:
        pid = p.get("ProcessId")
        cmdline = p.get("CommandLine") or ""
        csrf_match = re.search(r'--csrf_token\s+([a-f0-9\-]+)', cmdline)
        if not csrf_match:
            continue
        csrf_token = csrf_match.group(1)

        candidate_ports = discover_ports_for_pid(pid)
        expanded = []
        for c in candidate_ports:
            for delta in [0, 1, -1]:
                cand = c + delta
                if cand > 1024 and cand not in expanded:
                    expanded.append(cand)

        for port in expanded:
            for proto in ["https", "http"]:
                if test_endpoint(port, csrf_token, proto):
                    _CACHE["pid"] = pid
                    _CACHE["port"] = port
                    _CACHE["csrf_token"] = csrf_token
                    _CACHE["proto"] = proto
                    _CACHE["timestamp"] = time.time()
                    return port, csrf_token, proto

    raise RuntimeError("Failed to connect to LanguageServerService loopback endpoint.")


def rpc_call(method, payload=None):
    """Execute Connect RPC POST call to the local LanguageServerService."""
    if payload is None:
        payload = {}
    port, csrf_token, proto = discover_language_server()
    url = f"{proto}://127.0.0.1:{port}/exa.language_server_pb.LanguageServerService/{method}"
    data_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data_bytes,
        headers={
            "Content-Type": "application/json",
            "X-Codeium-Csrf-Token": csrf_token,
            "Connect-Protocol-Version": "1"
        },
        method="POST"
    )
    ctx = ssl._create_unverified_context() if proto == "https" else None
    with urllib.request.urlopen(req, context=ctx, timeout=3) as resp:
        return json.loads(resp.read().decode("utf-8"))


def format_relative_time(iso_str):
    """Convert ISO UTC timestamp into a human-readable countdown."""
    if not iso_str:
        return "N/A"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff = dt - now
        total_sec = diff.total_seconds()
        if total_sec > 0:
            days = int(total_sec // 86400)
            hours = int((total_sec % 86400) // 3600)
            mins = int((total_sec % 3600) // 60)
            if days > 0:
                return f"in {days}d {hours}h"
            return f"in {hours}h {mins}m"
        else:
            ago_sec = abs(total_sec)
            hours = int(ago_sec // 3600)
            mins = int((ago_sec % 3600) // 60)
            return f"{hours}h {mins}m ago (refresh due)"
    except Exception:
        return iso_str


def get_account_quota():
    """Fetch dual-window quota (5h rolling & weekly limits) and credit balances."""
    user_status_raw = rpc_call("GetUserStatus")
    quota_summary_raw = {}
    try:
        quota_summary_raw = rpc_call("RetrieveUserQuotaSummary")
    except Exception:
        pass

    user_status = user_status_raw.get("userStatus", {})
    name = user_status.get("name", "Unknown")
    email = user_status.get("email", "Unknown")
    plan_info = user_status.get("planStatus", {}).get("planInfo", {})
    tier_info = user_status.get("userTier", {})

    plan_name = plan_info.get("planName") or tier_info.get("name") or "Standard"
    avail_prompt = user_status.get("planStatus", {}).get("availablePromptCredits")
    avail_flow = user_status.get("planStatus", {}).get("availableFlowCredits")
    monthly_prompt = plan_info.get("monthlyPromptCredits")
    monthly_flow = plan_info.get("monthlyFlowCredits")

    quota_groups = []
    groups_data = quota_summary_raw.get("response", {}).get("groups", [])
    lowest_gemini = 1.0
    lowest_3p = 1.0

    for g in groups_data:
        g_name = g.get("displayName")
        g_desc = g.get("description")
        buckets = []
        for b in g.get("buckets", []):
            rem = b.get("remainingFraction", 0.0)
            window = b.get("window", "")
            reset_time = b.get("resetTime")
            disabled = b.get("disabled", False)
            pct = round(rem * 100, 1)

            if "gemini" in g_name.lower():
                if rem < lowest_gemini:
                    lowest_gemini = rem
            else:
                if rem < lowest_3p and not disabled:
                    lowest_3p = rem

            health = "HEALTHY"
            if disabled or rem == 0:
                health = "EXHAUSTED" if not disabled else "DISABLED"
            elif rem < 0.10:
                health = "CRITICAL"
            elif rem < 0.30:
                health = "WARNING"

            buckets.append({
                "window": window,
                "display_name": b.get("displayName"),
                "remaining_percentage": f"{pct}%",
                "remaining_fraction": rem,
                "reset_time_utc": reset_time,
                "reset_relative": format_relative_time(reset_time),
                "disabled": disabled,
                "health": health,
                "description": b.get("description")
            })

        quota_groups.append({
            "group_name": g_name,
            "description": g_desc,
            "buckets": buckets
        })

    verdict_parts = []
    if lowest_gemini < 0.10:
        verdict_parts.append(f"Gemini weekly pool is CRITICAL ({round(lowest_gemini*100, 1)}%)")
    elif lowest_gemini < 0.30:
        verdict_parts.append(f"Gemini weekly pool is WARNING ({round(lowest_gemini*100, 1)}%)")

    for g in quota_groups:
        if "claude" in g["group_name"].lower():
            for b in g["buckets"]:
                if b["window"] == "weekly" and b["remaining_fraction"] == 0:
                    verdict_parts.append("Claude/GPT weekly limit is EXHAUSTED (0% left)")

    verdict = " | ".join(verdict_parts) if verdict_parts else "HEALTHY: Adequate quota remaining across model pools."

    return {
        "account": {
            "name": name,
            "email": email,
            "tier": tier_info.get("name", plan_name),
            "plan_name": plan_name
        },
        "credits": {
            "available_prompt_credits": avail_prompt,
            "available_flow_credits": avail_flow,
            "monthly_prompt_credits": monthly_prompt,
            "monthly_flow_credits": monthly_flow
        },
        "verdict": verdict,
        "quota_groups": quota_groups
    }


def get_session_token_usage(conversation_id=None):
    """Estimate session tokens, turn counts, and context pressure from transcript.jsonl."""
    brain_dir = get_brain_dir()
    target_conv = conversation_id or os.environ.get("ANTIGRAVITY_CONVERSATION_ID")
    target_log = None

    if target_conv:
        cand = brain_dir / target_conv / ".system_generated" / "logs" / "transcript.jsonl"
        if cand.exists():
            target_log = cand

    if not target_log and brain_dir.exists():
        candidates = []
        for d in brain_dir.iterdir():
            if d.is_dir():
                log_file = d / ".system_generated" / "logs" / "transcript.jsonl"
                if log_file.exists():
                    candidates.append((d.stat().st_mtime, d.name, log_file))
        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            target_conv = candidates[0][1]
            target_log = candidates[0][2]

    if not target_log or not target_log.exists():
        return {
            "conversation_id": target_conv or "none",
            "status": "No active conversation transcript found",
            "estimated_tokens": 0
        }

    total_chars = 0
    step_count = 0
    breakdown = {
        "user_input_chars": 0,
        "planner_thinking_chars": 0,
        "planner_response_chars": 0,
        "tool_payload_chars": 0,
        "other_chars": 0
    }
    large_steps = []

    with open(target_log, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                step_count += 1
                entry_type = entry.get("type", "")
                content = entry.get("content", "") or ""
                thinking = entry.get("thinking", "") or ""
                tool_calls = json.dumps(entry.get("tool_calls", []))

                entry_len = len(content) + len(thinking) + len(tool_calls)
                total_chars += entry_len

                if entry_type == "USER_INPUT":
                    breakdown["user_input_chars"] += len(content)
                elif entry_type == "PLANNER_RESPONSE":
                    breakdown["planner_thinking_chars"] += len(thinking)
                    breakdown["planner_response_chars"] += len(content)
                    breakdown["tool_payload_chars"] += len(tool_calls)
                elif "TOOL" in entry_type:
                    breakdown["tool_payload_chars"] += len(content)
                else:
                    breakdown["other_chars"] += len(content)

                if entry_len > 4000:
                    large_steps.append({
                        "step_index": entry.get("step_index"),
                        "type": entry_type,
                        "est_tokens": entry_len // 4
                    })
            except Exception:
                pass

    est_tokens = total_chars // 4
    if est_tokens > 250000:
        pressure = "HIGH (Context bloated: recommend running /compact)"
    elif est_tokens > 100000:
        pressure = "MODERATE (Context expanding)"
    else:
        pressure = "HEALTHY (Plenty of context room)"

    return {
        "conversation_id": target_conv,
        "total_steps": step_count,
        "total_characters": total_chars,
        "estimated_session_tokens": est_tokens,
        "context_pressure": pressure,
        "token_breakdown": {
            "user_prompt_tokens": breakdown["user_input_chars"] // 4,
            "agent_thinking_tokens": breakdown["planner_thinking_chars"] // 4,
            "agent_response_tokens": breakdown["planner_response_chars"] // 4,
            "tool_io_tokens": breakdown["tool_payload_chars"] // 4,
            "system_other_tokens": breakdown["other_chars"] // 4
        },
        "large_steps_count": len(large_steps),
        "top_large_steps": large_steps[:5]
    }


def get_token_awareness_summary(conversation_id=None):
    """Generate Markdown executive pulse combining quota health and context consumption."""
    account_data = get_account_quota()
    session_data = get_session_token_usage(conversation_id)

    lines = [
        "### [Antigravity Dual-Window Token & Quota Self-Awareness]",
        f"- **Working Account:** `{account_data['account']['email']}` ({account_data['account']['tier']})",
        f"- **Credits Available:** Prompt: `{account_data['credits']['available_prompt_credits']}` | Flow: `{account_data['credits']['available_flow_credits']}`",
        f"- **Status Verdict:** **{account_data['verdict']}**",
        "",
        "#### Dual-Window Quota Pools (Rolling 5h & Weekly):",
    ]

    for g in account_data.get("quota_groups", []):
        lines.append(f"**{g['group_name']}:**")
        for b in g["buckets"]:
            dis = " [DISABLED]" if (b["disabled"] and b["health"] != "DISABLED") else ""
            lines.append(f"  - {b['display_name']} ({b['window']}): **{b['remaining_percentage']}** [{b['health']}]{dis} (resets {b['reset_relative']})")

    lines.extend([
        "",
        "#### Current Conversation Context Pressure:",
        f"- **Conversation ID:** `{session_data['conversation_id']}`",
        f"- **Steps Recorded:** {session_data['total_steps']}",
        f"- **Estimated Session Tokens:** ~{session_data['estimated_session_tokens']:,} tokens",
        f"- **Context Status:** {session_data['context_pressure']}",
        f"- **Breakdown:** User: ~{session_data['token_breakdown']['user_prompt_tokens']:,} | Agent: ~{session_data['token_breakdown']['agent_response_tokens']:,} | Tools: ~{session_data['token_breakdown']['tool_io_tokens']:,} | Thinking: ~{session_data['token_breakdown']['agent_thinking_tokens']:,}"
    ])

    return "\n".join(lines)


# MCP Tools Schema
TOOLS = [
    {
        "name": "get_account_quota",
        "description": "Fetch real-time dual-window quota (5h rolling & weekly limits) for Gemini and Claude/GPT pools directly from Antigravity language server.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "get_session_token_usage",
        "description": "Calculate token consumption and context bloat across the current conversation transcript.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Optional conversation ID to inspect. Defaults to the latest active conversation."
                }
            }
        }
    },
    {
        "name": "get_token_awareness_summary",
        "description": "Get a unified executive summary combining dual-window quota health (5h & weekly) and current conversation token consumption.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Optional conversation ID. Defaults to active conversation."
                }
            }
        }
    }
]


def handle_call_tool(name, args):
    if isinstance(args, str):
        try:
            args = json.loads(args) if args.strip() else {}
        except Exception:
            args = {}

    if name == "get_account_quota":
        return json.dumps(get_account_quota(), indent=2)

    elif name == "get_session_token_usage":
        cid = args.get("conversation_id")
        return json.dumps(get_session_token_usage(cid), indent=2)

    elif name == "get_token_awareness_summary":
        cid = args.get("conversation_id")
        return get_token_awareness_summary(cid)

    return f"Unknown tool: {name}"


def run_mcp_server():
    """Run standard Model Context Protocol (MCP) JSON-RPC stdio loop."""
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    sys.stdin.reconfigure(encoding="utf-8")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue

        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {})

        if method == "initialize":
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "agy-token-monitor", "version": __version__}
                }
            }
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()

        elif method == "notifications/initialized":
            pass

        elif method == "ping":
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {}}
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()

        elif method == "tools/list":
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": TOOLS}
            }
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()

        elif method == "tools/call":
            tool_name = params.get("name")
            tool_args = params.get("arguments", {})
            try:
                text_out = handle_call_tool(tool_name, tool_args)
                is_err = False
            except Exception as e:
                text_out = f"Error executing {tool_name}: {e}"
                is_err = True

            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": text_out}],
                    "isError": is_err
                }
            }
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()

        else:
            if req_id is not None:
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"}
                }
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()


def main():
    parser = argparse.ArgumentParser(
        description="agy-token-monitor: Antigravity Dual-Window Token & Quota Monitor (MCP Server + CLI)"
    )
    parser.add_argument(
        "-c", "--check", "--summary",
        action="store_true",
        help="Print real-time token awareness summary dashboard to stdout"
    )
    parser.add_argument(
        "-j", "--json",
        action="store_true",
        help="Print raw dual-window quota JSON"
    )
    parser.add_argument(
        "--session",
        action="store_true",
        help="Print active conversation session token breakdown JSON"
    )
    parser.add_argument(
        "--mcp",
        action="store_true",
        help="Force MCP stdio server mode"
    )
    parser.add_argument(
        "-v", "--version",
        action="version",
        version=f"agy-token-monitor {__version__}"
    )

    args = parser.parse_args()

    # CLI modes
    if args.check:
        try:
            print(get_token_awareness_summary())
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        return

    if args.json:
        try:
            print(json.dumps(get_account_quota(), indent=2))
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        return

    if args.session:
        try:
            print(json.dumps(get_session_token_usage(), indent=2))
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        return

    # If piped or explicitly requested, run MCP stdio server
    if args.mcp or not sys.stdin.isatty():
        run_mcp_server()
    else:
        # TTY without args: display live status + usage tip
        try:
            print(get_token_awareness_summary())
            print("\n[Tip] Run with --help for CLI flags, or configure in mcp_config.json to run as an MCP server.")
        except Exception as e:
            print(f"Error: {e}\nEnsure Antigravity IDE/App is running.", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()

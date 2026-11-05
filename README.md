# agy-token-monitor ⚡

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9+-brightgreen.svg)](pyproject.toml)
[![Dependencies](https://img.shields.io/badge/dependencies-0-success.svg)](server.py)
[![MCP](https://img.shields.io/badge/MCP-Compatible-purple.svg)](https://modelcontextprotocol.io)
[![Platform](https://img.shields.io/badge/platform-Windows%20|%20macOS%20|%20Linux-lightgrey.svg)](server.py)

**Self-aware dual-window quota telemetry and session token monitor for Google Antigravity.**  
Runs as both a native **Model Context Protocol (MCP) server** for AI coding assistants and a standalone **terminal CLI**.

---

## 💡 Why This Exists

Autonomous coding agents can rapidly burn thousands of tokens through iterative tool loops, subagent fan-outs, and large file diffs. When an agent hits an unannounced rate limit (`HTTP 429` / quota exhaustion):
1. Generations are terminated mid-stream, leaving half-written files and broken AST syntax.
2. The agent is blocked from even sending an error message or explaining what is left to do.
3. Repositories are left in uncommitted, dirty states.

`agy-token-monitor` gives Antigravity agents **continuous self-awareness** of their exact remaining headroom across both **5-hour rolling demand limits** and **weekly tier entitlement limits**, enabling graceful checkpointing before hitting hard boundaries.

---

## 🏗️ Architecture

```
┌────────────────────────────────────────────────────────┐
│             Antigravity Background Sidecar            │
│                 (language_server binary)               │
│                                                        │
│   • Dynamically allocated loopback port (127.0.0.1)    │
│   • Ephemeral --csrf_token in process arguments        │
└───────────────────────────┬────────────────────────────┘
                            │ Connect RPC (POST / JSON)
                            │ • RetrieveUserQuotaSummary
                            │ • GetUserStatus
                            ▼
┌────────────────────────────────────────────────────────┐
│                 agy-token-monitor                      │
│        (0 LLM tokens burned · ~15ms latency)           │
│                                                        │
│   • Auto-discovers PID, CSRF token, and active port    │
│   • Parses 5h rolling & weekly dual-window pools       │
│   • Scans session transcript.jsonl for token bloat     │
└───────────────────────────┬────────────────────────────┘
                            │
              ┌─────────────┴─────────────┐
              ▼                           ▼
    [MCP stdio JSON-RPC]          [Standalone CLI]
    (For AI Agent Turns)      (python server.py --check)
```

- **Zero LLM Token Cost:** Connects directly to the local language server's loopback RPC. Telemetry checks cost 0 API tokens.
- **Zero Pip Dependencies:** Built entirely with the Python standard library (`subprocess`, `urllib.request`, `ssl`, `json`, `re`).
- **Cross-Platform:** Works on Windows (PowerShell/netstat), macOS (ps/lsof), and Linux (ps/ss).

---

## 🚀 Quickstart

### 1. Clone & Standalone CLI Usage

Clone the repository:

```bash
git clone https://github.com/NaxonM/agy-token-monitor.git
cd agy-token-monitor
```

> 🤖 **One-Prompt Setup via Agent:** You can point your AI coding assistant directly at [`AGENTS.md`](AGENTS.md) (*"Configure agy-token-monitor according to AGENTS.md"*), and it will automatically register the MCP server in your `mcp_config.json` and install the companion skill for you.

Verify your active Antigravity quota straight from your terminal (zero pip dependencies required):

```bash
# Print formatted real-time dashboard
python server.py --check

# Print raw JSON telemetry
python server.py --json

# Print active conversation token consumption
python server.py --session
```

*(Optional)* Install into your Python environment for a direct `agy-token-monitor` CLI command:

```bash
pip install -e .

# Now callable from any directory
agy-token-monitor --check
```

#### Terminal Output Preview:
```markdown
### [Antigravity Dual-Window Token & Quota Self-Awareness]
- **Working Account:** `developer@gmail.com` (Google AI Pro)
- **Credits Available:** Prompt: `500` | Flow: `100`
- **Status Verdict:** Gemini weekly pool is HEALTHY (46.3%) | Claude/GPT weekly limit is EXHAUSTED (0% left)

#### Dual-Window Quota Pools (Rolling 5h & Weekly):
**Gemini Models:**
  - Weekly Limit Remaining (weekly): 46.3% [HEALTHY] (resets in 10h 55m)
  - Five Hour Limit Remaining (5h): 100% [HEALTHY] (resets in 4h 56m)
**Claude and GPT models:**
  - Weekly Limit Remaining (weekly): 0% [EXHAUSTED] (resets in 5d 1h)
  - Five Hour Limit Remaining (5h): 100% [DISABLED] (resets in 4h 56m)

#### Current Conversation Context Pressure:
- **Conversation ID:** `0205c6c6-8e40-473b-a238-bb9d711295a4`
- **Steps Recorded:** 17
- **Estimated Session Tokens:** ~4,733 tokens
- **Context Status:** HEALTHY (Plenty of context room)
- **Breakdown:** User: ~226 | Agent: ~363 | Tools: ~262 | Thinking: ~276
```

---

### 2. Antigravity MCP Server Setup

Add `agy-token-monitor` to your global Antigravity config (`~/.gemini/config/mcp_config.json`):

#### Option A: Direct Python Script
```json
{
  "mcpServers": {
    "agy-token-monitor": {
      "command": "python",
      "args": [
        "<path-to-repo>/server.py"
      ],
      "env": {
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
```

> **Note:** Replace `<path-to-repo>` with the absolute path to where you cloned this repository (e.g. `C:/path/to/agy-token-monitor/server.py` on Windows or `/home/username/agy-token-monitor/server.py` on macOS/Linux).

#### Option B: Installed CLI Command (`pip install -e .`)
```json
{
  "mcpServers": {
    "agy-token-monitor": {
      "command": "agy-token-monitor",
      "args": [
        "--mcp"
      ],
      "env": {
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
```

---

## 🛠️ MCP Tools Exposed

| Tool Name | Parameters | Description |
|---|---|---|
| `get_account_quota` | *None* | Returns real-time dual-window 5h and weekly quotas, per-model pool fractions, reset timers, and Google account plan credits. |
| `get_session_token_usage` | `conversation_id` *(optional)* | Reads active `transcript.jsonl` under `~/.gemini/antigravity/brain/<id>` and calculates total tokens burned, step breakdown (User, Thinking, Agent, Tool I/O), and context pressure. |
| `get_token_awareness_summary` | `conversation_id` *(optional)* | Returns a consolidated Markdown executive dashboard combining dual-window quotas and conversation token consumption. |

---

## 🧠 Companion Skill (`token-awareness`)

This repository bundles an agent skill in [`skill/token-awareness/SKILL.md`](skill/token-awareness/SKILL.md) that teaches Antigravity agents how to govern tokens autonomously:

1. **The 3% Landing Reserve:** The final 3% of quota is locked exclusively for clean file closing, syntax validation, and committing state. Generative tasks never burn quota down to 0%.
2. **Heartbeat & Runway Protocol:** During multi-file or multi-step tasks, the agent probes `get_account_quota()` every 3–5 tool steps. If remaining runway is insufficient for the next milestone, it halts cleanly, commits progress, and states the exact countdown until quota refresh.
3. **Quota-Scaled Ambiguity Gates:** When quota drops below 10%, guesswork is forbidden. The agent must halt for user clarification with bounded `[A]` vs `[B]` choices before executing high-burn operations.
4. **Swarm Governance:** Coordinators running weekly-quota models explicitly assign subagents to `Model: 'flash_lite'` or `'flash'` to spare the weekly entitlement tier.

### Installing the Skill

Copy the bundled skill into your global Antigravity skills directory:

```bash
# Windows PowerShell
Copy-Item -Recurse "skill/token-awareness" "$env:USERPROFILE\.gemini\config\skills\"

# macOS / Linux
cp -r skill/token-awareness ~/.gemini/config/skills/
```

---

## 🔍 How It Works Under The Hood

Antigravity executes a background binary (`language_server.exe` on Windows, `language_server_macos` on Apple Silicon, or `language_server` on Linux) with command-line arguments:

```bash
language_server.exe --csrf_token e4a891f8-... --https_server_port 0 ...
```

1. **Dynamic Port Discovery:** Because `--https_server_port 0` assigns an ephemeral OS port, `agy-token-monitor` inspects the local socket table (`netstat` on Windows, `lsof`/`ss` on Unix) matching the language server PID.
2. **Dynamic CSRF Authentication:** The script extracts the security token directly from the process command line.
3. **Connect RPC Telemetry:** Issues local requests to:
   - `POST /exa.language_server_pb.LanguageServerService/RetrieveUserQuotaSummary`
   - `POST /exa.language_server_pb.LanguageServerService/GetUserStatus`
4. **Zero-Latency In-Memory Caching:** Successful connection parameters (PID, port, token) are cached in-memory with a 30-second TTL.

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.

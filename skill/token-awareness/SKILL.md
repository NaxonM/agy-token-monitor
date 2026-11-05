---
name: token-awareness
description: "MANDATORY when monitoring model quota, checking remaining tokens, tracking session context burn, before launching heavy subagents, or when the user asks about token / quota status."
---

# Antigravity Token & Quota Self-Awareness

This skill provides the AGY agent with continuous, real-time awareness of its active working Google account, dual-window quota pools (5-hour rolling demand limiter & weekly tier entitlement), remaining capacity fractions, reset timestamps, and conversation context token pressure.

---

## 1. Core Architecture & Local Telemetry

Antigravity operates a background language server (`language_server.exe` / `language_server_windows_x64` / `language_server_macos`). The language server exposes a local Connect RPC / gRPC-over-HTTP service dynamically bound to a loopback port.

- **Primary Quota Endpoints:**
  - `POST /exa.language_server_pb.LanguageServerService/RetrieveUserQuotaSummary` (Provides exact dual-window 5h and weekly buckets for Gemini and Claude/GPT pools).
  - `POST /exa.language_server_pb.LanguageServerService/GetUserStatus` (Provides account tier, user identity, and prompt/flow credit balances).
- **Authentication:** Dynamic ephemeral `--csrf_token` extracted from the running language server process argument.
- **Data Source:** Zero external cloud requests needed — queried locally via the `agy-token-monitor` MCP server (`server.py`).

---

## 2. Available Tools (via `agy-token-monitor` MCP Server)

| Tool | Purpose |
|---|---|
| `get_account_quota` | Fetches dual-window 5h and weekly quota breakdowns, model pool health, account tier, and credit balances. |
| `get_session_token_usage` | Parses active session `transcript.jsonl` under `~/.gemini/antigravity/brain/<conv-id>`, calculating tokens burned, step count, and payload breakdown (User, Agent Response, Tools, Thinking). |
| `get_token_awareness_summary` | Generates a unified executive Markdown pulse combining dual-window quotas and conversation context consumption. |

---

## 3. Operational Protocols & Threshold Actions

### 3.1 Dual-Window Quota Thresholds
- **HEALTHY (> 30% weekly & 5h):** Full operational velocity. Zero quota narration.
- **WARNING (10% - 30%):** Enforce silent token conservation: compress thinking, prune tool output dumps, and read targeted line ranges only.
- **CRITICAL (< 10% weekly OR 5h): ZERO GUESSWORK.**
  1. **Atomic tasks (single file/command):** Execute immediately; do not stall on low-cost deliverables.
  2. **Multi-step / High-burn tasks:** Halt for clarification before action. State remaining %, reset timer, and offer bounded choices (`[A]` vs `[B]`).

### 3.2 Long-Task Runway Protocol (Graceful Park)
On tasks exceeding 3 tool steps or touching multiple files:
- **Landing Reserve (3% Floor):** Never burn quota below 3%. The final 3% is reserved exclusively for checkpointing and handoffs.
- **Heartbeat Cadence:** Probe `get_account_quota()` every 3–5 tool steps. Calculate burn velocity against remaining steps.
- **Graceful Park Trigger:** If runway is insufficient to complete the next atomic milestone without breaching the 3% floor:
  1. Complete and validate the current file (zero half-written code).
  2. Stage and commit (`git commit -m "checkpoint: <step>"`) or update a project status / checkpoint log.
  3. Halt execution cleanly. Output parked status: completed items, pending items, and exact reset countdown.

### 3.3 Swarm & Subagent Governance
- Never pass quota-anxiety warnings into subagent prompts.
- If running Claude or Flash High as coordinator, ALWAYS assign subagents to `Model: 'flash_lite'` or `'flash'` to spare the weekly tier.
- Quota < 25%: switch from parallel to sequential subagents. Quota < 10%: lock `invoke_subagent` entirely; execute in coordinator.
- If quota hits `< 10%` mid-swarm, immediately execute `manage_subagents(Action='kill_all')`, checkpoint partial findings, and halt to await user direction.

### 3.4 Context Pressure Thresholds
- **< 100k tokens:** Healthy context room.
- **100k - 250k tokens:** Moderate context. Prefer targeted file reads over dumping entire source trees.
- **> 250k tokens:** Context bloated. Recommend the user trigger `/compact` to summarize history and free window capacity.

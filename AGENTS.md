# Agent Automated Setup & Installation Playbook

> **Directive for the AI Agent:** You are executing the automated installation and configuration of `agy-token-monitor` for the user. Follow these instructions methodically from Step 1 through Step 5. Do not skip validation steps.

---

## Step 1: Environment & Path Resolution

1. Determine the host operating system (`Windows`, `macOS`, or `Linux`).
2. Resolve the absolute path of this cloned repository directory (`<REPO_ROOT>`).
3. Resolve the user's Antigravity configuration directory (`<CONFIG_DIR>`):
   - **Windows:** `$env:USERPROFILE\.gemini\config` (e.g. `C:\Users\<username>\.gemini\config`)
   - **macOS / Linux:** `~/.gemini/config` (expanded from `$HOME/.gemini/config`)
4. Detect the working Python binary:
   - Check `python --version` or `python3 --version` to determine the command name (`python` or `python3`). Ensure Python 3.9+ is available.

---

## Step 2: Register MCP Server in `mcp_config.json`

Target configuration file: `<CONFIG_DIR>/mcp_config.json`

1. Ensure the directory `<CONFIG_DIR>` exists (create if missing).
2. If `mcp_config.json` exists:
   - Read and parse its contents as JSON.
   - Preserve all existing server entries under `"mcpServers"`.
   - If `"mcpServers"` is missing, initialize it to `{}`.
3. If `mcp_config.json` does not exist:
   - Initialize a new object: `{"mcpServers": {}}`.
4. Add or update the `"agy-token-monitor"` configuration block:
   ```json
   "agy-token-monitor": {
     "command": "<PYTHON_BIN>",
     "args": [
       "<REPO_ROOT>/server.py"
     ],
     "env": {
       "PYTHONUNBUFFERED": "1"
     }
   }
   ```
   *(Normalize `<REPO_ROOT>/server.py` using forward slashes `/` for cross-platform JSON safety).*
5. Save the updated `mcp_config.json` with clean 2-space indentation.

---

## Step 3: Install Companion Skill (`token-awareness`)

Target directory: `<CONFIG_DIR>/skills/token-awareness`

1. Ensure `<CONFIG_DIR>/skills` exists.
2. Copy the entire bundled directory from `<REPO_ROOT>/skill/token-awareness` into `<CONFIG_DIR>/skills/token-awareness`.
3. Verify that `<CONFIG_DIR>/skills/token-awareness/SKILL.md` is in place and non-empty.

---

## Step 4: Verification & Diagnostic Check

Execute the following verification commands from the terminal:

1. **Automated Unit Tests:**
   ```bash
   <PYTHON_BIN> -m unittest discover -s <REPO_ROOT>/tests -p "test_*.py" -v
   ```
   *Expected output: 9 passed tests (`OK`).*

2. **Live Telemetry Probe:**
   ```bash
   <PYTHON_BIN> <REPO_ROOT>/server.py --check
   ```
   *Expected output: Displays the real-time quota dashboard (or version fallback if Antigravity is currently closed).*

---

## Step 5: Report to User

When all steps complete successfully, confirm to the user:
1. **MCP Server Registered:** `<CONFIG_DIR>/mcp_config.json` updated with `agy-token-monitor`.
2. **Skill Installed:** `token-awareness` installed into `<CONFIG_DIR>/skills/token-awareness/`.
3. **Next Action:** Advise the user to **reload the Antigravity window** (Command Palette -> `Developer: Reload Window` or restart the app) so the newly registered MCP server and skill are initialized.

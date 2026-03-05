# Project Instructions

## Commands
- Test: `uv run pytest tests/ -v`
- Build: `uv build`
- Install (dev): `uv tool install -e .`
- Refresh docs cache: `uv run bazzite-mcp-refresh`

## Workflow
- After completing work, always commit and push to the remote.
- Run tests before committing to verify nothing is broken.
- If something is wrong or missing, open a GitHub issue.

## Architecture
- Tools use action-dispatch pattern in `src/bazzite_mcp/tools/`.
- All shell commands go through `runner.py` — the only subprocess entry point.
- `guardrails.py` enforces allowlist/blocklist regex on every command before execution.
- Config loads: defaults → `~/.config/bazzite-mcp/config.toml` → env vars.
- Tests live in `tests/` and use `unittest.mock` to mock `run_command`.

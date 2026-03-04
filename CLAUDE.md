# Project Instructions

## Workflow
- After completing work, always commit and push to the remote.
- Run `uv run pytest tests/ -v` before committing to verify nothing is broken.

## Architecture
- Tools use action-dispatch pattern in `src/bazzite_mcp/tools/`.
- All shell commands go through `runner.py` with guardrails.
- Tests live in `tests/` and use `unittest.mock` to mock `run_command`.

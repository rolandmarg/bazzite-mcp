# Release Checklist

Use this checklist for every `bazzite-mcp` release.

## One-time setup

- [ ] Create the `pypi` environment in GitHub: repository `Settings` -> `Environments` -> `New environment` -> `pypi`.
- [ ] In PyPI project settings, enable Trusted Publishing for this repository/workflow:
  - Owner: `rolandmarg`
  - Repository: `bazzite-mcp`
  - Workflow file: `.github/workflows/release.yml`
  - Environment name: `pypi`
- [ ] Confirm package name on PyPI is `bazzite-mcp`.

## Per-release steps

1. Prepare version and notes

- [ ] Bump version in `pyproject.toml` and `src/bazzite_mcp/__init__.py`.
- [ ] Update `README.md` and/or changelog notes for user-facing changes.

2. Validate locally

- [ ] Run dependency sync: `uv sync --dev`
- [ ] Run tests: `uv run pytest tests/ -v`

3. Publish from git tag

- [ ] Commit release changes.
- [ ] Create annotated tag: `git tag -a vX.Y.Z -m "Release vX.Y.Z"`
- [ ] Push commit and tag: `git push && git push --tags`

4. Verify CI release pipeline

- [ ] Confirm `Release to PyPI` workflow succeeds in GitHub Actions.
- [ ] Confirm PyPI release exists: `https://pypi.org/project/bazzite-mcp/`
- [ ] Confirm GitHub Release is created from the tag.

5. Smoke test install

- [ ] In a clean environment: `uv tool install bazzite-mcp==X.Y.Z`
- [ ] Verify CLI entrypoint: `bazzite-mcp --version` (or `--help`)
- [ ] Verify import/version: `python -c "import bazzite_mcp; print(bazzite_mcp.__version__)"`
- [ ] Start from MCP client config and verify a basic tool call (e.g. `system_info`).
- [ ] Verify upgrade path: `uv tool upgrade bazzite-mcp`
- [ ] Verify uninstall path: `uv tool uninstall bazzite-mcp`

## Rollback options

- [ ] If a bad release was published, yank it on PyPI instead of deleting:
  - `pip index versions bazzite-mcp` (confirm versions)
  - `twine yank bazzite-mcp X.Y.Z -r pypi`
- [ ] Cut a patch release `vX.Y.(Z+1)` with the fix.

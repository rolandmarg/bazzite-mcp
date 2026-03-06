# Troubleshooting

## General System Issues

Use this sequence:

1. Gather `system_info(detail="basic")`.
2. Use `system_info(detail="full")` when hardware could be relevant.
3. Run `system_doctor()` for broad health checks.
4. Inspect service state with `manage_service(action="status", ...)` when a service is involved.
5. Search docs with `docs(action="search", query=...)`.
6. Use shell commands for targeted logs only when MCP does not expose the needed view.

Summarize findings as:

- observed state
- likely cause
- least invasive fix
- follow-up validation

## Service Diagnosis

For a failing systemd service:

1. Check `manage_service(action="status", name=...)`.
2. Confirm whether the service should be enabled.
3. Inspect recent logs with `journalctl` if the tool output is insufficient.
4. Search docs for service-specific Bazzite guidance.
5. Prefer restarting or re-enabling only after identifying the likely fault domain.

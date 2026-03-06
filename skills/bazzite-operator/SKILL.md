---
name: bazzite-operator
description: Operate and troubleshoot Bazzite OS systems with Bazzite-specific policy and workflow guidance. Use when Codex needs to choose the right Bazzite install tier, decide between host, container, and VM paths, diagnose services or desktop issues, set up development environments, or turn raw bazzite-mcp tool output into a platform-appropriate recommendation.
---

# Bazzite Operator

## Overview

Use this skill as the workflow and policy layer for Bazzite tasks. Treat `bazzite-mcp` as the capability layer for live system state, guarded mutations, documentation search, screenshots, and audit-aware changes.

Prefer MCP tools over ad hoc shell commands when an equivalent MCP tool exists. Use shell access mainly for targeted logs or for capabilities the MCP server does not expose yet.

## Tool Routing

Route tasks this way:

- Use `ujust` for Bazzite-provided setup and maintenance flows.
- Use `packages` for package discovery, installation, removal, and inventory across install methods.
- Use `docs` for Bazzite documentation search, changelogs, and policy lookup.
- Use `system_info`, `system_doctor`, and `storage_diagnostics` to inspect the host before recommending changes.
- Use `manage_service`, `manage_network`, and `manage_firewall` for service and network operations.
- Use `manage_distrobox`, `manage_quadlet`, and `manage_podman` for development environments and containerized services.
- Use `manage_vm` when the workload needs stronger isolation than a container should provide.
- Use `gaming` for Steam lookup, community reports, and game-specific settings changes.
- Use `screenshot`, `manage_windows`, `interact`, `set_text`, and `send_input` only when desktop automation is required.

Read these references when needed:

- `references/install-policy.md`
- `references/tool-routing.md`
- `references/troubleshooting.md`
- `references/dev-environments.md`
- `references/game-optimization.md`

## Operating Rules

Use this default order of operations:

1. Inspect current state first.
2. Choose the least invasive Bazzite-native path.
3. Explain the chosen path and why it fits Bazzite.
4. Mutate the system only after the path is justified.
5. Check audit history or rollback options after risky changes.

Keep these defaults:

- Prefer `ujust` before composing custom host commands.
- Prefer Flatpak for GUI apps and Homebrew for CLI/TUI tools.
- Prefer Distrobox for development environments and other package ecosystems that do not belong on the immutable host.
- Treat `rpm-ostree` as a last resort.
- Prefer VMs over containers for untrusted executables or high-isolation workflows.

## Response Style

Make the platform reasoning explicit. State which install tier, workflow, or execution model you chose and why alternatives were rejected.

When a tool returns raw results, translate them into a Bazzite-specific recommendation rather than repeating the output verbatim.

## Resources

Load only the specific reference file needed for the task. Keep this skill lean and avoid duplicating static policy text inside MCP code when the skill can own it instead.

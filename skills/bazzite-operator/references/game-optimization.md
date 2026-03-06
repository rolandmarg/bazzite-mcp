# Game Optimization

For game tuning:

1. Identify the game with `gaming(action="library", ...)`.
2. Collect host hardware with `system_info(detail="full")`.
3. Pull community data with `gaming(action="reports", ...)`.
4. Recommend Proton, Gamescope, MangoHud, and GameMode settings based on both hardware and report data.
5. Apply settings with `gaming(action="settings_set", ...)` only after explaining the tradeoffs.

Use this skill to justify the recommendation. Use MCP tools to inspect and apply it.

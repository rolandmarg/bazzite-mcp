# Dev Environments

For language runtimes, SDKs, and build chains:

1. Prefer `manage_distrobox(action="create", ...)`.
2. Install toolchains inside the container with `manage_distrobox(action="exec", ...)`.
3. Export GUI tools only when the user needs desktop integration.
4. Explain how to re-enter and maintain the environment.

Use the host only for tooling that must integrate directly with the immutable base system.

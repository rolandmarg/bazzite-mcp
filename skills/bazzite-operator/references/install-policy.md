# Install Policy

Use this file as the canonical policy reference for package and application decisions.

## Hierarchy

Apply the Bazzite install order in this sequence:

1. `ujust`
2. `flatpak`
3. `brew`
4. `distrobox` or `quadlet`
5. `AppImage`
6. `rpm-ostree`

## By Workload

### GUI apps

Prefer Flatpak. Check `ujust` first only when Bazzite ships a purpose-built setup path.

### CLI and TUI tools

Prefer Homebrew. Keep them out of the immutable base image unless host-level integration genuinely requires otherwise.

### Development environments

Prefer Distrobox. Put language runtimes, SDKs, and distro-native package managers there instead of on the host.

### Persistent services

Prefer Quadlet or another containerized service path before changing the host image.

### Drivers and kernel-adjacent components

Use `rpm-ostree` only when the requirement belongs on the host and no supported Bazzite-native option exists.

### Android support

Prefer the Bazzite or Waydroid path, typically through `ujust`.

## Decision Checklist

Answer these questions before changing the system:

1. Does Bazzite already provide a `ujust` path?
2. Is this a GUI app, CLI tool, dev environment, service, or host-level dependency?
3. Does the user need host integration, or is containerization acceptable?
4. Will an `rpm-ostree` change increase maintenance or rebase risk?
5. Is there a rollback path if the chosen method fails?

## Exceptions

- Use `rpm-ostree` only when the package must integrate with the host OS at the image level.
- Use a VM instead of a container when the workload is untrusted or isolation requirements are high.
- Use AppImage only from trusted sources and only after better-integrated options are unavailable.

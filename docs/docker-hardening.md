# Docker Sandbox Hardening Specification

## Overview

Every action (shell command, file write, API call, code patch) executed by SecureClawAgent runs inside an ephemeral Docker container. The container is destroyed immediately after the action completes. This document specifies the hardening measures applied to each container.

## Base Image

- **Source**: `python:3.11-alpine` (verified digest)
- **Custom image**: `secureclaw-sandbox:latest` built from `docker/Dockerfile.sandbox`
- **User**: Non-root (`uid=1000`, `gid=1000`)
- **Installed packages**: `bash`, `git`, `openssh-client`, `curl`, `jq` only

## Runtime Configuration

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `user` | `1000:1000` | Non-root execution; prevents privilege escalation |
| `network_mode` | `none` (default) | Zero-Trust: no external network access unless explicitly granted |
| `read_only` | `True` | Root filesystem is read-only; only workspace and /tmp are writable |
| `mem_limit` | `512m` | Prevents memory exhaustion attacks on host |
| `nano_cpus` | `1.0` (1 core) | Prevents CPU starvation of host |
| `tmpfs` | `/tmp:rw,noexec,nosuid,size=64m` | Writable temp space but no executable files |
| `security_opt` | `seccomp=<profile>` | Custom seccomp profile (see below) |
| `cap_drop` | `ALL` | Drop all Linux capabilities |
| `cap_add` | `CAP_SETUID`, `CAP_SETGID` | Only if uid switching is needed by tools |
| `privileged` | `False` | NEVER set to True |
| `docker_socket_mount` | `False` | NEVER mount `/var/run/docker.sock` |
| `pid_mode` | Container's own PID namespace | Prevents process visibility across containers |

## Seccomp Profile

Defined in `docker/seccomp.json`. The profile:

1. **Default action**: `SCMP_ACT_ERRNO` (deny with error)
2. **Blocked syscalls** (explicitly denied):
   - `ptrace` — prevents debugging/process injection
   - `mount`, `umount2` — prevents filesystem mount attacks
   - `unshare` — prevents namespace creation
   - `keyctl` — prevents kernel keyring abuse
   - `personality` — prevents architecture switching
   - `bpf` — prevents loading BPF programs
   - `kexec_load`, `kexec_file_load` — prevents kernel execution
   - `add_key`, `request_key` — prevents kernel key operations
   - `iopl`, `ioperm` — prevents direct I/O port access
   - `clock_settime`, `settimeofday` — prevents time manipulation
   - `reboot`, `shutdown` — prevents system shutdown
   - `init_module`, `finit_module`, `delete_module` — prevents kernel module loading

3. **Allowed syscalls**: Standard POSIX syscalls for file I/O, process management, networking (if permitted), memory management, and signal handling (detailed list in `seccomp.json`).

## Linux Capabilities

All capabilities dropped by default via Docker's `--cap-drop=ALL`. If sandbox tools require specific capabilities, they are added explicitly and documented:

| Capability | Required For | Risk Level |
|-----------|-------------|------------|
| `CAP_SETUID` | User switching inside container (e.g., `su`) | Low |
| `CAP_SETGID` | Group switching inside container | Low |
| `CAP_NET_BIND_SERVICE` | Binding to ports < 1024 (only when `network_mode=bridge` and domain allowlisted) | Medium |

## Volume Mounts

| Mount | Target | Mode | Purpose |
|-------|--------|------|---------|
| Workspace bind mount | `/workspace` | `rw` | User's working directory |
| tmpfs | `/tmp` | `rw,noexec,nosuid,size=64m` | Temporary files |

**NEVER mounted**:
- `/var/run/docker.sock`
- Host `/proc` or `/sys`
- Host `/etc` or any system config
- Host home directory

## Network Policy

Default: **No network access** (`network_mode=none`).

When network access is explicitly granted by the user:
1. User creates a per-domain allowlist for the task
2. Container uses `network_mode=bridge`
3. Egress filtering via iptables rules restricts outbound to allowlisted domains only
4. All network actions are logged to the action ledger
5. Network egress actions are classified as `RiskTier.NETWORK_EGRESS` and require explicit user confirmation

## Resource Limits

| Resource | Limit | Hard/Soft |
|----------|-------|-----------|
| Memory | 512 MB | Hard (OOM kill if exceeded) |
| CPU | 1.0 core | Soft (throttled via cgroups) |
| PIDs | 128 | Hard (prevents fork bombs) |
| Open files | 1024 | Soft |
| Core dump size | 0 | Hard (prevents memory dumps with secrets) |
| Container timeout | 300 seconds | Hard (SIGKILL after timeout) |

## Verification Checklist

Before considering a sandbox deployment secure, verify:

- [ ] Container starts with `--read-only` and cannot write to `/etc`, `/bin`, `/usr`
- [ ] Container cannot `ping` or `curl` to external hosts (without network allowlist)
- [ ] Container process runs as `uid=1000`, not `root` (uid=0)
- [ ] `docker inspect <container>` shows `"Privileged": false`
- [ ] `docker inspect <container>` shows no Docker socket mount
- [ ] Attempting `mount -t proc proc /proc` inside container fails
- [ ] Attempting `nsenter` or `unshare` inside container fails
- [ ] Attempting `ptrace` attach to another process fails
- [ ] Attempting to create a new user namespace fails
- [ ] Memory limit is enforced (container OOM-killed at 512 MB, not host OOM)

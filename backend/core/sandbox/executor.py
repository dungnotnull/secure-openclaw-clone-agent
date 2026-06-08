from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Optional

from backend.core.config import settings


class DockerExecutor:
    """Spawns an ephemeral Docker container for each action.

    - Hardened Alpine base image
    - No network by default
    - Seccomp profile applied
    - CPU / memory limits
    - Workspace bind-mounted read-write
    - Container is destroyed immediately after the call completes.
    """

    def __init__(self) -> None:
        self._client = None

    def _get_client(self):
        if self._client is None:
            import docker

            self._client = docker.from_env()
        return self._client

    def run(
        self,
        command: str | list[str],
        *,
        workspace_mount: Path | None = None,
        environment: dict[str, str] | None = None,
        network_allowed: bool = False,
        timeout: int | None = None,
    ) -> tuple[int, str, str]:
        client = self._get_client()
        timeout = timeout or settings.DOCKER_TIMEOUT_SECONDS

        if isinstance(command, list):
            command = " ".join(command)

        mounts = []
        if workspace_mount and workspace_mount.exists():
            mounts.append(
                {
                    "type": "bind",
                    "source": str(workspace_mount.resolve()),
                    "target": "/workspace",
                    "read_only": False,
                }
            )

        seccomp_args = {}
        if settings.SANDBOX_SECCOMP_PROFILE.exists():
            seccomp_args["security_opt"] = [
                f"seccomp={settings.SANDBOX_SECCOMP_PROFILE.resolve()}"
            ]

        container = client.containers.run(
            image=settings.DOCKER_BASE_IMAGE,
            command=f"/bin/sh -c '{command}'",
            detach=True,
            remove=False,
            network_mode="none" if not network_allowed else "bridge",
            mem_limit=settings.DOCKER_MEMORY_LIMIT,
            nano_cpus=int(settings.DOCKER_CPU_LIMIT * 1_000_000_000),
            mounts=mounts,
            environment=environment or {},
            user="1000:1000",
            read_only=True,
            tmpfs={"/tmp": "rw,noexec,nosuid,size=64m"},
            **seccomp_args,
        )

        container_id = container.id

        try:
            result = container.wait(timeout=timeout)
            exit_code = result.get("StatusCode", -1)
            stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
            stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")
        except Exception:
            exit_code = -1
            stdout = ""
            stderr = "Container timed out or failed"
        finally:
            try:
                container.remove(force=True)
            except Exception:
                pass

        return exit_code, stdout, stderr

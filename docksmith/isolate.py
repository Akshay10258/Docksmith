import subprocess
from pathlib import Path


def run_isolated(
    rootfs: Path,
    command: list[str],
    env: dict[str, str],
    workdir: str = "/",
    use_shell: bool = False,
) -> int:
    """
    Run command inside container (blocking).
    Used for:
    - build RUN steps
    - normal container run (if not tracking async)
    """

    cmd = _build_cmd(rootfs, command, env, workdir, use_shell)

    result = subprocess.run(cmd)
    return result.returncode


def run_isolated_async(
    rootfs: Path,
    command: list[str],
    env: dict[str, str],
    workdir: str = "/",
    use_shell: bool = False,
):
    """
    Run command inside container (non-blocking).
    Used for:
    - container lifecycle tracking (ps)
    """

    cmd = _build_cmd(rootfs, command, env, workdir, use_shell)

    return subprocess.Popen(cmd)


# ──────────────────────────────────────────────────────────────
# Shared helper
# ──────────────────────────────────────────────────────────────

def _build_cmd(
    rootfs: Path,
    command: list[str],
    env: dict[str, str],
    workdir: str,
    use_shell: bool,
):
    env_dict = dict(env)

    if "PATH" not in env_dict:
        env_dict["PATH"] = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

    workdir = workdir or "/"

    # ── command handling ───────────────────────────────────────
    if use_shell:
        # builder RUN (raw shell string)
        inner = command[0]
    else:
        # runtime execution (safe quoting)
        inner = " ".join(_q(a) for a in command)

    # ── environment export ─────────────────────────────────────
    env_exports = "\n".join(
        f'export {k}={_q(v)}' for k, v in env_dict.items()
    )

    shell_cmd = f"{env_exports}\ncd {_q(workdir)}\n{inner}"

    # ── FINAL COMMAND ──────────────────────────────────────────
    cmd = [
        "sudo",
        "unshare",
        "--pid",
        "--mount",
        "--uts",
        "--fork",
        "chroot",
        str(rootfs),
        "/bin/sh",
        "-c",
        shell_cmd,
    ]

    return cmd

def _q(s: str) -> str:
    """Safe shell quoting"""
    return "'" + s.replace("'", "'\\''") + "'"
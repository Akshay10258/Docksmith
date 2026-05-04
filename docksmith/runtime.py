import shutil
import sys
import tempfile
import json
import uuid
import os
from pathlib import Path

from .image import read_manifest
from .isolate import run_isolated_async   # <-- IMPORTANT (new)
from .layers import extract_layers_to
from .state import CONTAINERS_DIR


def run_container(
    name: str,
    tag: str,
    cmd_override: list[str],
    env_overrides: dict[str, str],
):
    try:
        manifest = read_manifest(name, tag)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        raise SystemExit(1)

    config = manifest["config"]

    # ── resolve command ──────────────────────────────────────────
    if cmd_override:
        command = cmd_override
    elif config.get("Cmd"):
        command = config["Cmd"]
    else:
        print(
            f"Error: no CMD defined in {name}:{tag} and no command given.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    # ── env setup ────────────────────────────────────────────────
    env = {}
    for pair in config.get("Env", []):
        k, _, v = pair.partition("=")
        env[k] = v
    env.update(env_overrides)

    workdir = config.get("WorkingDir") or "/"

    # ── create rootfs ────────────────────────────────────────────
    rootfs = Path(tempfile.mkdtemp(prefix="docksmith_rootfs_"))

    # ── container metadata ───────────────────────────────────────
    container_id = str(uuid.uuid4())[:12]
    container_file = CONTAINERS_DIR / f"{container_id}.json"

    try:
        # assemble filesystem
        layer_digests = [l["digest"] for l in manifest["layers"]]
        extract_layers_to(layer_digests, rootfs)

        if workdir and workdir != "/":
            (rootfs / workdir.lstrip("/")).mkdir(parents=True, exist_ok=True)

        # ── run container (async) ────────────────────────────────
        proc = run_isolated_async(
            rootfs=rootfs,
            command=command,
            env=env,
            workdir=workdir,
        )

        # ── save metadata ────────────────────────────────────────
        meta = {
            "id": container_id,
            "image": f"{name}:{tag}",
            "pid": proc.pid,
            "status": "running",
        }

        container_file.write_text(json.dumps(meta, indent=2))

        print(f"Container started: {container_id} (PID {proc.pid})")

        # ── wait for process ─────────────────────────────────────
        exit_code = proc.wait()

        # ── update status ────────────────────────────────────────
        meta["status"] = "exited"
        container_file.write_text(json.dumps(meta, indent=2))

        print(f"\nContainer exited with code {exit_code}")

        if exit_code != 0:
            raise SystemExit(exit_code)

    finally:
        # cleanup filesystem
        shutil.rmtree(rootfs, ignore_errors=True)
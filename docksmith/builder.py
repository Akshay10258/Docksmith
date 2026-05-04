import hashlib
import json
import os
import shutil
import tempfile
import time
from pathlib import Path

from .cache import compute_cache_key, load_cache, save_cache
from .image import new_manifest, read_manifest, write_manifest
from .isolate import run_isolated
from .layers import (
    collect_copy_files,
    extract_layers_to,
    make_layer_tar,
    store_layer,
)
from .parser import (
    parse_cmd_args,
    parse_copy_args,
    parse_docksmithfile,
    parse_env_args,
)
from .state import layer_path


def build(context_dir: str, tag: str, no_cache: bool = False):
    context = Path(context_dir).resolve()
    if ":" in tag:
        name, image_tag = tag.split(":", 1)
    else:
        name, image_tag = tag, "latest"

    instructions = parse_docksmithfile(context)
    total = len(instructions)
    cache_index = load_cache()

    # ── build state ──────────────────────────────────────────────
    manifest = None
    base_manifest = None
    workdir = ""
    env_vars = {}          # accumulated ENV values
    cache_busted = False   # once True, all steps are misses
    step = 0
    build_start = time.time()

    for instr in instructions:
        step += 1

        # ── FROM ─────────────────────────────────────────────────
        if instr.op == "FROM":
            img_ref = instr.args.strip()
            if ":" in img_ref:
                base_name, base_tag = img_ref.split(":", 1)
            else:
                base_name, base_tag = img_ref, "latest"

            print(f"Step {step}/{total} : FROM {img_ref}")

            try:
                base_manifest = read_manifest(base_name, base_tag)
            except FileNotFoundError as e:
                print(f"Error: {e}")
                raise SystemExit(1)

            manifest = new_manifest(name, image_tag, base_manifest)
            workdir = manifest["config"].get("WorkingDir", "")
            # parse existing ENV from base
            for pair in manifest["config"].get("Env", []):
                k, _, v = pair.partition("=")
                env_vars[k] = v
            continue

        # ── WORKDIR ──────────────────────────────────────────────
        if instr.op == "WORKDIR":
            workdir = instr.args.strip()
            manifest["config"]["WorkingDir"] = workdir
            print(f"Step {step}/{total} : WORKDIR {workdir}")
            continue

        # ── ENV ──────────────────────────────────────────────────
        if instr.op == "ENV":
            k, v = parse_env_args(instr.args)
            env_vars[k] = v
            # store in manifest config as KEY=VALUE list
            env_list = [f"{ek}={ev}" for ek, ev in sorted(env_vars.items())]
            manifest["config"]["Env"] = env_list
            print(f"Step {step}/{total} : ENV {k}={v}")
            continue

        # ── CMD ──────────────────────────────────────────────────
        if instr.op == "CMD":
            cmd_list = parse_cmd_args(instr.args)
            manifest["config"]["Cmd"] = cmd_list
            print(f"Step {step}/{total} : CMD {instr.args}")
            continue

        # ── COPY ─────────────────────────────────────────────────
        if instr.op == "COPY":
            src_pat, dest = parse_copy_args(instr.args)
            t_start = time.time()

            # compute file hashes for cache key
            import glob as globmod
            pattern = str(context / src_pat)
            matched = sorted(globmod.glob(pattern, recursive=True))
            file_hashes = ""
            for fp in matched:
                p = Path(fp)
                if p.is_file():
                    h = hashlib.sha256(p.read_bytes()).hexdigest()
                    file_hashes += str(p.relative_to(context)) + ":" + h + "\n"

            # previous layer digest for cache key
            prev_digest = _prev_layer_digest(manifest, base_manifest)
            cache_key = compute_cache_key(
                prev_digest=prev_digest,
                instruction=f"COPY {instr.args}",
                workdir=workdir,
                env_vars=env_vars,
                extra=file_hashes,
            )

            if not cache_busted and not no_cache and cache_key in cache_index:
                stored_digest = cache_index[cache_key]
                if layer_path(stored_digest).exists():
                    lp = layer_path(stored_digest)
                    elapsed = time.time() - t_start
                    print(
                        f"Step {step}/{total} : COPY {instr.args} "
                        f"[CACHE HIT] {elapsed:.2f}s"
                    )
                    manifest["layers"].append({
                        "digest": stored_digest,
                        "size": lp.stat().st_size,
                        "createdBy": f"COPY {instr.args}",
                    })
                    continue
                else:
                    cache_busted = True

            cache_busted = True
            files = collect_copy_files(context, src_pat, dest)
            tar_bytes = make_layer_tar(files)
            digest, size = store_layer(tar_bytes)

            if not no_cache:
                cache_index[cache_key] = digest
                save_cache(cache_index)

            elapsed = time.time() - t_start
            print(
                f"Step {step}/{total} : COPY {instr.args} "
                f"[CACHE MISS] {elapsed:.2f}s"
            )
            manifest["layers"].append({
                "digest": digest,
                "size": size,
                "createdBy": f"COPY {instr.args}",
            })
            continue

        # ── RUN ──────────────────────────────────────────────────
        if instr.op == "RUN":
            t_start = time.time()
            prev_digest = _prev_layer_digest(manifest, base_manifest)
            cache_key = compute_cache_key(
                prev_digest=prev_digest,
                instruction=f"RUN {instr.args}",
                workdir=workdir,
                env_vars=env_vars,
                extra="",
            )

            if not cache_busted and not no_cache and cache_key in cache_index:
                stored_digest = cache_index[cache_key]
                if layer_path(stored_digest).exists():
                    lp = layer_path(stored_digest)
                    elapsed = time.time() - t_start
                    print(
                        f"Step {step}/{total} : RUN {instr.args} "
                        f"[CACHE HIT] {elapsed:.2f}s"
                    )
                    manifest["layers"].append({
                        "digest": stored_digest,
                        "size": lp.stat().st_size,
                        "createdBy": f"RUN {instr.args}",
                    })
                    continue
                else:
                    cache_busted = True

            cache_busted = True

            # assemble rootfs from all layers so far
            rootfs = Path(tempfile.mkdtemp(prefix="docksmith_run_"))
            try:
                all_digests = [l["digest"] for l in manifest["layers"]]
                extract_layers_to(all_digests, rootfs)

                # create workdir inside rootfs if needed
                if workdir:
                    (rootfs / workdir.lstrip("/")).mkdir(parents=True, exist_ok=True)

                # snapshot before
                before = _snapshot(rootfs)

                # run command in isolation
                run_env = dict(env_vars)
                exit_code = run_isolated(
                    rootfs=rootfs,
                    command=[instr.args],
                    env=run_env,
                    workdir=workdir or "/",
                    use_shell=True,
                )

                if exit_code != 0:
                    print(f"Error: RUN command failed with exit code {exit_code}")
                    raise SystemExit(exit_code)

                # snapshot after — delta only
                after = _snapshot(rootfs)
                delta = _compute_delta(rootfs, before, after)

                tar_bytes = make_layer_tar(delta)
                digest, size = store_layer(tar_bytes)

                if not no_cache:
                    cache_index[cache_key] = digest
                    save_cache(cache_index)

                elapsed = time.time() - t_start
                print(
                    f"Step {step}/{total} : RUN {instr.args} "
                    f"[CACHE MISS] {elapsed:.2f}s"
                )
                manifest["layers"].append({
                    "digest": digest,
                    "size": size,
                    "createdBy": f"RUN {instr.args}",
                })
            finally:
                shutil.rmtree(rootfs, ignore_errors=True)

    # ── write final manifest ──────────────────────────────────────
    total_time = time.time() - build_start
    manifest_path = write_manifest(manifest)
    short_digest = manifest["digest"].removeprefix("sha256:")[:12]
    print(f"\nSuccessfully built sha256:{short_digest} {name}:{image_tag} ({total_time:.2f}s)")


# ── helpers ──────────────────────────────────────────────────────

def _prev_layer_digest(manifest: dict, base_manifest: dict) -> str:
    """
    The cache key needs the digest of the last COPY/RUN layer.
    If no layers produced yet, use the base image manifest digest.
    """
    own_layers = [
        l for l in manifest["layers"]
        if l["createdBy"].startswith("COPY") or l["createdBy"].startswith("RUN")
    ]
    if own_layers:
        return own_layers[-1]["digest"]
    return base_manifest["digest"]


def _snapshot(rootfs: Path) -> dict[str, float]:
    """
    Walk rootfs and return {relative_path: mtime} for all files.
    Used to detect which files changed after a RUN command.
    """
    snap = {}
    for p in rootfs.rglob("*"):
        if p.is_file():
            try:
                rel = str(p.relative_to(rootfs))
                snap[rel] = p.stat().st_mtime
            except Exception:
                pass
    return snap


def _compute_delta(
    rootfs: Path,
    before: dict[str, float],
    after: dict[str, float],
) -> dict[str, bytes]:
    """
    Return {arc_path: bytes} for files that are new or modified
    since the before snapshot — this becomes the RUN delta layer.
    """
    delta = {}
    for rel, mtime in after.items():
        if rel not in before or before[rel] != mtime:
            abs_path = rootfs / rel
            try:
                delta[rel] = abs_path.read_bytes()
            except Exception:
                pass
    return delta

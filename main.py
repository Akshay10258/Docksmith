#!/usr/bin/env python3
"""
docksmith — a simplified Docker-like build and runtime system.
"""
import sys
import argparse
from docksmith.state import init_state

def cmd_build(args):
    from docksmith.builder import build
    build(
        context_dir=args.context,
        tag=args.tag,
        no_cache=args.no_cache,
    )

def cmd_images(args):
    from docksmith.image import all_images
    imgs = all_images()
    if not imgs:
        print("No images found.")
        return
    fmt = "{:<20} {:<10} {:<14} {}"
    print(fmt.format("NAME", "TAG", "ID", "CREATED"))
    for m in imgs:
        short_id = m["digest"].removeprefix("sha256:")[:12]
        print(fmt.format(m["name"], m["tag"], short_id, m["created"]))

def cmd_ps(args):
    from docksmith.state import CONTAINERS_DIR
    import json, os

    fmt = "{:<15} {:<20} {:<10}"
    print(fmt.format("CONTAINER ID", "IMAGE", "STATUS"))

    for f in CONTAINERS_DIR.glob("*.json"):
        data = json.loads(f.read_text())

        pid = data.get("pid")
        status = "running"

        try:
            os.kill(pid, 0)
        except Exception:
            status = "exited"

        print(fmt.format(data["id"], data["image"], status))

def cmd_rmi(args):
    from docksmith.image import read_manifest
    from docksmith.state import image_manifest_path, layer_path
    import os
    name, tag = _parse_tag(args.name_tag)
    try:
        manifest = read_manifest(name, tag)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    removed_layers = 0
    for layer in manifest["layers"]:
        lp = layer_path(layer["digest"])
        if lp.exists():
            lp.unlink()
            removed_layers += 1

    image_manifest_path(name, tag).unlink()
    print(f"Removed {name}:{tag} ({removed_layers} layer files deleted)")

def cmd_run(args):
    from docksmith.runtime import run_container
    name, tag = _parse_tag(args.name_tag)
    overrides = {}
    for pair in (args.env or []):
        k, _, v = pair.partition("=")
        overrides[k] = v
    run_container(
        name, tag,
        cmd_override=args.cmd or [],
        env_overrides=overrides,
    )


def cmd_import(args):
    """Import a base image tarball into the local store."""
    from docksmith.importer import import_image
    import_image(args.tarball, args.name, args.tag)

def _parse_tag(name_tag: str) -> tuple[str, str]:
    if ":" in name_tag:
        name, tag = name_tag.split(":", 1)
    else:
        name, tag = name_tag, "latest"
    return name, tag

def main():
    init_state()

    parser = argparse.ArgumentParser(prog="docksmith")
    sub = parser.add_subparsers(dest="command", required=True)

    # build
    p_build = sub.add_parser("build", help="Build an image from a Docksmithfile")
    p_build.add_argument("-t", dest="tag", required=True, metavar="name:tag")
    p_build.add_argument("context", metavar="context_dir")
    p_build.add_argument("--no-cache", action="store_true")
    p_build.set_defaults(func=cmd_build)

    # images
    p_images = sub.add_parser("images", help="List local images")
    p_images.set_defaults(func=cmd_images)

    # ps
    p_ps = sub.add_parser("ps", help="List containers")
    p_ps.set_defaults(func=cmd_ps)

    # rmi
    p_rmi = sub.add_parser("rmi", help="Remove an image")
    p_rmi.add_argument("name_tag", metavar="name:tag")
    p_rmi.set_defaults(func=cmd_rmi)

    # run
    p_run = sub.add_parser("run", help="Run a container")
    p_run.add_argument("name_tag", metavar="name:tag")
    p_run.add_argument("cmd", nargs=argparse.REMAINDER, help="Override CMD")
    p_run.add_argument("-e", dest="env", action="append", metavar="KEY=VALUE")
    p_run.set_defaults(func=cmd_run)

    # import (setup helper)
    p_import = sub.add_parser("import", help="Import a base image tarball")
    p_import.add_argument("tarball")
    p_import.add_argument("name")
    p_import.add_argument("tag")
    p_import.set_defaults(func=cmd_import)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()

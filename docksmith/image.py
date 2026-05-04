
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from .state import image_manifest_path, layer_path

def compute_manifest_digest(manifest: dict) -> str:
    """
    Spec rule: set digest="" in a copy, serialize, SHA-256 that,
    then write the real manifest with digest set to the result.
    """
    tmp = {**manifest, "digest": ""}
    canonical = json.dumps(tmp, separators=(",", ":"), sort_keys=True)
    h = hashlib.sha256(canonical.encode()).hexdigest()
    return f"sha256:{h}"

def write_manifest(manifest: dict) -> Path:
    name, tag = manifest["name"], manifest["tag"]
    manifest["digest"] = compute_manifest_digest(manifest)
    path = image_manifest_path(name, tag)
    path.write_text(json.dumps(manifest, indent=2))
    return path

def read_manifest(name: str, tag: str) -> dict:
    path = image_manifest_path(name, tag)
    if not path.exists():
        raise FileNotFoundError(
            f"Image {name}:{tag} not found in local store. "
            "Import it first with: docksmith import <tarball> <name> <tag>"
        )
    return json.loads(path.read_text())

def new_manifest(name: str, tag: str, base: dict | None) -> dict:
    """Start a fresh manifest, inheriting base layers if FROM was used."""
    now = datetime.now(timezone.utc).isoformat()
    layers = list(base["layers"]) if base else []
    config = dict(base["config"]) if base else {"Env": [], "Cmd": [], "WorkingDir": ""}
    return {
        "name": name,
        "tag": tag,
        "digest": "",
        "created": now,
        "config": config,
        "layers": layers,
    }

def all_images() -> list[dict]:
    from .state import all_image_manifests
    result = []
    for p in all_image_manifests():
        try:
            result.append(json.loads(p.read_text()))
        except Exception:
            pass
    return result

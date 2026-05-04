import os
from pathlib import Path

DOCKSMITH_HOME = Path.home() / ".docksmith"
CONTAINERS_DIR = DOCKSMITH_HOME / "containers"
IMAGES_DIR     = DOCKSMITH_HOME / "images"
LAYERS_DIR     = DOCKSMITH_HOME / "layers"
CACHE_DIR      = DOCKSMITH_HOME / "cache"
CACHE_INDEX    = CACHE_DIR / "index.json"

def init_state():
    """Create ~/.docksmith/ layout if it doesn't exist yet."""
    for d in (IMAGES_DIR, LAYERS_DIR, CACHE_DIR, CONTAINERS_DIR):
        d.mkdir(parents=True, exist_ok=True)
    if not CACHE_INDEX.exists():
        CACHE_INDEX.write_text("{}")

def image_manifest_path(name: str, tag: str) -> Path:
    return IMAGES_DIR / f"{name}_{tag}.json"

def layer_path(digest: str) -> Path:
    # digest is "sha256:<hex>", filename is just the hex
    hex_part = digest.removeprefix("sha256:")
    return LAYERS_DIR / hex_part

def all_image_manifests() -> list[Path]:
    return sorted(IMAGES_DIR.glob("*.json"))



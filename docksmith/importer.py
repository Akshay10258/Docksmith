import hashlib
import json
import tarfile
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from .state import LAYERS_DIR, layer_path
from .image import write_manifest

def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"

def import_image(tarball_path: str, name: str, tag: str):
    src = Path(tarball_path).resolve()
    if not src.exists():
        raise FileNotFoundError(f"Tarball not found: {src}")

    print(f"Importing {src.name} as {name}:{tag} ...")

    digest = sha256_of_file(src)
    dest = layer_path(digest)

    if dest.exists():
        print(f"  Layer already present: {digest[:19]}...")
    else:
        shutil.copy2(src, dest)
        print(f"  Layer stored: {digest[:19]}...")

    size = dest.stat().st_size

    manifest = {
        "name": name,
        "tag": tag,
        "digest": "",
        "created": datetime.now(timezone.utc).isoformat(),
        "config": {
            "Env": [],
            "Cmd": [],
            "WorkingDir": "",
        },
        "layers": [
            {
                "digest": digest,
                "size": size,
                "createdBy": f"imported from {src.name}",
            }
        ],
    }

    path = write_manifest(manifest)
    print(f"  Manifest written: {path}")
    print(f"Successfully imported {name}:{tag}")

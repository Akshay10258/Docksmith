import hashlib
import io
import os
import tarfile
from pathlib import Path
from .state import layer_path, LAYERS_DIR

def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()

def make_layer_tar(files: dict[str, bytes]) -> bytes:
    """
    Build a deterministic tar archive from a dict of {archive_path: file_bytes}.
    Rules for reproducibility:
      - entries added in lexicographically sorted order
      - all timestamps zeroed
      - no uid/gid/uname/gname info
    """
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for arc_path in sorted(files.keys()):
            data = files[arc_path]
            info = tarfile.TarInfo(name=arc_path)
            info.size  = len(data)
            info.mtime = 0      # zero timestamp — required for reproducibility
            info.mode  = 0o755 if arc_path.endswith("/") else 0o644
            info.uid   = 0
            info.gid   = 0
            info.uname = ""
            info.gname = ""
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()

def store_layer(tar_bytes: bytes) -> tuple[str, int]:
    """
    Write tar bytes to layers/ named by their SHA-256 digest.
    Returns (digest, size).
    """
    digest = sha256_bytes(tar_bytes)
    dest = layer_path(digest)
    if not dest.exists():
        dest.write_bytes(tar_bytes)
    return digest, len(tar_bytes)

def collect_copy_files(
    context_dir: Path,
    src_pattern: str,
    dest: str,
) -> dict[str, bytes]:
    """
    Collect files matching src_pattern from context_dir.
    Returns dict of {archive_path: bytes} ready for make_layer_tar.
    Supports * and ** globs.
    """
    import fnmatch
    import glob as globmod

    # resolve glob relative to context
    pattern = str(context_dir / src_pattern)
    matched = sorted(globmod.glob(pattern, recursive=True))

    if not matched:
        raise FileNotFoundError(
            f"COPY: no files matched '{src_pattern}' in {context_dir}"
        )

    files = {}
    for abs_path in matched:
        p = Path(abs_path)
        if p.is_dir():
            continue
        rel = p.relative_to(context_dir)
        # build archive path under dest
        if dest.endswith("/"):
            arc = dest.lstrip("/") + str(rel)
        else:
            arc = dest.lstrip("/")
        files[arc] = p.read_bytes()

    return files

def extract_layers_to(layer_digests: list[str], target_dir: Path):
    """
    Extract all layers in order into target_dir.
    Later layers overwrite earlier ones (union filesystem behaviour).
    """
    for digest in layer_digests:
        lp = layer_path(digest)
        if not lp.exists():
            raise FileNotFoundError(
                f"Layer {digest[:19]}... missing from ~/.docksmith/layers/. "
                "The image may be broken."
            )
        with tarfile.open(lp, "r:*") as tar:
            # Safe extract — avoid path traversal
            for member in tar.getmembers():
                member_path = target_dir / member.name
                # ensure it stays within target_dir
                try:
                    member_path.resolve().relative_to(target_dir.resolve())
                except ValueError:
                    continue  # skip unsafe paths
            tar.extractall(path=target_dir, filter="tar")

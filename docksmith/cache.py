
import hashlib
import json
from .state import CACHE_INDEX


def compute_cache_key(
    prev_digest: str,
    instruction: str,
    workdir: str,
    env_vars: dict,
    extra: str = "",
) -> str:
    env_str = "\n".join(
        f"{k}={v}" for k, v in sorted(env_vars.items())
    )
    raw = "\n".join([prev_digest, instruction, workdir, env_str, extra])
    return hashlib.sha256(raw.encode()).hexdigest()


def load_cache() -> dict:
    if CACHE_INDEX.exists():
        try:
            return json.loads(CACHE_INDEX.read_text())
        except Exception:
            return {}
    return {}


def save_cache(index: dict):
    CACHE_INDEX.write_text(json.dumps(index, indent=2))


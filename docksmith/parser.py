
import json
from pathlib import Path
from dataclasses import dataclass

@dataclass
class Instruction:
    line_no: int
    op: str        # FROM, COPY, RUN, WORKDIR, ENV, CMD
    args: str      # everything after the op

VALID_OPS = {"FROM", "COPY", "RUN", "WORKDIR", "ENV", "CMD"}

def parse_docksmithfile(context_dir: Path) -> list[Instruction]:
    path = context_dir / "Docksmithfile"
    if not path.exists():
        raise FileNotFoundError(f"No Docksmithfile found in {context_dir}")

    instructions = []
    for line_no, raw in enumerate(path.read_text().splitlines(), start=1):
        line = raw.strip()
        # skip blank lines and comments
        if not line or line.startswith("#"):
            continue

        parts = line.split(None, 1)
        op = parts[0].upper()
        args = parts[1] if len(parts) > 1 else ""

        if op not in VALID_OPS:
            raise SyntaxError(
                f"Docksmithfile line {line_no}: "
                f"unrecognised instruction '{op}'"
            )

        instructions.append(Instruction(line_no=line_no, op=op, args=args))

    if not instructions or instructions[0].op != "FROM":
        raise SyntaxError("Docksmithfile must start with FROM")

    return instructions

def parse_cmd_args(args: str) -> list[str]:
    """Parse CMD ["exec","arg"] JSON array form."""
    try:
        result = json.loads(args)
        if not isinstance(result, list):
            raise ValueError
        return result
    except Exception:
        raise ValueError(
            f"CMD requires JSON array form e.g. CMD [\"python\", \"main.py\"], got: {args}"
        )

def parse_env_args(args: str) -> tuple[str, str]:
    """Parse ENV KEY=VALUE."""
    if "=" not in args:
        raise ValueError(f"ENV requires KEY=VALUE form, got: {args}")
    key, _, value = args.partition("=")
    return key.strip(), value.strip()

def parse_copy_args(args: str) -> tuple[str, str]:
    """Parse COPY <src> <dest>."""
    parts = args.split()
    if len(parts) < 2:
        raise ValueError(f"COPY requires <src> <dest>, got: {args}")
    src = " ".join(parts[:-1])
    dest = parts[-1]
    return src, dest

"""Scan files that git tracks (or has staged) for secrets. Exit 1 if anything is found.

    uv run python scripts/check_secrets.py              # tracked + staged files (make secrets / check)
    uv run python scripts/check_secrets.py --staged     # staged content only (the pre-commit hook)
    uv run python scripts/check_secrets.py --install-hook

Two kinds of checks:
1. Exact values: every non-empty value of a secret-looking variable in .env (whatever its format)
   is searched for literally. This catches key formats that no pattern knows about.
2. Patterns: Google API keys, Kaggle tokens, private keys, and long token-like strings assigned
   to a name containing key / token / secret.
Findings are printed with the secret masked.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 5 * 1024 * 1024
SECRET_NAME = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD)", re.I)

PATTERNS = [
    ("Google API key", re.compile(r"AIza[0-9A-Za-z_\-]{35}")),
    ("Kaggle API token", re.compile(r"KGAT_[0-9a-fA-F]{32}")),
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----")),
    ("kaggle.json key", re.compile(r'"key"\s*:\s*"[0-9a-f]{32}"')),
    ("token assignment", re.compile(
        r"""(?i)\b[\w-]*(?:api[_-]?key|token|secret)[\w-]*\b\s*[:=]\s*["']?([A-Za-z0-9_\-\.]{32,})""")),
]

ALLOW_FILES = {".env.example"}
PLACEHOLDER = re.compile(r"(?i)^(x+|your[_-].*|changeme|fake.*|dummy.*|test.*|example.*|\.\.\.)$")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=True).stdout


def env_secret_values() -> list[tuple[str, str]]:
    env = ROOT / ".env"
    out = []
    if env.exists():
        for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            name, _, value = line.partition("=")
            value = value.strip().strip('"').strip("'")
            if SECRET_NAME.search(name) and len(value) >= 12:
                out.append((name.strip(), value))
    return out


def mask(s: str) -> str:
    return s[:4] + "…" + s[-2:] if len(s) > 8 else "***"


def files_to_scan(staged_only: bool) -> dict[str, bytes]:
    contents: dict[str, bytes] = {}
    staged = [p for p in git("diff", "--cached", "--name-only", "--diff-filter=ACMR").splitlines() if p]
    for path in staged:
        blob = subprocess.run(["git", "show", f":{path}"], cwd=ROOT, capture_output=True).stdout
        contents[path] = blob
    if not staged_only:
        for path in git("ls-files").splitlines():
            if path in contents:
                continue
            p = ROOT / path
            if p.is_file() and p.stat().st_size <= MAX_BYTES:
                contents[path] = p.read_bytes()
    return contents


def scan(contents: dict[str, bytes]) -> list[str]:
    findings = []
    values = env_secret_values()
    for path, blob in contents.items():
        if len(blob) > MAX_BYTES or b"\0" in blob[:8000]:
            continue  # binary or huge
        if Path(path).name == ".env":
            findings.append(f"{path}: the .env file itself is tracked or staged")
            continue
        text = blob.decode("utf-8", errors="replace")
        for name, value in values:
            if value in text:
                findings.append(f"{path}: contains the value of {name} from .env ({mask(value)})")
        if Path(path).name in ALLOW_FILES:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for label, pattern in PATTERNS:
                for m in pattern.finditer(line):
                    secret = m.group(1) if m.groups() else m.group(0)
                    if PLACEHOLDER.match(secret) or "check_secrets" in path:
                        continue
                    # long hex hashes are cache keys / sha256, not secrets
                    if label == "token assignment" and re.fullmatch(r"[0-9a-f]{64}", secret):
                        continue
                    findings.append(f"{path}:{lineno}: possible {label} ({mask(secret)})")
    return findings


HOOK = """#!/bin/sh
# installed by `make setup`: block commits that contain secrets
exec uv run python scripts/check_secrets.py --staged
"""


def install_hook() -> int:
    hooks = ROOT / ".git" / "hooks"
    if not hooks.parent.exists():
        print("not a git repository; run `git init` first", file=sys.stderr)
        return 1
    hooks.mkdir(exist_ok=True)
    hook = hooks / "pre-commit"
    hook.write_bytes(HOOK.encode("utf-8"))
    try:
        hook.chmod(0o755)
    except OSError:
        pass
    print(f"installed {hook.relative_to(ROOT).as_posix()}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--staged", action="store_true", help="scan staged content only (pre-commit)")
    ap.add_argument("--install-hook", action="store_true", help="install .git/hooks/pre-commit")
    args = ap.parse_args(argv)
    if args.install_hook:
        return install_hook()
    findings = scan(files_to_scan(args.staged))
    if findings:
        print("Secrets check FAILED:", file=sys.stderr)
        for f in findings:
            print(f"  {f}", file=sys.stderr)
        return 1
    print(f"secrets check: ok ({'staged files' if args.staged else 'tracked + staged files'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

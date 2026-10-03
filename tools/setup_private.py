"""Install checkout-local publication controls from an external policy."""
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-root", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    args = parser.parse_args()
    research = args.research_root.resolve()
    source = args.policy.resolve(strict=True)
    if research.is_relative_to(ROOT) or ROOT.is_relative_to(research):
        raise ValueError("Research and repository roots must be separate trees")
    if source.is_relative_to(ROOT):
        raise ValueError("Policy source must be outside the repository")
    policy = json.loads(source.read_text(encoding="utf-8-sig"))
    patterns = policy.get("patterns")
    if not isinstance(patterns, list) or not patterns or any(not isinstance(p, str) or not p for p in patterns):
        raise ValueError("Policy requires a nonempty list of regex patterns")
    for pattern in patterns:
        re.compile(pattern, re.IGNORECASE)
    if Path(git("rev-parse", "--show-toplevel")).resolve() != ROOT:
        raise ValueError("Initialize this project as its own repository first")
    policy_path = Path(git("rev-parse", "--git-path", "private-content-policy.json"))
    hooks = Path(git("rev-parse", "--git-path", "hooks"))
    if not policy_path.is_absolute():
        policy_path = ROOT / policy_path
    if not hooks.is_absolute():
        hooks = ROOT / hooks
    if policy_path.parent.resolve() == ROOT or hooks.resolve() == ROOT:
        raise ValueError("Private policy and hook must remain in Git-private storage")
    hook_path = hooks / "pre-commit"
    hook = "#!/bin/sh\n# Check actual indexed content using the local private policy.\nexec " + " ".join(
        shlex.quote(item) for item in [Path(sys.executable).as_posix(), (ROOT / "tools/check_repo.py").as_posix(), "--staged"]
    ) + "\n"
    if hook_path.exists() and hook_path.read_text(encoding="utf-8") != hook:
        raise ValueError("Existing pre-commit hook differs; preserve it and integrate the guard explicitly")
    research.mkdir(parents=True, exist_ok=True)
    for name in ("scripts", "reports", "projects", "logs", "captures", "fixtures", "settings", "cache", "tmp", "plans"):
        (research / name).mkdir(exist_ok=True)
    if os.name == "nt":
        import ctypes
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.GetFileAttributesW.argtypes = [ctypes.c_wchar_p]
        api.GetFileAttributesW.restype = ctypes.c_uint32
        api.SetFileAttributesW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32]
        api.SetFileAttributesW.restype = ctypes.c_int
        attributes = api.GetFileAttributesW(str(research))
        if attributes == 0xFFFFFFFF or not api.SetFileAttributesW(str(research), attributes | 2):
            raise OSError("Could not mark the private research folder hidden")
    policy_path.write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")
    hooks.mkdir(parents=True, exist_ok=True)
    hook_path.write_text(hook, encoding="utf-8", newline="\n")
    hook_path.chmod(hook_path.stat().st_mode | 0o111)
    git("config", "--local", "inkbolt.researchRoot", str(research))
    git("config", "--local", "inkbolt.requireContentPolicy", "true")
    print("Private research root, required content policy and commit hook configured.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, re.error, subprocess.CalledProcessError) as error:
        raise SystemExit(f"Private setup failed: {error}") from error

"""Check candidate or indexed material; this is not proof of copyright provenance."""
import argparse
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_SUFFIXES = {".rs", ".py", ".md", ".json", ".toml", ".lock"}
ALLOWED_NAMES = {"LICENSE", ".gitignore", ".gitattributes"}
PRIVATE_PARTS = {
    "vendor", "decompiled", "decompilation", "disassembly", "research-private",
    "private-research", "captures", "ghidra-projects", "audit-private", "research", "audits", "private",
}
MAX_BYTES = 1024 * 1024


def git(root, *args, input_data=None, allowed=(0,)):
    result = subprocess.run(["git", *args], cwd=root, input=input_data, capture_output=True)
    if result.returncode not in allowed:
        raise ValueError("Git material check failed: " + result.stderr.decode("utf-8", "replace").strip())
    return result.stdout


def local_patterns(root):
    required = True
    path = Path(git(root, "rev-parse", "--git-path", "private-content-policy.json").decode().strip())
    if not path.is_absolute():
        path = root / path
    if not path.exists():
        if required:
            raise ValueError("Required Git-private content policy is missing.")
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    patterns = data["patterns"]
    if not isinstance(patterns, list) or not patterns or any(not isinstance(p, str) or not p for p in patterns):
        raise ValueError("Invalid Git-private content policy.")
    return [re.compile(p, re.IGNORECASE) for p in patterns]


def inspect_file(name, content, patterns):
    issues = []
    path = Path(name)
    if path.suffix.lower() not in ALLOWED_SUFFIXES and path.name not in ALLOWED_NAMES:
        issues.append(f"Unreviewed file type: {name}")
    if PRIVATE_PARTS & {p.lower() for p in path.parts}:
        issues.append(f"Excluded material directory: {name}")
    if len(content) > MAX_BYTES or b"\0" in content:
        issues.append(f"Binary or oversized material: {name}")
        return issues
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        issues.append(f"Non-UTF-8 material: {name}")
        return issues
    if any(pattern.search(name) for pattern in patterns):
        issues.append(f"Private content restriction in path: {name}")
    for number, line in enumerate(text.splitlines(), 1):
        if any(pattern.search(line) for pattern in patterns):
            # Do not print private text into public verification output.
            issues.append(f"Private content restriction: {name}:{number}")
    return issues


def check_repository(root=ROOT, staged=False):
    root = Path(root).resolve()
    patterns = local_patterns(root)
    issues = []
    files = {}
    if staged:
        for record in git(root, "ls-files", "--stage", "-z").split(b"\0"):
            if not record:
                continue
            metadata, raw_name = record.split(b"\t", 1)
            mode, oid, stage = metadata.decode().split()
            name = raw_name.decode("utf-8")
            if stage != "0" or mode not in {"100644", "100755"}:
                issues.append(f"Unexpected index entry: {name}")
                continue
            size = int(git(root, "cat-file", "-s", oid))
            if size > MAX_BYTES:
                issues.append(f"Binary or oversized material: {name}")
                continue
            files[name] = git(root, "cat-file", "blob", oid)
    else:
        names = git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z").decode("utf-8").split("\0")
        for name in sorted(set(names) - {""}):
            path = root / name
            if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
                issues.append(f"Unexpected file type: {name}")
                continue
            if path.stat().st_size > MAX_BYTES:
                issues.append(f"Binary or oversized material: {name}")
                continue
            files[name] = path.read_bytes()
    if files:
        ignored = git(root, "check-ignore", "--no-index", "--stdin", "-z",
                      input_data=("\0".join(files) + "\0").encode("utf-8"), allowed=(0, 1))
        for name in ignored.decode("utf-8").split("\0"):
            if name:
                issues.append(f"Ignored material present in commit candidates: {name}")
    for name, content in files.items():
        issues.extend(inspect_file(name, content, patterns))
    return sorted(set(issues)), len(files)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--staged", action="store_true", help="Inspect actual index bytes, including forced additions")
    args = parser.parse_args()
    try:
        issues, count = check_repository(staged=args.staged)
    except (ValueError, KeyError, OSError, re.error) as error:
        raise SystemExit(f"Repository material check failed: {error}") from error
    if issues:
        raise SystemExit("\n".join(issues))
    scope = "indexed files" if args.staged else "candidate files"
    print(f"Repository material check passed ({count} {scope}; private material excluded).")


if __name__ == "__main__":
    main()

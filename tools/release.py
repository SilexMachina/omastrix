#!/usr/bin/env python3
"""Offline metadata preparation only. Never tags, publishes, or runs services."""
import argparse
from datetime import date
import json
from pathlib import Path
import re

SEMVER = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?")


def parse_version(value):
    match = SEMVER.fullmatch(value) if isinstance(value, str) else None
    if not match:
        raise ValueError("version must be strict SemVer (without a v prefix)")
    pre = match[4].split(".") if match[4] else []
    if any(p.isdigit() and len(p) > 1 and p.startswith("0") for p in pre):
        raise ValueError("SemVer numeric prerelease identifiers cannot have leading zeros")
    return match


def read_metadata(root):
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    version = manifest.get("version") if isinstance(manifest, dict) else None
    parse_version(version)
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    headings = list(re.finditer(r"^## \[([^\]\n]+)\] - ([^\n]+)$", changelog, re.M))
    if len(headings) != len(re.findall(r"^##(?:[ \t]|$)", changelog, re.M)):
        raise ValueError("changelog sections must use ## [SemVer] - Unreleased or YYYY-MM-DD")
    if not headings or headings[0][1] != version:
        raise ValueError("changelog must begin with the current version's section")
    for heading in headings:
        try:
            parse_version(heading[1])
        except ValueError as exc:
            raise ValueError(f"changelog section: {exc}") from None
        if heading[2] != "Unreleased":
            try:
                if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", heading[2]):
                    raise ValueError("date format")
                date.fromisoformat(heading[2])
            except ValueError:
                raise ValueError("changelog dates must be Unreleased or valid YYYY-MM-DD") from None
    versions = [h[1] for h in headings]
    if len(versions) != len(set(versions)):
        raise ValueError("changelog contains duplicate version sections")
    end = headings[1].start() if len(headings) > 1 else len(changelog)
    if not re.search(r"^- \S", changelog[headings[0].end():end], re.M):
        raise ValueError("changelog current section needs at least one change note")
    return manifest, changelog


def precedence(version):
    match = parse_version(version)
    core = tuple(int(match[n]) for n in (1, 2, 3))
    # Stable sorts above prerelease; numeric identifiers below alphanumeric.
    pre = tuple((0, int(p)) if p.isdigit() else (1, p) for p in match[4].split(".")) if match[4] else ()
    return core, not bool(match[4]), pre


def bump(root, manifest, changelog, target, note, write):
    if precedence(target) <= precedence(manifest["version"]):
        raise ValueError("new version must have greater SemVer precedence")
    if not note or not note.strip() or any(c in note for c in "\r\n\v\f\x1c\x1d\x1e\x85\u2028\u2029"):
        raise ValueError("--note must be a nonempty single line")
    if re.search(rf"^## \[{re.escape(target)}\] - ", changelog, re.M):
        raise ValueError("changelog already contains the target version")
    old = manifest["version"]
    if write:
        manifest["version"] = target
        heading = re.search(r"^## \[", changelog, re.M)
        assert heading is not None  # read_metadata validated the section.
        offset = heading.start()
        notes = changelog[:offset] + f"## [{target}] - Unreleased\n\n- {note.strip()}\n\n" + changelog[offset:]
        # Validation precedes writes; no Git, network, or service operations.
        # Two file writes are not transactional: inspect both if interrupted.
        (root / "CHANGELOG.md").write_text(notes, encoding="utf-8")
        (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    mode = "wrote metadata" if write else "dry run; pass --write to apply"
    print(f"{old} -> {target} ({mode}; not a release)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="validate version and current changelog notes")
    commands.add_parser("version", help="print the manifest version")
    bump_parser = commands.add_parser("bump", help="prepare a higher version; dry run by default")
    bump_parser.add_argument("version")
    bump_parser.add_argument("--note", required=True)
    bump_parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    try:
        manifest, changelog = read_metadata(args.root)
        if args.command == "version":
            print(manifest["version"])
        elif args.command == "bump":
            bump(args.root, manifest, changelog, args.version, args.note, args.write)
        else:
            print(f"OK: {manifest['version']} (metadata only; release approval still required)")
    except (OSError, ValueError) as exc:
        parser.exit(1, f"error: {exc}\n")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Validate local links in every Git-tracked Markdown document."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]

FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
INLINE_LINK_START = re.compile(r"!?\[[^\]\n]*\]\(")
REFERENCE_DEFINITION = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*(?:<([^>]+)>|(\S+))")
HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")
EXPLICIT_ANCHOR = re.compile(r"<(?:a\s+(?:[^>]*?\s)?(?:id|name)|[^>]+\s+id)=[\"']([^\"']+)[\"']", re.I)
HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
INLINE_CODE = re.compile(r"(`+)(.+?)\1")
WINDOWS_ABSOLUTE_PATH = re.compile(r"^[A-Za-z]:[\\/]")


@dataclass(frozen=True)
class MarkdownLink:
    source: Path
    line: int
    target: str


def tracked_markdown_files(root: Path) -> list[Path]:
    completed = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.md"],
        cwd=root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git ls-files failed: {detail}")
    return [root / item.decode("utf-8") for item in completed.stdout.split(b"\0") if item]


def _mask_ignored_markdown(text: str) -> str:
    text = HTML_COMMENT.sub(lambda match: "\n" * match.group(0).count("\n"), text)
    output: list[str] = []
    active_fence: str | None = None
    for line in text.splitlines(keepends=True):
        fence = FENCE.match(line)
        if active_fence is not None:
            output.append("\n" if line.endswith("\n") else "")
            if fence and fence.group(1)[0] == active_fence:
                active_fence = None
            continue
        if fence:
            active_fence = fence.group(1)[0]
            output.append("\n" if line.endswith("\n") else "")
            continue
        output.append(INLINE_CODE.sub(lambda match: " " * len(match.group(0)), line))
    return "".join(output)


def _inline_target(text: str, start: int) -> tuple[str, int] | None:
    if start >= len(text):
        return "", start
    if text[start] == "<":
        end = text.find(">", start + 1)
        return None if end == -1 else (text[start + 1 : end], end + 1)

    position = start
    nested_parentheses = 0
    escaped = False
    while position < len(text):
        character = text[position]
        if escaped:
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == "(":
            nested_parentheses += 1
        elif character == ")":
            if nested_parentheses == 0:
                return text[start:position].strip(), position + 1
            nested_parentheses -= 1
        elif character.isspace() and nested_parentheses == 0:
            return text[start:position].strip(), position
        position += 1
    return None


def extract_links(source: Path, text: str) -> list[MarkdownLink]:
    masked = _mask_ignored_markdown(text)
    links: list[MarkdownLink] = []
    for match in INLINE_LINK_START.finditer(masked):
        parsed = _inline_target(masked, match.end())
        if parsed is None:
            continue
        target, _ = parsed
        links.append(MarkdownLink(source, masked.count("\n", 0, match.start()) + 1, target))

    for line_number, line in enumerate(masked.splitlines(), start=1):
        match = REFERENCE_DEFINITION.match(line)
        if match:
            links.append(MarkdownLink(source, line_number, match.group(1) or match.group(2)))
    return links


def _github_slug(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value).strip().lower()
    value = re.sub(r"\s+", "-", value)
    return "".join(
        character
        for character in value
        if character in "-_" or not unicodedata.category(character).startswith(("P", "S"))
    )


def markdown_anchors(path: Path) -> set[str]:
    text = _mask_ignored_markdown(path.read_text(encoding="utf-8"))
    anchors = set(EXPLICIT_ANCHOR.findall(text))
    occurrences: dict[str, int] = {}
    for line in text.splitlines():
        match = HEADING.match(line)
        if not match:
            continue
        base = _github_slug(match.group(1))
        count = occurrences.get(base, 0)
        occurrences[base] = count + 1
        anchors.add(base if count == 0 else f"{base}-{count}")
    return anchors


def _is_external(target: str) -> bool:
    parsed = urlsplit(target)
    return bool(parsed.scheme or parsed.netloc or target.startswith("//"))


def validate_markdown_links(root: Path, markdown_files: list[Path] | None = None) -> list[str]:
    root = root.resolve()
    files = tracked_markdown_files(root) if markdown_files is None else markdown_files
    errors: list[str] = []
    anchor_cache: dict[Path, set[str]] = {}

    for source in files:
        source = source.resolve()
        text = source.read_text(encoding="utf-8")
        for link in extract_links(source, text):
            target = link.target.strip()
            if not target or _is_external(target) or target.startswith("/") or WINDOWS_ABSOLUTE_PATH.match(target):
                continue

            path_text, separator, fragment = target.partition("#")
            path_text = path_text.partition("?")[0]
            decoded_path = unquote(path_text)
            destination = (source if not decoded_path else source.parent / decoded_path).resolve()
            display_source = source.relative_to(root).as_posix()

            try:
                display_destination = destination.relative_to(root).as_posix()
            except ValueError:
                errors.append(
                    f"{display_source}:{link.line}: local Markdown link {target!r} escapes the repository"
                )
                continue

            if not destination.exists():
                errors.append(
                    f"{display_source}:{link.line}: broken Markdown link {target!r} "
                    f"(resolved to {display_destination!r})"
                )
                continue

            if separator and destination.is_file() and destination.suffix.lower() in {".md", ".markdown"}:
                decoded_fragment = unquote(fragment)
                anchors = anchor_cache.setdefault(destination, markdown_anchors(destination))
                if decoded_fragment not in anchors:
                    errors.append(
                        f"{display_source}:{link.line}: missing anchor '#{decoded_fragment}' "
                        f"in {display_destination!r}"
                    )
    return errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="Repository root (defaults to this checkout)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        files = tracked_markdown_files(args.root.resolve())
        errors = validate_markdown_links(args.root, files)
    except (OSError, UnicodeError, RuntimeError) as error:
        print(f"Markdown link validation could not run: {error}", file=sys.stderr)
        return 2

    if errors:
        print("Markdown link validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(f"Markdown link validation passed: {len(files)} tracked Markdown files checked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

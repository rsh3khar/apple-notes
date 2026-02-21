#!/usr/bin/env python3
"""Export Apple Notes to Markdown files.

Usage:
    apple-notes --list-folders
    apple-notes --folder Logs
    apple-notes --folder Logs --last 7
    apple-notes --folder "1 Projects" --recursive
    apple-notes --folder Logs --output ~/Desktop/logs
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import re
import threading
import time
from pathlib import Path
from dataclasses import dataclass

from markdownify import markdownify

SPINNER_CHARS = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


def spinner(message: str, stop_event: threading.Event) -> None:
    i = 0
    while not stop_event.is_set():
        sys.stderr.write(f"\r{SPINNER_CHARS[i % len(SPINNER_CHARS)]} {message}")
        sys.stderr.flush()
        i += 1
        stop_event.wait(0.1)
    sys.stderr.write(f"\r\033[2K")
    sys.stderr.flush()


@dataclass
class Note:
    name: str
    body_html: str
    created: str
    modified: str
    folder: str

    @property
    def body_md(self) -> str:
        md = markdownify(self.body_html, heading_style="ATX", strip=["div"])
        md = re.sub(r"\n{3,}", "\n\n", md)
        return md.strip()

    @property
    def safe_filename(self) -> str:
        name = self.name.strip()
        name = re.sub(r"[/\\:*?\"<>|]", "-", name)
        name = re.sub(r"[\s-]+", "-", name)
        return name


def run_applescript(script: str, message: str = "Working...") -> str:
    stop = threading.Event()
    t = threading.Thread(target=spinner, args=(message, stop), daemon=True)
    t.start()
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=120,
        )
    finally:
        stop.set()
        t.join()
    if result.returncode != 0:
        print(f"AppleScript error: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def list_folder_tree() -> dict:
    """Return nested dict of {folder_name: {subfolder_name: {...}, ...}}."""
    script = """
tell application "Notes"
    set output to ""
    repeat with f in folders
        try
            set fName to name of f
            set subCount to count of folders of f
            set output to output & "<<<F>>>" & fName & "<<<SC>>>" & subCount & "<<</F>>>"
            if subCount > 0 then
                repeat with sf in folders of f
                    try
                        set sfName to name of sf
                        set sfSubCount to count of folders of sf
                        set output to output & "<<<SF>>>" & fName & "<<<P>>>" & sfName & "<<<SC>>>" & sfSubCount & "<<</SF>>>"
                    end try
                end repeat
            end if
        end try
    end repeat
    return output
end tell
"""
    raw = run_applescript(script, "Fetching folders...")

    tree = {}
    # Parse top-level folders
    for match in re.finditer(r"<<<F>>>(.+?)<<<SC>>>(\d+)<<<\/F>>>", raw):
        name, sub_count = match.group(1), int(match.group(2))
        tree[name] = {}

    # Parse subfolders
    for match in re.finditer(r"<<<SF>>>(.+?)<<<P>>>(.+?)<<<SC>>>(\d+)<<<\/SF>>>", raw):
        parent, child = match.group(1), match.group(2)
        if parent in tree:
            tree[parent][child] = {}

    return tree


def print_folder_tree(tree: dict, indent: int = 0) -> None:
    for name, children in sorted(tree.items()):
        print(f"{'  ' * indent}{name}")
        if children:
            print_folder_tree(children, indent + 1)


FETCH_NOTES_TEMPLATE = """
tell application "Notes"
    set targetFolder to {folder_ref}
    set noteList to notes of targetFolder
    set noteCount to count of noteList
    {limit_clause}
    set output to ""
    repeat with i from 1 to fetchCount
        set n to item i of noteList
        set noteName to name of n
        set noteBody to body of n
        set noteCreated to creation date of n as string
        set noteModified to modification date of n as string
        set output to output & "<<<NOTE_START>>>" & return
        set output to output & "<<<NAME>>>" & noteName & "<<<END_NAME>>>" & return
        set output to output & "<<<CREATED>>>" & noteCreated & "<<<END_CREATED>>>" & return
        set output to output & "<<<MODIFIED>>>" & noteModified & "<<<END_MODIFIED>>>" & return
        set output to output & "<<<BODY>>>" & noteBody & "<<<END_BODY>>>" & return
        set output to output & "<<<NOTE_END>>>" & return
    end repeat
    return output
end tell
"""


def _folder_ref(folder_path: str) -> str:
    """Convert a folder path like '1 Projects/Vestro' to an AppleScript reference."""
    parts = folder_path.split("/")
    if len(parts) == 1:
        return f'folder "{parts[0]}"'
    # Nested: folder "child" of folder "parent"
    ref = f'folder "{parts[-1]}"'
    for parent in reversed(parts[:-1]):
        ref = f'{ref} of folder "{parent}"'
    return ref


def fetch_notes(folder_path: str, last_n: int = None) -> list[Note]:
    if last_n:
        limit_clause = f"""
    if noteCount < {last_n} then
        set fetchCount to noteCount
    else
        set fetchCount to {last_n}
    end if"""
    else:
        limit_clause = "set fetchCount to noteCount"

    folder_ref = _folder_ref(folder_path)
    script = FETCH_NOTES_TEMPLATE.format(folder_ref=folder_ref, limit_clause=limit_clause)
    raw = run_applescript(script, f"Fetching notes from '{folder_path}'...")

    notes = []
    for block in raw.split("<<<NOTE_START>>>"):
        block = block.strip()
        if not block:
            continue

        name = _extract(block, "<<<NAME>>>", "<<<END_NAME>>>")
        created = _extract(block, "<<<CREATED>>>", "<<<END_CREATED>>>")
        modified = _extract(block, "<<<MODIFIED>>>", "<<<END_MODIFIED>>>")
        body = _extract(block, "<<<BODY>>>", "<<<END_BODY>>>")

        if name and body:
            notes.append(Note(
                name=name,
                body_html=body,
                created=created,
                modified=modified,
                folder=folder_path,
            ))

    return notes


def _extract(text: str, start_tag: str, end_tag: str) -> str:
    start = text.find(start_tag)
    end = text.find(end_tag)
    if start == -1 or end == -1:
        return ""
    return text[start + len(start_tag):end].strip()


def _get_subfolder_paths(folder_path: str, tree: dict) -> list[str]:
    """Get all subfolder paths recursively for a given folder."""
    parts = folder_path.split("/")
    subtree = tree
    for part in parts:
        if part in subtree:
            subtree = subtree[part]
        else:
            return []

    paths = []
    for child, grandchildren in subtree.items():
        child_path = f"{folder_path}/{child}"
        paths.append(child_path)
        paths.extend(_get_subfolder_paths(child_path, tree))
    return paths


def save_notes(notes: list[Note], output_dir: Path, add_metadata: bool = True) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    used_names: dict[str, int] = {}

    for note in notes:
        base_name = note.safe_filename
        if base_name in used_names:
            used_names[base_name] += 1
            filename = f"{base_name}-{used_names[base_name]}.md"
        else:
            used_names[base_name] = 0
            filename = f"{base_name}.md"

        content = ""
        if add_metadata:
            content += f"---\n"
            content += f"title: \"{note.name}\"\n"
            content += f"created: \"{note.created}\"\n"
            content += f"modified: \"{note.modified}\"\n"
            content += f"folder: \"{note.folder}\"\n"
            content += f"---\n\n"

        content += note.body_md + "\n"

        filepath = output_dir / filename
        filepath.write_text(content, encoding="utf-8")


def export_folder(folder_path: str, output_dir: Path, recursive: bool,
                  last_n: int = None, add_metadata: bool = True, tree: dict = None) -> int:
    """Export a folder and optionally its subfolders. Returns total notes exported."""
    total = 0

    # Export notes in this folder
    notes = fetch_notes(folder_path, last_n=last_n)
    if notes:
        save_notes(notes, output_dir, add_metadata=add_metadata)
        print(f"  {folder_path}: {len(notes)} notes")
        total += len(notes)

    # Recurse into subfolders
    if recursive and tree:
        for subfolder_path in _get_subfolder_paths(folder_path, tree):
            sub_name = subfolder_path.split("/")[-1]
            sub_name = re.sub(r"[/\\:*?\"<>|]", "-", sub_name)
            sub_output = output_dir / sub_name
            sub_notes = fetch_notes(subfolder_path)
            if sub_notes:
                save_notes(sub_notes, sub_output, add_metadata=add_metadata)
                print(f"  {subfolder_path}: {len(sub_notes)} notes")
                total += len(sub_notes)

    return total


def main():
    parser = argparse.ArgumentParser(
        description="Export Apple Notes to Markdown files",
    )
    parser.add_argument(
        "--list-folders",
        action="store_true",
        help="List all available Notes folders",
    )
    parser.add_argument(
        "--folder",
        type=str,
        help="Folder name to export (e.g. 'Logs', '1 Projects/Vestro')",
    )
    parser.add_argument(
        "--recursive", "-r",
        action="store_true",
        help="Export subfolders too, preserving directory structure",
    )
    parser.add_argument(
        "--last",
        type=int,
        default=None,
        help="Only export the last N notes (most recent first, top-level only)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output directory (default: ./<folder-name>)",
    )
    parser.add_argument(
        "--no-metadata",
        action="store_true",
        help="Skip YAML frontmatter metadata in exported files",
    )

    args = parser.parse_args()

    tree = list_folder_tree()
    all_folder_names = set(tree.keys())

    if args.list_folders:
        print(f"Folders:\n")
        print_folder_tree(tree)
        return

    if not args.folder:
        parser.error("Provide --folder or use --list-folders to see available folders")

    # Validate folder exists (check top-level and paths like "Parent/Child")
    parts = args.folder.split("/")
    valid = parts[0] in all_folder_names
    if valid and len(parts) > 1:
        subtree = tree[parts[0]]
        for part in parts[1:]:
            if part in subtree:
                subtree = subtree[part]
            else:
                valid = False
                break

    if not valid:
        print(f"Folder '{args.folder}' not found.", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(args.output) if args.output else Path(parts[-1])
    output_dir = output_dir.expanduser()

    print(f"Exporting from '{args.folder}'{'(recursive)' if args.recursive else ''}...")
    total = export_folder(
        args.folder,
        output_dir,
        recursive=args.recursive,
        last_n=args.last,
        add_metadata=not args.no_metadata,
        tree=tree,
    )

    if total == 0:
        print("No notes found.")
    else:
        print(f"\nDone. {total} notes exported to {output_dir}/")


if __name__ == "__main__":
    main()

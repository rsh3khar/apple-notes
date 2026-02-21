#!/usr/bin/env python3
"""Export Apple Notes to Markdown files.

Usage:
    python export_notes.py --list-folders
    python export_notes.py --folder Logs
    python export_notes.py --folder Logs --last 7
    python export_notes.py --folder Logs --output ~/Desktop/logs
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import re
from pathlib import Path
from dataclasses import dataclass

from markdownify import markdownify


@dataclass
class Note:
    name: str
    body_html: str
    created: str
    modified: str
    folder: str

    @property
    def body_md(self) -> str:
        """Convert HTML body to clean Markdown."""
        md = markdownify(self.body_html, heading_style="ATX", strip=["div"])
        # Clean up excessive blank lines
        md = re.sub(r"\n{3,}", "\n\n", md)
        return md.strip()

    @property
    def safe_filename(self) -> str:
        """Generate a filesystem-safe filename from the note name."""
        name = self.name.strip()
        # Replace slashes and other unsafe chars
        name = re.sub(r"[/\\:*?\"<>|]", "-", name)
        # Collapse multiple spaces/dashes
        name = re.sub(r"[\s-]+", "-", name)
        return name


def run_applescript(script: str) -> str:
    """Run an AppleScript and return its output."""
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        print(f"AppleScript error: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def list_folders() -> list[str]:
    """List all Apple Notes folder names."""
    raw = run_applescript('tell application "Notes" to return name of every folder')
    return [f.strip() for f in raw.split(",")]


FETCH_NOTES_TEMPLATE = """
tell application "Notes"
    set targetFolder to folder "{folder}"
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


def fetch_notes(folder: str, last_n: int | None = None) -> list[Note]:
    """Fetch notes from a specific folder."""
    if last_n:
        limit_clause = f"""
    if noteCount < {last_n} then
        set fetchCount to noteCount
    else
        set fetchCount to {last_n}
    end if"""
    else:
        limit_clause = "set fetchCount to noteCount"

    script = FETCH_NOTES_TEMPLATE.format(folder=folder, limit_clause=limit_clause)
    raw = run_applescript(script)

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
                folder=folder,
            ))

    return notes


def _extract(text: str, start_tag: str, end_tag: str) -> str:
    """Extract text between delimiter tags."""
    start = text.find(start_tag)
    end = text.find(end_tag)
    if start == -1 or end == -1:
        return ""
    return text[start + len(start_tag):end].strip()


def save_notes(notes: list[Note], output_dir: Path, add_metadata: bool = True) -> None:
    """Save notes as Markdown files to output directory."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Track filenames to handle duplicates
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

    print(f"Exported {len(notes)} notes to {output_dir}")


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
        help="Folder name to export (e.g. 'Logs')",
    )
    parser.add_argument(
        "--last",
        type=int,
        default=None,
        help="Only export the last N notes (most recent first)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output directory (default: ./export/<folder-name>)",
    )
    parser.add_argument(
        "--no-metadata",
        action="store_true",
        help="Skip YAML frontmatter metadata in exported files",
    )

    args = parser.parse_args()

    if args.list_folders:
        folders = list_folders()
        print(f"Found {len(folders)} folders:\n")
        for f in sorted(folders):
            print(f"  {f}")
        return

    if not args.folder:
        parser.error("Provide --folder or use --list-folders to see available folders")

    # Validate folder exists
    folders = list_folders()
    if args.folder not in folders:
        print(f"Folder '{args.folder}' not found.", file=sys.stderr)
        print(f"Available folders: {', '.join(sorted(folders))}", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(args.output) if args.output else Path("export") / args.folder
    output_dir = output_dir.expanduser()

    print(f"Fetching notes from '{args.folder}'...")
    notes = fetch_notes(args.folder, last_n=args.last)

    if not notes:
        print("No notes found in that folder.")
        return

    save_notes(notes, output_dir, add_metadata=not args.no_metadata)

    # Print summary
    print(f"\nFiles:")
    for f in sorted(output_dir.iterdir()):
        if f.suffix == ".md":
            print(f"  {f.name}")


if __name__ == "__main__":
    main()

# apple-notes

Export Apple Notes to Markdown files. Uses AppleScript under the hood — no database hacking, no special permissions.

## Install

```bash
pipx install git+https://github.com/rsh3khar/apple-notes.git
```

Requires macOS and Python 3.8+. If you don't have pipx: `brew install pipx`.

## Usage

```bash
# List all folders (with nested structure)
apple-notes --list-folders

# Export an entire folder
apple-notes --folder "My Notes"

# Export with subfolders
apple-notes --folder "My Notes" --recursive

# Export last 7 notes only
apple-notes --folder "My Notes" --last 7

# Export to a specific directory
apple-notes --folder "My Notes" --output ~/Desktop/notes

# Skip YAML frontmatter
apple-notes --folder "My Notes" --no-metadata
```

## Output

Each note becomes a `.md` file with YAML frontmatter:

```markdown
---
title: "Meeting Notes"
created: "Monday, 10 February 2025 at 9:00:00 AM"
modified: "Monday, 10 February 2025 at 10:30:00 AM"
folder: "My Notes"
---

# Meeting Notes

- Bullet points, headings, and formatting preserved
- Clean Markdown output
```

## Limitations

- Password-protected notes are not accessible via AppleScript
- Attachments (images, files) are not exported
- First run may trigger a macOS permission dialog for Notes access

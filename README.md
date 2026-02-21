# apple-notes

Export Apple Notes to Markdown files. Uses AppleScript under the hood — no database hacking, no special permissions.

## Requirements

- macOS
- Python 3.8+
- `markdownify` (`pip install markdownify`)

## Usage

```bash
# List all folders
python export_notes.py --list-folders

# Export an entire folder
python export_notes.py --folder "My Notes"

# Export last 7 notes only
python export_notes.py --folder "My Notes" --last 7

# Export to a specific directory
python export_notes.py --folder "My Notes" --output ~/Desktop/notes

# Skip YAML frontmatter
python export_notes.py --folder "My Notes" --no-metadata
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

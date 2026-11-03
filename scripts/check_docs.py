"""Check relative Markdown file targets without network or optional packages."""

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    documents = [root / name for name in ("README.md", "CONTRIBUTING.md", "CHANGELOG.md")]
    documents += sorted((root / "docs").rglob("*.md"))
    documents += sorted((root / "examples").rglob("*.md"))
    errors = []
    checked = 0
    for document in documents:
        text = document.read_text(encoding="utf-8")
        for target in re.findall(r"\[[^\]]*\]\(([^)\s]+)\)", text):
            parsed = urlsplit(target.strip("<>"))
            if parsed.scheme or not parsed.path:
                continue
            checked += 1
            path = (document.parent / unquote(parsed.path)).resolve()
            if not path.is_relative_to(root) or not path.exists():
                errors.append(f"{document.relative_to(root)}: invalid local target {target}")
        if re.search(r"/(?:Users|home|private/tmp)/", text):
            errors.append(
                f"{document.relative_to(root)}: contains a machine-specific absolute path"
            )
    for error in errors:
        print(error)
    if errors:
        return 1
    print(f"Checked {len(documents)} Markdown documents and {checked} local links.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

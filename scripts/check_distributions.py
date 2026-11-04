"""Inspect built archives for the files needed by the documented workflows."""

import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    dist = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "dist"
    metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    name = metadata["name"].replace("-", "_")
    version = metadata["version"]
    prefix = f"{name}-{version}"
    with zipfile.ZipFile(dist / f"{prefix}-py3-none-any.whl") as wheel:
        wheel_files = set(wheel.namelist())
    required_wheel = {
        "incident_lab/__main__.py",
        "incident_lab/data/incidents.json",
        "incident_lab/data/ground_truth.json",
        "incident_lab/data/challenge_incidents.json",
        "incident_lab/data/challenge_labels.json",
        f"{prefix}.dist-info/licenses/LICENSE",
    }
    with tarfile.open(dist / f"{prefix}.tar.gz", "r:gz") as archive:
        source_files = {item.name.removeprefix(prefix + "/") for item in archive.getmembers()}
    required_source = {
        "README.md",
        "LICENSE",
        "CONTRIBUTING.md",
        "CHANGELOG.md",
        "uv.lock",
        "pyproject.toml",
        "Dockerfile",
        ".dockerignore",
        ".gitattributes",
    }
    for directory in ("docs", "examples", "scripts", "tests", "incident_lab", ".github"):
        required_source.update(
            str(path.relative_to(root))
            for path in (root / directory).rglob("*")
            if path.is_file()
            and path.suffix in {".py", ".json", ".md", ".yml"}
            and "__pycache__" not in path.parts
        )
    missing = (required_wheel - wheel_files) | (required_source - source_files)
    forbidden = {".venv", "artifacts", "__pycache__", ".git", ".aws", ".ollama"}
    unexpected = [path for path in wheel_files | source_files if set(Path(path).parts) & forbidden]
    if missing or unexpected:
        print(f"Missing distribution files: {sorted(missing)}")
        print(f"Unexpected local files: {sorted(unexpected)}")
        return 1
    print(
        "Wheel contains the CLI, fixture resources, and license; source archive includes the documented workflows."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

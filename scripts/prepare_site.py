"""Prepare the public website without publishing the local Python application."""
from pathlib import Path
from shutil import copytree, rmtree


def prepare_site():
    root = Path(__file__).resolve().parents[1]
    destination = root / "dist"
    if destination.exists():
        rmtree(destination)
    copytree(root / "web", destination)
    copytree(root / "assets", destination / "assets")


if __name__ == "__main__":
    prepare_site()

"""Athlete profile and program versions under $THP_DATA_DIR/athlete. Versions are never overwritten."""

from __future__ import annotations

from pathlib import Path

from src.kb.paths import athlete_dir
from src.planner.schema import Profile, Program


class StaleProgramError(RuntimeError):
    """The program changed since this candidate was built; rebuild it from the latest version."""


def _dir(directory: Path | None) -> Path:
    return directory or athlete_dir()


def load_profile(directory: Path | None = None) -> Profile | None:
    path = _dir(directory) / "profile.json"
    return Profile.model_validate_json(path.read_text()) if path.exists() else None


def save_profile(profile: Profile, directory: Path | None = None) -> Path:
    path = _dir(directory) / "profile.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(profile.model_dump_json(indent=2))
    return path


def _program_dir(directory: Path | None) -> Path:
    return _dir(directory) / "program"


def latest_version(directory: Path | None = None) -> int:
    versions = [int(p.stem[1:]) for p in _program_dir(directory).glob("v[0-9][0-9][0-9][0-9].json")]
    return max(versions, default=0)


def load_program(version: int | None = None, directory: Path | None = None) -> Program | None:
    version = latest_version(directory) if version is None else version
    path = _program_dir(directory) / f"v{version:04d}.json"
    return Program.model_validate_json(path.read_text()) if version and path.exists() else None


def save_program(program: Program, directory: Path | None = None) -> Path:
    latest = latest_version(directory)
    if program.version != latest + 1:
        raise StaleProgramError(f"candidate is v{program.version} but the latest saved version is v{latest}")
    path = _program_dir(directory) / f"v{program.version:04d}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as f:  # "x": fail rather than overwrite
        f.write(program.model_dump_json(indent=2))
    return path

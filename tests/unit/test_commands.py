from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import pytest

from speechmatics_tools.download import write_transcripts
from speechmatics_tools.errors import ValidationError
from speechmatics_tools.start import load_config


def start_args(**overrides: object) -> Namespace:
    values: dict[str, object] = {
        "config": None,
        "language": None,
        "model": None,
        "diarization": None,
        "title": None,
    }
    values.update(overrides)
    return Namespace(**values)


def test_start_defaults_match_requested_speechmatics_preset() -> None:
    config = load_config(start_args())

    assert config == {
        "type": "transcription",
        "transcription_config": {
            "language": "lt",
            "model": "enhanced",
            "diarization": "none",
            "punctuation_overrides": {
                "sensitivity": 0.5,
                "permitted_marks": [",", ".", "?", "!"],
            },
        },
        "output_config": {
            "srt_overrides": {
                "max_line_length": 37,
                "max_lines": 2,
            }
        },
    }


def test_cli_values_override_advanced_config(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "type": "transcription",
                "transcription_config": {"language": "lt", "model": "standard"},
                "tracking": {"tags": ["original"]},
            }
        ),
        encoding="utf-8",
    )

    config = load_config(
        start_args(
            config=str(path),
            language="en",
            model="enhanced",
            diarization="speaker",
            title="Interview",
        )
    )

    assert config["transcription_config"] == {
        "language": "en",
        "model": "enhanced",
        "diarization": "speaker",
    }
    assert config["tracking"] == {"tags": ["original"], "title": "Interview"}


def test_write_transcripts_creates_both_formats(tmp_path: Path) -> None:
    paths = write_transcripts(
        tmp_path,
        "abc123",
        {"json": b"{}", "srt": b"subtitle"},
        overwrite=False,
    )

    assert paths == [tmp_path / "abc123.json", tmp_path / "abc123.srt"]
    assert paths[0].read_bytes() == b"{}"
    assert paths[1].read_bytes() == b"subtitle"


def test_write_transcripts_requires_explicit_overwrite(tmp_path: Path) -> None:
    existing = tmp_path / "abc123.json"
    existing.write_bytes(b"original")

    with pytest.raises(ValidationError):
        write_transcripts(tmp_path, "abc123", {"json": b"new"}, overwrite=False)

    assert existing.read_bytes() == b"original"


def test_write_transcripts_rolls_back_when_second_install_fails(tmp_path: Path) -> None:
    real_replace = __import__("os").replace

    def fail_srt_install(source: Path, destination: Path) -> None:
        if Path(source).suffix == ".tmp" and Path(destination).suffix == ".srt":
            raise OSError("injected second install failure")
        real_replace(source, destination)

    with (
        patch("speechmatics_tools.download.os.replace", fail_srt_install),
        pytest.raises(ValidationError, match="transaction"),
    ):
        write_transcripts(
            tmp_path,
            "abc123",
            {"json": b"{}", "srt": b"subtitle"},
            overwrite=False,
        )

    assert list(tmp_path.iterdir()) == []


def test_write_transcripts_restores_both_originals_when_overwrite_fails(
    tmp_path: Path,
) -> None:
    json_path = tmp_path / "abc123.json"
    srt_path = tmp_path / "abc123.srt"
    json_path.write_bytes(b"old-json")
    srt_path.write_bytes(b"old-srt")
    real_replace = __import__("os").replace

    def fail_srt_install(source: Path, destination: Path) -> None:
        if Path(source).suffix == ".tmp" and Path(destination).suffix == ".srt":
            raise OSError("injected second install failure")
        real_replace(source, destination)

    with (
        patch("speechmatics_tools.download.os.replace", fail_srt_install),
        pytest.raises(ValidationError, match="transaction"),
    ):
        write_transcripts(
            tmp_path,
            "abc123",
            {"json": b"new-json", "srt": b"new-srt"},
            overwrite=True,
        )

    assert json_path.read_bytes() == b"old-json"
    assert srt_path.read_bytes() == b"old-srt"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["abc123.json", "abc123.srt"]

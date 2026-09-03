from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

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

"""Submit a Speechmatics transcription job."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .cli_common import (
    add_connection_arguments,
    client_from_args,
    print_json,
    require_json_object,
    run_command,
)
from .errors import ValidationError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="start_transcription.py",
        description="Upload media and start an asynchronous Speechmatics Batch job.",
    )
    parser.add_argument("media", help="Local audio or video file.")
    parser.add_argument("--config", help="Advanced Speechmatics JobConfig JSON file.")
    parser.add_argument("--language", help="Transcription language (default: en).")
    parser.add_argument(
        "--model",
        choices=("standard", "enhanced", "melia-1"),
        help="Speechmatics transcription model (default: standard).",
    )
    parser.add_argument(
        "--diarization",
        choices=("none", "speaker", "channel"),
        help="Speaker/channel labeling mode (default: none).",
    )
    parser.add_argument("--title", help="Optional tracking title for the job.")
    add_connection_arguments(parser)
    return parser


def load_config(args: argparse.Namespace) -> dict[str, Any]:
    """Load an advanced config or create a minimal config, then apply CLI overrides."""

    if args.config:
        path = Path(args.config).expanduser()
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ValidationError(f"Cannot read job config: {path}") from exc
        except json.JSONDecodeError as exc:
            raise ValidationError(f"Job config is not valid JSON: {path}") from exc
        config: dict[str, Any] = dict(require_json_object(value, "Job config"))
    else:
        config = {
            "type": "transcription",
            "transcription_config": {
                "language": "en",
                "model": "standard",
                "diarization": "none",
            },
        }

    transcription = config.get("transcription_config")
    if not isinstance(transcription, dict):
        raise ValidationError("Job config requires a `transcription_config` object.")
    if args.language:
        transcription["language"] = args.language
    if args.model:
        transcription["model"] = args.model
    if args.diarization:
        transcription["diarization"] = args.diarization
    if args.title:
        tracking = config.setdefault("tracking", {})
        if not isinstance(tracking, dict):
            raise ValidationError("Job config `tracking` must be an object.")
        tracking["title"] = args.title
    return config


def _run(args: argparse.Namespace) -> int:
    response = client_from_args(args).create_job(Path(args.media).expanduser(), load_config(args))
    print_json(response)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return run_command(_run, build_parser(), argv)

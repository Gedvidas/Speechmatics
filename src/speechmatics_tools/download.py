"""Download Speechmatics transcripts as JSON, SRT, or both."""

from __future__ import annotations

import argparse
import os
import uuid
from collections.abc import Mapping, Sequence
from contextlib import suppress
from pathlib import Path

from .cli_common import add_connection_arguments, client_from_args, print_json, run_command
from .errors import ValidationError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="download_transcription.py",
        description="Download a completed Speechmatics transcript.",
    )
    parser.add_argument("job_id", help="Completed Speechmatics job ID.")
    parser.add_argument("--format", choices=("json", "srt", "both"), default="json")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Destination directory (default: WORKSPACE/transcripts).",
    )
    parser.add_argument("--overwrite", action="store_true", help="Replace existing transcript files.")
    add_connection_arguments(parser)
    return parser


def write_transcripts(
    output_dir: Path,
    job_id: str,
    content: Mapping[str, bytes],
    *,
    overwrite: bool,
) -> list[Path]:
    """Atomically write all downloaded formats after checking collision policy."""

    destinations = {name: output_dir / f"{job_id}.{name}" for name in content}
    existing = [path for path in destinations.values() if path.exists()]
    if existing and not overwrite:
        names = ", ".join(str(path) for path in existing)
        raise ValidationError(f"Output already exists; pass --overwrite to replace: {names}")
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ValidationError(f"Cannot create transcript directory: {output_dir}") from exc

    written: list[Path] = []
    for name, payload in content.items():
        destination = destinations[name]
        temporary = output_dir / f".{destination.name}.{uuid.uuid4().hex}.tmp"
        try:
            temporary.write_bytes(payload)
            os.replace(temporary, destination)
        except OSError as exc:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)
            raise ValidationError(f"Cannot write transcript: {destination}") from exc
        written.append(destination)
    return written


def _run(args: argparse.Namespace) -> int:
    client = client_from_args(args)
    formats = ("json", "srt") if args.format == "both" else (args.format,)
    downloaded = {name: client.download_transcript(args.job_id, name) for name in formats}
    workspace = Path(args.workspace).expanduser() if args.workspace else Path(
        os.environ.get("SPEECHMATICS_WORKSPACE", ".local")
    ).expanduser()
    output_dir = Path(args.output_dir).expanduser() if args.output_dir else workspace / "transcripts"
    paths = write_transcripts(output_dir, args.job_id, downloaded, overwrite=args.overwrite)
    print_json({"job_id": args.job_id, "files": [str(path) for path in paths]})
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return run_command(_run, build_parser(), argv)

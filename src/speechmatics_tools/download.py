"""Download Speechmatics transcripts as JSON, SRT, or both."""

from __future__ import annotations

import argparse
import os
import uuid
from collections.abc import Mapping, Sequence
from contextlib import suppress
from pathlib import Path

from .cli_common import add_connection_arguments, connection_from_args, print_json, run_command
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
    """Write all formats as one rollback-capable local transaction."""

    destinations = {name: output_dir / f"{job_id}.{name}" for name in content}
    existing = [path for path in destinations.values() if path.exists()]
    if existing and not overwrite:
        names = ", ".join(str(path) for path in existing)
        raise ValidationError(f"Output already exists; pass --overwrite to replace: {names}")
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ValidationError(f"Cannot create transcript directory: {output_dir}") from exc

    temporary_files: dict[str, Path] = {}
    backup_files: dict[str, Path] = {}
    installed: list[Path] = []
    preserve_backups = False
    try:
        for name, payload in content.items():
            destination = destinations[name]
            temporary = output_dir / f".{destination.name}.{uuid.uuid4().hex}.tmp"
            temporary_files[name] = temporary
            with temporary.open("xb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())

        if overwrite:
            for name, destination in destinations.items():
                if destination.exists():
                    backup = output_dir / f".{destination.name}.{uuid.uuid4().hex}.bak"
                    os.replace(destination, backup)
                    backup_files[name] = backup

        for name, destination in destinations.items():
            os.replace(temporary_files[name], destination)
            installed.append(destination)
    except OSError as exc:
        for destination in reversed(installed):
            with suppress(OSError):
                destination.unlink(missing_ok=True)
        restore_failure: OSError | None = None
        for name, backup in backup_files.items():
            if backup.exists():
                try:
                    os.replace(backup, destinations[name])
                except OSError as rollback_exc:
                    restore_failure = rollback_exc
        if restore_failure is not None:
            preserve_backups = True
            raise ValidationError(
                f"Transcript transaction failed and rollback was incomplete: {output_dir}"
            ) from restore_failure
        raise ValidationError(f"Cannot commit transcript transaction: {output_dir}") from exc
    finally:
        for temporary in temporary_files.values():
            with suppress(OSError):
                temporary.unlink(missing_ok=True)
        if not preserve_backups:
            for backup in backup_files.values():
                with suppress(OSError):
                    backup.unlink(missing_ok=True)
    return list(destinations.values())


def _run(args: argparse.Namespace) -> int:
    connection = connection_from_args(args, job_id=args.job_id)
    client = connection.client
    formats = ("json", "srt") if args.format == "both" else (args.format,)
    downloaded = {name: client.download_transcript(args.job_id, name) for name in formats}
    output_dir = (
        Path(args.output_dir).expanduser().resolve()
        if args.output_dir
        else connection.workspace / "transcripts"
    )
    paths = write_transcripts(output_dir, args.job_id, downloaded, overwrite=args.overwrite)
    print_json(
        {
            "job_id": args.job_id,
            "region": connection.region,
            "files": [str(path) for path in paths],
        }
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return run_command(_run, build_parser(), argv)

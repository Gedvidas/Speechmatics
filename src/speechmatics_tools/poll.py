"""Poll a Speechmatics transcription job."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from .cli_common import add_connection_arguments, connection_from_args, print_json, run_command


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="poll_transcription.py",
        description="Fetch once or poll a Speechmatics Batch job until it finishes.",
    )
    parser.add_argument("job_id", help="Job ID returned by start_transcription.py.")
    parser.add_argument("--once", action="store_true", help="Fetch one status and exit.")
    parser.add_argument("--interval-seconds", type=float, default=5.0)
    parser.add_argument("--timeout-seconds", type=float, default=1800.0)
    add_connection_arguments(parser)
    return parser


def _run(args: argparse.Namespace) -> int:
    client = connection_from_args(args, job_id=args.job_id).client
    if args.once:
        print_json(client.get_job(args.job_id))
        return 0

    last_status = ""
    for body in client.iter_job_status(
        args.job_id,
        interval_seconds=args.interval_seconds,
        timeout_seconds=args.timeout_seconds,
    ):
        print_json(body)
        last_status = body["job"]["status"]
    if last_status == "done":
        return 0
    if last_status == "rejected":
        return 2
    return 3


def main(argv: Sequence[str] | None = None) -> int:
    return run_command(_run, build_parser(), argv)

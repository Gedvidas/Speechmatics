from __future__ import annotations

from speechmatics_tools.download import build_parser as build_download_parser
from speechmatics_tools.poll import build_parser as build_poll_parser
from speechmatics_tools.start import build_parser as build_start_parser


def test_all_three_command_parsers_are_available() -> None:
    assert build_start_parser().prog == "start_transcription.py"
    assert build_poll_parser().prog == "poll_transcription.py"
    assert build_download_parser().prog == "download_transcription.py"

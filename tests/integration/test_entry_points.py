from __future__ import annotations

from importlib.metadata import entry_points
from importlib.resources import files

from speechmatics_tools.download import build_parser as build_download_parser
from speechmatics_tools.poll import build_parser as build_poll_parser
from speechmatics_tools.start import build_parser as build_start_parser


def test_all_three_command_parsers_are_available() -> None:
    assert build_start_parser().prog == "start_transcription.py"
    assert build_poll_parser().prog == "poll_transcription.py"
    assert build_download_parser().prog == "download_transcription.py"


def test_all_three_console_scripts_are_packaged() -> None:
    scripts = {
        entry.name: entry.value
        for entry in entry_points(group="console_scripts")
        if entry.name.startswith("speechmatics-")
    }

    assert scripts == {
        "speechmatics-start": "speechmatics_tools.start:main",
        "speechmatics-poll": "speechmatics_tools.poll:main",
        "speechmatics-download": "speechmatics_tools.download:main",
    }


def test_default_job_config_is_a_packaged_resource() -> None:
    resource = files("speechmatics_tools").joinpath("data/job-defaults.json")

    assert resource.is_file()
    assert '"language": "lt"' in resource.read_text(encoding="utf-8")

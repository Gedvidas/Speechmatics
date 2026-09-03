from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "private_path",
    [
        ".local/secrets/speechmatics-api-key.txt",
        ".local/secrets/speechmatics-api-key.json",
        ".local/media/customer-interview.mp3",
        ".local/transcripts/abc123.json",
        ".local/transcripts/abc123.srt",
    ],
)
def test_private_workspace_is_gitignored(private_path: str) -> None:
    if shutil.which("git") is None:
        pytest.skip("Git is not available.")
    result = subprocess.run(
        ["git", "check-ignore", "--quiet", private_path],
        cwd=REPOSITORY_ROOT,
        check=False,
    )
    assert result.returncode == 0, f"Private path is not ignored: {private_path}"


def test_no_private_workspace_file_is_tracked() -> None:
    if shutil.which("git") is None:
        pytest.skip("Git is not available.")
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", ".local"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
    )
    assert result.stdout == b""


def test_committed_credentials_example_contains_placeholder_only() -> None:
    credentials = json.loads(
        (REPOSITORY_ROOT / "examples" / "credentials.example.json").read_text(
            encoding="utf-8"
        )
    )
    assert credentials == {"api_key": "YOUR_SPEECHMATICS_API_KEY"}

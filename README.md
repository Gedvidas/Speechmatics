# Speechmatics Batch transcription tools

Three small Python scripts for the asynchronous Speechmatics Batch API:

1. submit a local audio or video file as a transcription job;
2. poll the job until it is done or rejected;
3. download the transcript as JSON, SRT, or both.

The project follows the same layout and safety conventions as the neighboring `Facebook` and
`Tiktok` repositories: reusable code lives in `src/`, executable scripts stay thin, private data
lives under a Git-ignored `.local/` directory, and all HTTP behavior is tested without real API
calls.

## Requirements

- Python 3.11 or newer;
- a Speechmatics Batch API key;
- a supported input file: WAV, MP3, AAC, OGG, MPEG, AMR, M4A, MP4, or FLAC.

The tools default to the Speechmatics EU1 endpoint. Use the same `--region` value for starting,
polling, and downloading a particular job. Available values are `eu1`, `eu2`, `us1`, `us2`, and
`au1`; EU2 and US2 are enterprise endpoints.

## Install

PowerShell:

```powershell
cd C:\Users\gedvi\Documents\GitHub\Clipping\Transcribe\Speechmatics
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## API key

The source key was plain text, so its private repo-local copy was normalized to JSON and stored at:

```text
.local/secrets/speechmatics-api-key.json
```

In a source checkout, this `.local/` path is resolved from the repository root even when an
installed console command is launched from another working directory. In a wheel-only install,
the stable default is `%LOCALAPPDATA%\SpeechmaticsBatchTools` on Windows and
`$XDG_DATA_HOME/speechmatics-batch-tools` (or `~/.local/share/speechmatics-batch-tools`) on Unix.
`--workspace` and `SPEECHMATICS_WORKSPACE` override either default and are normalized to absolute
paths.

The whole repository `.local/` directory is ignored by Git. The credentials reader accepts either a plain
text key or a JSON file containing an `api_key` string. To replace the JSON credential manually:

```powershell
New-Item -ItemType Directory -Force .local\secrets
Copy-Item examples\credentials.example.json .local\secrets\speechmatics-api-key.json
```

Then replace the placeholder. This is the default credentials path, so no `--credentials` option
is needed. Alternatively, set the
`SPEECHMATICS_API_KEY` environment variable; an explicit `--credentials` file takes precedence.
Never place a real key in `examples/`.

As a second safety boundary, supported media extensions, SRT files, `transcripts/` directories,
and files named `speechmatics-api-key.*` are ignored anywhere in this repository. Keep source
media under `.local/media/`; never force-add ignored customer data with `git add -f`.

## 1. Start a transcription job

Without extra options, the command loads the packaged
`src/speechmatics_tools/data/job-defaults.json` preset:

- Lithuanian (`lt`);
- enhanced model;
- diarization off;
- punctuation on with sensitivity `0.5` and marks `, . ? !`;
- SRT formatting at 37 characters per line and 2 lines per subtitle section;
- custom dictionary, translation, audio filtering, summary, topics, chapters, and audio events
  off (their optional config sections are omitted).

Start a job with those defaults:

```powershell
python scripts\start_transcription.py "C:\media\interview.mp3"
```

Select a language, model, and speaker diarization:

```powershell
python scripts\start_transcription.py "C:\media\interview.mp3" `
  --language en `
  --model enhanced `
  --diarization speaker `
  --title "Interview 2026-09-03"
```

The command prints the Speechmatics creation response, including the job `id`, selected `region`,
and local record path. It also stores non-secret resume metadata in `.local/jobs/JOB_ID.json`.
Poll and download read the saved region automatically, so a non-EU1 job cannot silently fall back
to EU1. An explicit conflicting `--region` is rejected. For advanced features, copy and edit
`examples/job-config.example.json`, then submit it with `--config`.
Explicit `--language`, `--model`, `--diarization`, and `--title` options override the matching
fields from that JSON file. To change repository-wide defaults, edit
`src/speechmatics_tools/data/job-defaults.json`; JSON is used because it maps directly to the
Speechmatics `JobConfig` request without an additional parser or dependency.

Status and transcript GET requests retry transient network failures and HTTP
`429/500/502/503/504`, honoring `Retry-After` and using capped exponential backoff with jitter.
Job submission retries only an explicit `429`. A network failure during POST is reported as an
unknown outcome and is never resubmitted automatically, avoiding accidental duplicate jobs.
Multipart upload uses a 120-second socket timeout and a 600-second response timeout so large WAV
files tolerate temporary upload stalls. This does not weaken the unknown-outcome safeguard.

### Recovering an unknown submit outcome

If `start_transcription.py` reports that the submission outcome is unknown, do not immediately
submit the media again. The server may have accepted the POST even though the client did not
receive its response. First list recent jobs in the same region and match the submitted
`tracking.title`, media name, and creation time. Resume polling with the existing job ID if a
match is found; submit a new job only after confirming that no matching recent job exists.

For orchestrated runs, always set a unique `--title`. The Clipping Step 4–6 runner uses its local
test job ID for that title, making this reconciliation deterministic.

## 2. Poll transcription status

Poll every five seconds for up to 30 minutes:

```powershell
python scripts\poll_transcription.py JOB_ID
```

Fetch only the current state:

```powershell
python scripts\poll_transcription.py JOB_ID --once
```

For continuous polling, exit code `0` means `done`, `2` means `rejected`, and `3` means the local
polling timeout elapsed while the job was still running. An API or validation error returns `1`.

## 3. Download JSON, SRT, or both

Files are written to `.local/transcripts` by default:

```powershell
python scripts\download_transcription.py JOB_ID --format json
python scripts\download_transcription.py JOB_ID --format srt
python scripts\download_transcription.py JOB_ID --format both
```

Choose another output directory and replace existing files explicitly:

```powershell
python scripts\download_transcription.py JOB_ID `
  --format both `
  --output-dir "D:\transcripts" `
  --overwrite
```

JSON downloads use Speechmatics `json-v2`; SRT downloads use `srt`. The command validates JSON
before writing it. For `--format both`, it stages both files first and rolls back the complete pair
if either replacement fails; `--overwrite` also restores both prior versions on failure.

## Shared options

All three scripts accept:

- `--credentials PATH` for a specific text or JSON API-key file;
- `--workspace PATH` to move the private workspace from `.local`;
- `--region {eu1,eu2,us1,us2,au1}` to select the Speechmatics Batch SaaS endpoint when starting a
  job. Later commands use its saved region automatically.

`SPEECHMATICS_WORKSPACE` and `SPEECHMATICS_REGION` provide environment-variable defaults. One
shared resolver supplies the same absolute workspace to credential loading, job records, and
transcript output.

## Project structure

```text
Speechmatics/
├── .github/workflows/ci.yml
├── docs/architecture/batch-flow.md
├── examples/
├── scripts/
│   ├── start_transcription.py
│   ├── poll_transcription.py
│   └── download_transcription.py
├── src/speechmatics_tools/
│   ├── data/job-defaults.json
│   └── ...
├── tests/
├── AGENTS.md
└── pyproject.toml
```

## Quality checks

```powershell
python -m ruff check .
python -m mypy src scripts
python -m pytest -q
python -m compileall -q src scripts
python -m build
git diff --check
```

Tests use fake HTTP sessions and do not contact Speechmatics. CI also builds the wheel, installs it
into a clean virtual environment, runs all three packaged console entry points, and verifies the
packaged default JSON resource.

## Official documentation

- [Batch quickstart](https://docs.speechmatics.com/speech-to-text/batch/quickstart)
- [Authentication and regional endpoints](https://docs.speechmatics.com/get-started/authentication)
- [Batch input and job configuration](https://docs.speechmatics.com/speech-to-text/batch/input)
- [Batch status and transcript output](https://docs.speechmatics.com/speech-to-text/batch/output)
- [Batch API reference](https://docs.speechmatics.com/api-ref)

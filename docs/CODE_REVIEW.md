# Speechmatics repository code review

Review date: 2026-09-03

Reviewed commit: `a172fc7` (`main`)

Scope: tracked application code, CLI behavior, tests, packaging, CI, documentation, and repository
safety. No implementation fixes are included in this review.

## Executive summary

The three-command workflow is small, readable, and works end to end. Authentication is kept out
of URLs and output, job IDs are validated before URL interpolation, transcript JSON is validated,
and private files under `.local/` are protected. Ruff, mypy, compilation, and all 31 tests pass.
A wheel build also confirmed that `data/job-defaults.json` is currently packaged correctly.

The main remaining risks are operational rather than algorithmic. A media or credential file
placed elsewhere in the repository can still be committed, and the region required to retrieve a
job is not persisted with its ID. Transient Speechmatics failures are not retried, while the
two-format downloader can leave a partial result even though its contract says the operation is
atomic.

| Priority | Count | Meaning |
| --- | ---: | --- |
| P0 | 0 | Release blocker or immediate compromise |
| P1 | 2 | High-impact correctness or data-safety issue |
| P2 | 2 | Material reliability or consistency issue |
| P3 | 2 | Maintainability or verification gap |

## Findings

### CR-01 — P1: customer media and credential protection depends entirely on using `.local/`

Affected code:

- [`.gitignore`](../.gitignore#L11)
- [`test_repository_safety.py`](../tests/integration/test_repository_safety.py#L13)
- [`client.py`](../src/speechmatics_tools/client.py#L70)

The repository policy says customer media and real credentials must never be committed, but the
only ignore rule is `.local/`. The safety tests likewise check only paths below `.local/`. The CLI
accepts a media file from any path and does not warn when a file is inside the repository but
outside the ignored workspace.

This was reproduced with Git directly: `sample.wav` and `speechmatics-api-key.json` at repository
root are not ignored, while `.local/media/sample.wav` is ignored. A routine `git add .` can
therefore stage customer audio or a misplaced key. This is especially credible because the first
manual workflow placed `test_audio.wav` at repository root before it was moved to `.local/media/`.

Recommended fix:

1. Ignore supported media extensions and known real credential names at repository scope, or
   reject files located inside the repository unless `git check-ignore` confirms protection.
2. Add integration tests for representative root-level media and key paths.
3. Consider a pre-commit/CI secret and large-media scan as a second boundary; `.gitignore` alone
   is bypassed by `git add -f`.

### CR-02 — P1: job region is not persisted, so later commands can query the wrong API endpoint

Affected code:

- [`cli_common.py`](../src/speechmatics_tools/cli_common.py#L24)
- [`start.py`](../src/speechmatics_tools/start.py#L84)
- [`poll.py`](../src/speechmatics_tools/poll.py#L24)
- [`download.py`](../src/speechmatics_tools/download.py#L67)

Speechmatics requires every request for a job to use the same regional endpoint that created it.
The start command prints only the API creation response (normally the job ID). Poll and download
create new clients from an independent `--region` value which silently defaults to EU1. A job
started with `--region us1`, `au1`, `eu2`, or `us2` will therefore look missing when a later command
omits the flag.

The README warning reduces the chance of misuse but does not make the three-script workflow safe.
The requirement is confirmed by the current
[Speechmatics authentication and endpoint documentation](https://docs.speechmatics.com/get-started/authentication).

Recommended fix:

1. After job creation, atomically write `.local/jobs/<job-id>.json` containing at least `id`,
   `region`, `data_name`, `created_at`, and non-secret config metadata.
2. Let poll and download resolve the saved region automatically; reject a conflicting explicit
   `--region` unless an override flag is supplied.
3. Include `region` in start-command output and test a non-EU1 start-to-download flow.

### CR-03 — P2: transient network, `429`, and `5xx` responses terminate every operation immediately

Affected code:

- [`client.py` job submission](../src/speechmatics_tools/client.py#L145)
- [`client.py` status request](../src/speechmatics_tools/client.py#L165)
- [`client.py` transcript request](../src/speechmatics_tools/client.py#L215)
- [`test_client.py`](../tests/unit/test_client.py#L52)

All three HTTP paths translate the first `RequestException` or unexpected status into `ApiError`.
There is no retry, backoff, jitter, or `Retry-After` handling. The current API reference explicitly
lists `429` and `500` responses for Batch endpoints, and Speechmatics documents rate limiting for
job creation and status polling.

One brief service or connection failure aborts a 30-minute polling command, even though retrying a
GET is safe. Submission requires more care: blindly retrying a POST after an ambiguous timeout can
create a duplicate chargeable job.

Recommended fix:

1. Retry idempotent GET requests for connection failures, `429`, `502`, `503`, and `504`, honoring
   `Retry-After` and applying capped exponential backoff with jitter.
2. For POST, retry only responses known not to have accepted the body. On an ambiguous timeout,
   return a distinct error and provide a reconciliation path using tracking metadata or recent-job
   listing rather than submitting again automatically.
3. Add deterministic tests for recovery, retry exhaustion, `Retry-After`, and POST ambiguity.

### CR-04 — P2: `--format both` can leave a partial or mixed-version result

Affected code:

- [`download.py`](../src/speechmatics_tools/download.py#L33)
- [`test_commands.py`](../tests/unit/test_commands.py#L80)

`write_transcripts` says it atomically writes all downloaded formats, but it stages and replaces
one destination at a time. An injected failure on the second `os.replace` leaves the first file in
place; the reproduction left `abc123.json` without `abc123.srt`. With `--overwrite`, a failure can
also leave one new file alongside one old file.

Each individual file write is atomic, but the pair is not a transaction. Existing tests cover a
fully successful pair and a collision before writing, not a mid-commit failure.

Recommended fix:

1. Write and flush all temporary files before changing any destination.
2. For overwrite, move existing destinations to backups, replace all outputs, and restore backups
   if any replacement fails.
3. Update the docstring if pair-level atomicity is intentionally not guaranteed, and add a failure
   injection test for the second replacement.

### CR-05 — P3: the default private workspace changes with the process working directory

Affected code:

- [`auth.py`](../src/speechmatics_tools/auth.py#L12)
- [`download.py`](../src/speechmatics_tools/download.py#L71)
- [`pyproject.toml` console commands](../pyproject.toml#L23)

`.local` is resolved relative to the current process directory. Running the installed
`speechmatics-start` command outside the repository was reproduced to fail with
`Cannot read Speechmatics credentials file: .local\\secrets\\speechmatics-api-key.json`.
Downloads have a second, duplicated workspace-resolution implementation, creating a future drift
risk.

The README's initial `cd` makes the documented example work, and users can supply `--workspace`,
so this is not a current release blocker. It does make installed console entry points less portable
than their packaging suggests.

Recommended fix:

1. Centralize all workspace resolution in one module and return an absolute path.
2. Require `SPEECHMATICS_WORKSPACE` for installed/global use, or add a small user configuration
   file that records the default workspace.
3. Add a subprocess test that invokes each installed console command from a different directory.

### CR-06 — P3: CI does not verify the built artifact or the documented full quality gate

Affected code:

- [`.github/workflows/ci.yml`](../.github/workflows/ci.yml#L19)
- [`test_entry_points.py`](../tests/integration/test_entry_points.py#L8)
- [`pyproject.toml` package data](../pyproject.toml#L31)

Tests import from `src` through pytest's `pythonpath`, and the entry-point test only constructs
parsers. CI does not build a wheel, install that wheel into a clean environment, verify the three
console executables, or confirm that the default JSON resource is present. It also omits
`git diff --check`, although `AGENTS.md` defines that as part of the quality gate.

The wheel was built manually during this review and currently contains
`speechmatics_tools/data/job-defaults.json`; the issue is regression detection, not a present
packaging failure.

Recommended fix:

1. Build both wheel and source distribution in CI.
2. Install the wheel into a clean environment, run the three `--help` commands, and load the
   packaged default config.
3. Add `git diff --check` and an assertion that no `.local/` path is tracked.

## Positive observations

- API keys are sent in the `Authorization` header rather than URLs.
- Region hosts are allowlisted instead of accepting an arbitrary endpoint that could receive the
  API key.
- Job IDs are validated before URL interpolation and output filename construction.
- The downloader fetches both remote payloads before beginning a `both` write, avoiding local
  changes when the second download itself fails.
- JSON transcripts are parsed before persistence, and existing outputs require explicit
  `--overwrite`.
- The real EU1 upload → poll → JSON/SRT download flow completed successfully with the requested
  Lithuanian enhanced preset.

## Validation performed

```text
ruff:       passed
mypy:      passed (11 source files)
pytest:     31 passed
compileall: passed
wheel:      built; data/job-defaults.json present
git status: clean before review output
```

No production code was modified as part of this review.

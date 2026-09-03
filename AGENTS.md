# Repository working rules

These instructions apply to the entire repository.

## Before changing code

1. Run `git status --short` and preserve any user changes.
2. Read `README.md` and the relevant file under `docs/`.
3. Verify changing Speechmatics API behavior against current official documentation. Do not
   guess endpoints, regions, request fields, output formats, or job states.

## Architecture boundaries

- `auth.py` is the only module that reads and validates API keys.
- `client.py` is the only module that makes Speechmatics HTTP requests.
- `data/job-defaults.json` contains the repository-wide default transcription preset.
- `start.py`, `poll.py`, and `download.py` own command-specific argument parsing and output.
- Files under `scripts/` remain thin executable wrappers; business logic belongs in `src/`.
- Authentication is always sent in the `Authorization` header, never in a URL or log.
- Keep a job on the region where it was created. The default is EU1, but every command must
  retain the explicit `--region` option.

## Secrets and local data

- Never commit `.local/`, real API keys, customer media, transcripts, or temporary API data.
- Committed examples must contain obvious placeholders only.
- Tests must use fake HTTP sessions and must never call the real Speechmatics API.
- Error messages must not include authorization headers or secret values.

## Quality and Git history

Before each commit run:

```powershell
python -m ruff check .
python -m mypy src scripts
python -m pytest -q
python -m compileall -q src scripts
git diff --check
```

Commit each completed logical change separately with a short imperative Conventional Commit
message. Update documentation and examples together with behavior changes.

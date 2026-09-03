# Batch transcription flow

The three public scripts share one authenticated `SpeechmaticsClient` and keep command-line
concerns separate from HTTP behavior.

```text
media file + JobConfig
        |
        v
POST /v2/jobs  --------------------> job id
                                          |
                                          v
                              GET /v2/jobs/{job_id}?wait=0
                                          |
                              running ----+---- done / rejected
                                                        |
                                                        v
                              GET /v2/jobs/{job_id}/transcript
                                  ?format=json-v2 or srt&wait=0
                                                        |
                                                        v
                                         atomic local file write
```

## Boundaries

- `auth.py` resolves `.local`, optional environment variables, and credential formats.
- `client.py` validates job IDs, media types, configuration, regional endpoints, response status,
  and transcript content.
- `start.py`, `poll.py`, and `download.py` translate command-line options into client calls and
  stable exit codes.
- `scripts/` contains only executable wrappers so the same behavior is available through the
  installed `speechmatics-*` console commands.

The API key is sent only in the `Authorization: Bearer ...` request header. The client never adds
it to a URL, response object, output JSON, or exception. Follow-up operations must use the same
region that accepted the original job.

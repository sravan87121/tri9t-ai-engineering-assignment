# Tri9T AI Engineering Internship — CT-200

FastAPI backend that extracts the two supplied manuals into immutable versioned trees, browses/searches their content, compares versions, saves named selections, and generates source-traceable QA ideas with queryable staleness.

## Quick start

Requires Python 3.12 and Tesseract with English language data for scanned pages (`sudo apt-get install tesseract-ocr` on Ubuntu). Native text extraction does not require Tesseract.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Windows: use `.venv\Scripts\activate` instead of `source`. Open http://127.0.0.1:8000/docs for interactive OpenAPI documentation. The default SQLite database is created under `runtime/`; it survives process restarts.

Environment variables are listed in `.env.example`. The app reads process environment variables; it does **not** automatically load `.env`. Export variables in your shell or configure them in your process runner.

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///runtime/ct200.db` | SQLite storage |
| `LLM_PROVIDER` | `mock` | `mock` or `openai-compatible` |
| `LLM_API_KEY` | unset | Required for live generation |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | Trusted provider base URL |
| `LLM_MODEL` | `gpt-4.1-mini` | Provider-supported model name |

**Mock mode is a deterministic fixture, not live AI output.** It produces three source-backed review templates so the full workflow runs without a paid key. For live QA ideas set `LLM_PROVIDER=openai-compatible`, an API key, and a model supported by your provider. Selected source text is sent to that provider. Never commit API keys.

## Reproduce the v1 → v2 workflow

```bash
curl -X POST http://127.0.0.1:8000/versions/v1 -F file=@data/ct200_manual.pdf
curl http://127.0.0.1:8000/versions/v1/sections
curl http://127.0.0.1:8000/nodes/v1:2.1.1.1
curl -X POST http://127.0.0.1:8000/selections -H 'Content-Type: application/json' -d '{"name":"Battery regression","version":"v1","node_ids":["v1:2.1.1.1"]}'
# Substitute the returned selection ID below.
curl -X POST http://127.0.0.1:8000/selections/SELECTION_ID/generate
curl -X POST http://127.0.0.1:8000/versions/v2 -F file=@data/ct200_manual_v2.pdf
curl 'http://127.0.0.1:8000/diff?from_version=v1&to_version=v2'
curl 'http://127.0.0.1:8000/generations?stale=true'
```

Or run `python -m scripts.demo` for an isolated in-process demonstration. It writes `docs/demo-results.json`, including actual source snapshots, three mock cases, and the complete diff. This script uses a temporary database and leaves your running server database untouched. It honors your LLM environment; use `LLM_PROVIDER=mock` for a free offline run.

## API reference

| Method | Path | Behavior |
|---|---|---|
| GET | `/health` | Liveness |
| POST | `/versions/{version}` | Import multipart PDF; optional `force_ocr=true`; 20 MiB limit |
| GET | `/versions` | Ordered imports, file hashes and warnings |
| GET | `/versions/{version}/sections?parent=root` | Immediate children in source order |
| GET | `/nodes/{node_id}` | Text, subtree text/hash, children, block provenance |
| GET | `/search?version=v1&q=battery` | Case-insensitive direct text/title search; limit/offset |
| GET | `/diff?from_version=v1&to_version=v2` | Added/removed/modified nodes and token-level unified diff |
| POST | `/selections` | Immutable named, version-pinned node selection |
| GET | `/selections/{id}` | Retrieve selection |
| POST | `/selections/{id}/generate` | Validate and store 3–5 QA ideas |
| GET | `/generations` | Filters: `selection_id`, `node_id`, `stale`, `against_version` |

Node IDs use `version:section`, e.g. `v1:4.2`; the document root is `v1:root`. Duplicate selection names return 409; repeated node IDs within a selection are deduplicated. Versions cannot be overwritten. Latest means latest successfully imported sequence, not lexical version ordering. An imported older manual becomes latest unless callers specify `against_version`.

## Verification

```bash
python -m pytest -q
python -m scripts.demo
```

12 tests pass in the development environment. Coverage includes the real PDFs, irregular headings, table-row extraction, cross-page continuation, a raster-only OCR fixture, v1/v2 integration, invalid input, duplicate selections, retry/exhaustion, false citations, provider request contract, absent credentials and persistence. GitHub Actions is configured but has not been run remotely. A dependency deprecation warning recommends a future TestClient transport migration; tests currently pass with the pinned versions.

## Results and limitations

- v1 has 28 nodes including root; v2 has 29. Both have eight top-level sections.
- Changed direct sections: `2.1.1.1`, `3.2`, `4.2`, `4.3`; new section: `5.3`. Parent subtree changes are also reported.
- Source evidence and model attempts are stored as JSON documents in SQLite via SQLAlchemy; no separate MongoDB service is required.
- Live provider execution is **not verified**: no real credential was available. The adapter is tested using HTTP simulation. Mock cases are review templates, not evidence of live LLM quality.
- Native table rows preserve text, individual spans and bounding boxes. Arbitrary merged-cell reconstruction, OCR table reconstruction, and automatic figure-to-caption association are incomplete.
- Section matching uses section numbers. Renumbering/moves are not semantically reconciled; they can appear as additions/removals or misleading same-number edits. Human review is required.
- JSON validation and evidence checks do not prove every expected result is semantically entailed. Human review remains necessary.
- Local assignment backend: no authentication, rate limiting, background OCR queue or production deployment. Do not expose it publicly as-is.

See [Approach Document](docs/Approach_Document.pdf), [editable approach](docs/Approach_Document.md), and [demo evidence](docs/demo-results.json).

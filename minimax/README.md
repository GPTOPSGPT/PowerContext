# MiniMax SDD context module (work in progress)

The target task is to reject negative invoice quantities while preserving zero and positive behavior. `sample/spec.md`, `sample/pricing.py`, and `sample/test_pricing.py` are imported into seekdb. `sdd_context.py context` reads the engineering sources from seekdb and searches saved task state in PowerContext.

Required services: seekdb (MySQL protocol) and PowerContext HTTP API. Set `SEEKDB_HOST`, `SEEKDB_PORT`, `SEEKDB_USER`, `SEEKDB_PASSWORD`, `SEEKDB_DATABASE`, `POWERCONTEXT_URL`, and `POWERCONTEXT_SCOPE_ID`; set `POWERCONTEXT_TOKEN` if authentication is enabled. The examples below use placeholders; never commit credentials.

Start seekdb and PowerContext as described by their respective distributions. On a clean installation, create the database and an isolated Scope before running the module:

```sh
mysql -h "$SEEKDB_HOST" -P "$SEEKDB_PORT" -u "$SEEKDB_USER" -p -e 'CREATE DATABASE IF NOT EXISTS sdd_context'
export SEEKDB_DATABASE=sdd_context
curl -fsS -X POST "$POWERCONTEXT_URL/v1/scopes" -H 'Content-Type: application/json' \
  -d '{"title":"MiniMax SDD validation","summary":"Isolated invoice task","idempotency_key":"minimax-sdd-validation-v1"}'
# Set POWERCONTEXT_SCOPE_ID to the returned scope_id. The Scope is not a directory name.
```

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r minimax/requirements.txt
python minimax/sdd_context.py import
python minimax/sdd_context.py context 'reject negative invoice quantity; preserve zero and positive totals'
python minimax/sdd_context.py remember 'Target test failed before fix; negative quantity returned a negative total.'
python minimax/sdd_context.py context 'negative invoice quantity target test'
python -m unittest discover -s minimax/sample -p 'test_*.py' -v
python -m unittest discover -s minimax -p 'test_sdd_context.py' -v
```

Re-import after editing `sample/spec.md`; the returned source content and SHA-256 must change. Restart the CLI between `remember` and the second `context` call to demonstrate persisted PowerContext state. The sample code patch was made with MiniMax-M2.7; exact request, sanitized response, before/after snapshots, diff, and test logs are under `evidence/`.

`context` returns `assistant_context`, the exact text to supply to the coding assistant. It includes source paths, content and hashes from seekdb plus retrieved PowerContext progress. `saved_progress` exposes the retrieved state separately. `database_query` identifies the SQL used. See `EVIDENCE.md` and `TECHNICAL_NOTE.md`. To reset the sample, delete the isolated `sdd_context` database and the isolated PowerContext Scope or use a new `POWERCONTEXT_HOME`/Scope; preserve the pre-change sample code and test for the before/after run.

To reproduce a bounded MiniMax coding request from the module output, save `context` JSON to a file and run `python minimax/model_patch.py --context-json /path/to/context.json --output-dir /path/to/evidence`. This defaults to a dry run and writes `request.json` without any credential. With owner authorization, use `--send --key-file /path/outside/repo/raw-token.txt`. The key file must contain one raw token. The script never commits or prints it, and it writes the model response separately for review before applying any patch.

# MiniMax SDD context module

The target task is to reject negative invoice quantities while preserving zero and positive behavior. `sample/spec.md`, `sample/pricing.py`, and `sample/test_pricing.py` are imported into seekdb. `sdd_context.py context` reads the engineering sources from seekdb and searches saved task state in PowerContext.

Required services: seekdb (MySQL protocol) and PowerContext HTTP API. Set `SEEKDB_HOST`, `SEEKDB_PORT`, `SEEKDB_USER`, `SEEKDB_PASSWORD`, `SEEKDB_DATABASE`, `POWERCONTEXT_URL`, and `POWERCONTEXT_SCOPE_ID`; set `POWERCONTEXT_TOKEN` if authentication is enabled. The examples below use placeholders; never commit credentials.

On a clean Linux host with Docker, Python 3.12, and a MySQL client, run these in separate terminals. The image below is the one used for validation; a compatible seekdb installation is also acceptable. Use a free local port if 2881 or 18766 is occupied.

Terminal A:

```sh
docker run -d --name sdd-seekdb -p 127.0.0.1:2881:2881 docker.1ms.run/oceanbase/seekdb:latest
python3.12 -m venv .sdd-venv
. .sdd-venv/bin/activate
pip install -r minimax/requirements.txt 'powercontext[cli,server]==1.2.0'
export POWERCONTEXT_HOME=/tmp/minimax-sdd-powercontext
powercontext server run --host 127.0.0.1 --port 18766 --no-env-file
```

Terminal B, after both services are ready:

```sh
export SEEKDB_HOST=127.0.0.1 SEEKDB_PORT=2881 SEEKDB_USER=root SEEKDB_PASSWORD=''
export POWERCONTEXT_URL=http://127.0.0.1:18766
mysql -h "$SEEKDB_HOST" -P "$SEEKDB_PORT" -u "$SEEKDB_USER" -e 'CREATE DATABASE IF NOT EXISTS sdd_context'
export SEEKDB_DATABASE=sdd_context
curl -fsS -X POST "$POWERCONTEXT_URL/v1/scopes" -H 'Content-Type: application/json' \
  -d '{"title":"MiniMax SDD validation","summary":"Isolated invoice task","idempotency_key":"minimax-sdd-validation-v1"}'
# Export POWERCONTEXT_SCOPE_ID from the returned scope_id. It is not a directory name.
```

```sh
. .sdd-venv/bin/activate
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

To replay the unchanged tests against both committed snapshots without changing the checkout:

```sh
tmp=$(mktemp -d)
cp minimax/sample/test_pricing.py "$tmp/test_pricing.py"
cp minimax/evidence/pricing.before.py "$tmp/pricing.py"
python -m unittest discover -s "$tmp" -p 'test_*.py' -v  # expected exit 1: target failure
cp minimax/evidence/pricing.after.py "$tmp/pricing.py"
python -m unittest discover -s "$tmp" -p 'test_*.py' -v  # expected exit 0: all pass
```

See `evidence/before_tests.log` and `evidence/after_tests.log` for the observed commands and exit codes.

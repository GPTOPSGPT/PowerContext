# MiniMax SDD context module (work in progress)

The target task is to reject negative invoice quantities while preserving zero and positive behavior. `sample/spec.md`, `sample/pricing.py`, and `sample/test_pricing.py` are imported into seekdb. `sdd_context.py context` reads the engineering sources from seekdb and searches saved task state in PowerContext.

Required services: seekdb (MySQL protocol) and PowerContext HTTP API. Set `SEEKDB_HOST`, `SEEKDB_PORT`, `SEEKDB_USER`, `SEEKDB_PASSWORD`, `SEEKDB_DATABASE`, `POWERCONTEXT_URL`, and an existing `POWERCONTEXT_SCOPE_ID`; set `POWERCONTEXT_TOKEN` if authentication is enabled. Create the seekdb database `sdd_context` before import. `POWERCONTEXT_SCOPE_ID` must identify a user-established Scope for this task.

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r minimax/requirements.txt
python minimax/sdd_context.py import
python minimax/sdd_context.py context 'reject negative invoice quantity; preserve zero and positive totals'
python minimax/sdd_context.py remember 'Target test failed before fix; negative quantity returned a negative total.'
python minimax/sdd_context.py context 'negative invoice quantity target test'
python -m unittest discover -s minimax/sample -p 'test_*.py' -v
```

Re-import after editing `sample/spec.md`; the returned source content and SHA-256 must change. Restart the CLI between `remember` and the second `context` call to demonstrate persisted PowerContext state. The code patch must be made with MiniMax and recorded with exact input context, output diff, and before/after test logs. No model call or code patch has been claimed yet.

# MiniMax SDD verification record

## Current status

The integration below verifies the context module, seekdb, PowerContext, and an authorized MiniMax-assisted patch. It does not claim a platform score until the fixed submission is graded.

## Environment and source data

- Date: 2026-11-07 Beijing time.
- Isolated host: `trip` Linux ECS. Database: `sdd_context` inside seekdb `gptops-prelim-seekdb` (server version `5.7.25-OceanBase seekdb-v1.4.0.0`); PowerContext home: `/tmp/gptops-sdd-pc-home`, bound to loopback port 18766; Python environment: `/tmp/gptops-sdd-venv` with PyMySQL 1.1.1 and PowerContext 1.2.0.
- Source commit: `d1c57d6b`. Source files imported: `sample/spec.md`, `sample/pricing.py`, `sample/test_pricing.py`.
- `python minimax/sdd_context.py import` exited 0 and returned all three paths.
- `SELECT path,kind,LEFT(sha256,12),LENGTH(content) FROM sdd_sources ORDER BY kind,path` exited 0 and returned:

```text
sample/pricing.py       code  f954405ff428  162
sample/spec.md          spec  0028688a35e2  301
sample/test_pricing.py  test  ee899a63e8f4  484
```

## Context and restart

1. Created an isolated PowerContext Scope with `POST /v1/scopes`; the response returned `scope_id=scp_2crr7ycq5dsr06y4zh0762j6cg`.
2. Ran `sdd_context.py context 'negative invoice quantity target test'`; exit 0; `sources=3`, `saved_progress=0`, and `assistant_context` contained all three source paths.
3. Ran `sdd_context.py remember 'Target test failed before fix: negative quantity returned a negative total; preserve zero and positive behavior.'`; exit 0; response contained `entry` and `memory`.
4. Stopped only this isolated PowerContext process and restarted it with the same `POWERCONTEXT_HOME`.
5. Ran the same `context` command in a new Python process; exit 0; `sources=3`, `saved_progress=1`, and `assistant_context` contained the saved target-test result.

The full context output was stored on the isolated host as `/tmp/gptops-sdd-context-before.json` and `/tmp/gptops-sdd-context-after.json`. Those runtime files are not required by the submitted source.

To test specification evolution, appended a temporary marker to the isolated remote copy of `sample/spec.md`, ran `import` and `context` again, and observed the marker in the returned specification with a new hash prefix `6e25f2c94797` (exit 0). Restored the original sample file, re-imported it, and retained the original source in the submitted worktree. This proves the current seekdb row, rather than a hard-coded local specification, supplies the context.

`model_patch.py` dry run on the post-restart context exited 0 and printed `dry_run=true; no MiniMax request sent`; the generated request SHA-256 was `b298b547f45b1765cdc1a196416b749973c7b626580556c87c65a3e1d0d30b13`. It contains only the three sample sources and the saved task observation.

## MiniMax-assisted modification

The owner authorized sending only the isolated sample specification, code, and tests. The first request used the retired `MiniMax-Text-01` model and returned provider code 2069; it did not generate code. The second request used the active `MiniMax-M2.7` model, succeeded with provider status 0, and used 764 total tokens (643 prompt, 121 completion). No API key was put into the request artifact or logs. The successful request SHA-256 was `1bf4bc0d13cf3a8f0b9feb295e615f4562c3d980264f98ea74054ac91fe8c361`; response SHA-256 was `9365683979039f33044025eec45251a1ab7a68f25dcd48a531f4705368eabc44` before sanitization. Exact prompt and a sanitized model reply are in `evidence/model_request.json` and `evidence/model_response.json`.

MiniMax returned a complete replacement for `sample/pricing.py`. Its only behavioral change is a negative-quantity check that raises `ValueError`. The exact before/after source and diff are in `evidence/pricing.before.py`, `pricing.after.py`, and `pricing.diff`. The unchanged target and regression tests are in `sample/test_pricing.py`.

## Before-patch tests

At pre-patch commit `58f2f6a5`, `/Users/chase/codex/KB/.venv/bin/python -m unittest discover -s minimax/sample -p 'test_*.py' -v` exited 1: `test_negative_quantity_rejected` failed because `ValueError` was not raised; the positive and zero regression tests passed. The same command after applying the MiniMax reply exited 0 with all three tests passing. The unchanged context-module test command `python -m unittest discover -s minimax -p 'test_sdd_context.py' -v` exited 0 with one test passing. Full outputs and exit codes are in `evidence/before_tests.log` and `evidence/after_tests.log`.

After the patch, re-importing `sample/pricing.py` into seekdb and writing the successful validation observation to PowerContext exited 0. A new context run returned the updated code (`if quantity < 0:`) and two saved progress hits; both the old failure and new success are visible, preserving task history.

`evidence/integration.log` contains raw commands, service versions, SQL rows, exit codes, a fresh PowerContext write, an actual process restart, and post-restart context outputs. The task-specific post-restart query returned the saved marker in `assistant_context` and the MiniMax patch from seekdb. A broader negative-quantity query did not retrieve the marker because memory search ranks by relevance; that result is retained in the log rather than concealed.

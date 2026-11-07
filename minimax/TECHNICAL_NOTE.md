# One-page technical note

`sdd_context.py` is a small CLI for one change: reject a negative invoice quantity while preserving positive and zero totals. Its `import` command writes current specification, code, and test content with SHA-256 hashes into a dedicated seekdb table. `context TASK` queries that table each time and assembles the required sources and citations into `assistant_context`. Re-importing a changed specification updates the row, so the next context uses the new content.

PowerContext stores task progress under an isolated Scope. `remember TEXT` writes a decision or validation observation; `context TASK` searches the Scope and includes returned text in `assistant_context`. This allows a new process to continue from saved progress. The module does not restore an entire agent session.

MiniMax-M2.7 performed the business code edit after the owner authorized sending only this isolated sample. The assistant input was the module's `assistant_context`; the target was only `sample/pricing.py`. The model added a negative-quantity guard. The unchanged target test failed before that patch and all target and regression tests passed afterward. The exact prompt, sanitized reply, source snapshots, diff, and test logs are committed under `evidence/`.

The validation uses PyMySQL 1.1.1 over seekdb's MySQL protocol and PowerContext 1.2.0 HTTP endpoints. It requires no production data. The sample's small size means all three source kinds are included; ranking within a kind is deterministic but no relevance threshold is applied. The caller must create a database and Scope and supply service locations. No credentials are stored in this repository.

# One-page technical note

`sdd_context.py` is a small CLI for one change: reject a negative invoice quantity while preserving positive and zero totals. Its `import` command writes current specification, code, and test content with SHA-256 hashes into a dedicated seekdb table. `context TASK` queries that table each time and assembles the required sources and citations into `assistant_context`. Re-importing a changed specification updates the row, so the next context uses the new content.

PowerContext stores task progress under an isolated Scope. `remember TEXT` writes a decision or validation observation; `context TASK` searches the Scope and includes returned text in `assistant_context`. This allows a new process to continue from saved progress. The module does not restore an entire agent session.

MiniMax is reserved for the business code edit. The assistant input is the module's `assistant_context`; the target is only `sample/pricing.py`. The unchanged target and regression tests define success. No model call or code patch is claimed until an authorized MiniMax request and the corresponding prompt, response, diff, and test logs are recorded.

The validation uses PyMySQL 1.1.1 over seekdb's MySQL protocol and PowerContext 1.2.0 HTTP endpoints. It requires no production data. The sample's small size means all three source kinds are included; ranking within a kind is deterministic but no relevance threshold is applied. The caller must create a database and Scope and supply service locations. No credentials are stored in this repository.

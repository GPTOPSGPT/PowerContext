"""Prepare a bounded MiniMax coding request; send only with explicit --send.

The API key file must contain only the raw token and must live outside this repo.
No credential is written to the request or response artifacts.
"""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
API = "https://api.minimax.chat/v1/text/chatcompletion_v2"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--context-json", type=Path, required=True,
                   help="Output of sdd_context.py context, produced from seekdb and PowerContext")
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--model", default="MiniMax-M2.7")
    p.add_argument("--send", action="store_true", help="Actually call MiniMax; requires user authorization")
    p.add_argument("--key-file", type=Path, help="Raw token in a file outside this repository")
    args = p.parse_args()

    context = json.loads(args.context_json.read_text(encoding="utf-8"))
    paths = {row["path"] for row in context["sources"]}
    expected = {"sample/spec.md", "sample/pricing.py", "sample/test_pricing.py"}
    if paths != expected:
        p.error("context must contain exactly the three isolated sample sources")
    prompt = context["assistant_context"] + "\n\n" + (
        "Modify only sample/pricing.py so negative quantities raise ValueError. "
        "Preserve zero and positive behavior, and do not change the tests. "
        "Return the complete replacement Python source for sample/pricing.py, "
        "inside one Python code fence, with no other files."
    )
    payload = {"model": args.model, "stream": False, "messages": [
        {"role": "system", "content": "You are a careful software development assistant. Follow the current specification and tests supplied by the user."},
        {"role": "user", "content": prompt},
    ]}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    request_bytes = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    (args.output_dir / "request.json").write_bytes(request_bytes)
    print("request_sha256=" + hashlib.sha256(request_bytes).hexdigest())
    if not args.send:
        print("dry_run=true; no MiniMax request sent")
        return
    if args.key_file is None:
        p.error("--send requires --key-file")
    key_path = args.key_file.resolve()
    if ROOT.parent == key_path or ROOT.parent in key_path.parents:
        p.error("key file must be outside the repository")
    key = key_path.read_text(encoding="utf-8").strip()
    if not key or any(ch.isspace() for ch in key):
        p.error("key file must contain one raw token only")
    req = Request(API, data=request_bytes,
                  headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
                  method="POST")
    try:
        with urlopen(req, timeout=60) as response:
            body = response.read()
            status = response.status
    except HTTPError as exc:
        # Do not echo request headers or potentially sensitive response bodies.
        raise SystemExit(f"MiniMax HTTP {exc.code}; no response artifact written") from None
    result = json.loads(body)
    provider_status = result.get("base_resp", {}).get("status_code")
    if provider_status != 0:
        raise SystemExit(f"MiniMax provider status {provider_status}; no successful response artifact written")
    (args.output_dir / "response.json").write_bytes(body)
    print(f"minimax_http_status={status}; response_sha256={hashlib.sha256(body).hexdigest()}")


if __name__ == "__main__":
    main()

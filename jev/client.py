"""Jev 呼叫入口：本機走 brain 的 jev_client（Keychain＋強制記帳），CI 走環境變數＋直推 Jev Ledger。

兩條路都會記帳（ai4biz-tw board R8／brain#129）：每次呼叫、含失敗，都寫一列進共用 Jev Ledger。
CI 環境變數（org secret，不進 repo）：TYPESAFE_API_KEY、JEV_LEDGER_URL、JEV_LEDGER_SECRET；JEV_CALLER 選填。
"""
import datetime, json, os, sys, time, urllib.error, urllib.request

API = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-latest"
PRICE_IN_PER_TOKEN = 0.042 / 1_000_000  # US$0.042 / M input tokens；output 免費（2026-09-15 官方）

try:  # 本機：Daniel 的唯一入口，Keychain 取 key、本機 ledger＋Sheet 佇列
    sys.path.insert(0, os.path.expanduser("~/brain/05_operations/mail/jev"))
    from jev_client import evaluate as _local_evaluate  # noqa: E402
except ImportError:
    _local_evaluate = None


def _post(url, payload, headers=None, timeout=60):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _ledger(res, *, repo, purpose, questions, latency_ms, status="ok", note=""):
    u = (res or {}).get("usage", {})
    tin, tout = int(u.get("input_tokens", 0)), int(u.get("output_tokens", 0))
    row = [datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           os.environ.get("JEV_CALLER") or f"CI ({os.environ.get('GITHUB_ACTOR', 'unknown')})",
           repo, purpose, (res or {}).get("model", MODEL), len(questions), tin, tout,
           round(tin * PRICE_IN_PER_TOKEN, 10), latency_ms, status, note]
    url, secret = os.environ.get("JEV_LEDGER_URL"), os.environ.get("JEV_LEDGER_SECRET")
    if not (url and secret):
        raise SystemExit("缺 JEV_LEDGER_URL／JEV_LEDGER_SECRET：Jev 呼叫一定要記帳，不准略過")
    try:
        if not _post(url, {"secret": secret, "rows": [row]}, timeout=20).get("ok"):
            raise RuntimeError("webhook 回 ok=false")
    except Exception as e:  # noqa: BLE001 — 記帳失敗留給 CI artifact 補送，不吞掉
        with open(os.environ.get("JEV_QUEUE", "jev-ledger-queue.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"[jev] ⚠️ Sheet 記帳失敗，已存 jev-ledger-queue.jsonl：{e}", file=sys.stderr)


def evaluate(state, questions, *, tag, repo, note="", timeout=60):
    if _local_evaluate and not os.environ.get("CI"):
        return _local_evaluate(state, questions, tag=tag, repo=repo, note=note, timeout=timeout)
    key = os.environ.get("TYPESAFE_API_KEY")
    if not key:
        raise SystemExit("缺 TYPESAFE_API_KEY：閘門失敗即擋（fail closed）")
    t0 = time.monotonic()
    try:
        res = _post(API, {"model": MODEL, "state": state, "questions": questions},
                    {"Authorization": f"Bearer {key}"}, timeout=timeout)
    except Exception as e:
        _ledger(None, repo=repo, purpose=tag, questions=questions, status="error",
                latency_ms=int((time.monotonic() - t0) * 1000), note=f"{note} {str(e)[:120]}".strip())
        raise
    _ledger(res, repo=repo, purpose=tag, questions=questions, note=note,
            latency_ms=int((time.monotonic() - t0) * 1000))
    return res

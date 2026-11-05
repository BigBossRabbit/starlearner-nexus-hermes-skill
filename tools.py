"""tools.py — the three registered tool handlers (spec B.3).

The contract (dev guide, "Common mistakes"): every handler returns a JSON
string ALWAYS and NEVER raises (anything the driver throws is converted
into a clean error JSON here), takes ``**kwargs`` for forward
compatibility, and the schema's ``description`` is how the model decides
when to call it.

No check_fn mode gating (B.2.3): ``requires_env`` install-prompts for
the token, and the HANDLERS guard — a missing/empty token is
starlearner_sync's clean ``token_not_set`` error (R12), while the
read-only status/review surfaces work regardless (status reports
``token: "not set"``). Lazy everything: the driver (harvest.py),
github_fetch and the engine are imported inside the handlers.
"""
from __future__ import annotations

import json

from . import runtime, schemas


def _tool_error(exc: BaseException, **extra) -> str:
    """The never-raise error JSON: exception class + message, no
    tracebacks to the model (B.3.1)."""
    return json.dumps({"ok": False,
                       "error": f"{type(exc).__name__}: {exc}", **extra},
                      ensure_ascii=False)


def sync(args: dict, **kwargs) -> str:
    """starlearner_sync (the product)."""
    try:
        from . import harvest as _harvest
        return json.dumps(_harvest.run_sync(args or {}),
                          ensure_ascii=False)
    except BaseException as exc:  # noqa: BLE001 — never raise
        return _tool_error(exc)


def status(args: dict, **kwargs) -> str:
    """starlearner_status (read-only)."""
    try:
        from . import harvest as _harvest
        from . import skills_out
        state = _harvest._read_run_state()
        result = {"ok": True,
                  "last_run": state.get("last_run"),
                  "sync_running": _harvest.harvest_running(),
                  "enrich": runtime.setting("enrich", "llm"),
                  "llm_max_items": runtime.setting("llm_max_items", 50),
                  "generate_limit": runtime.setting("generate_limit", 5),
                  "max_pages": runtime.setting("max_pages", 30),
                  "register_generated_skills":
                      runtime.setting("register_generated_skills", True)}
        # the token state (presence ONLY — never a value):
        try:
            from . import github_fetch
            result["token"] = ("set" if github_fetch.has_token()
                               else "not set")
        except Exception as exc:  # a status read must never fail
            result["token"] = f"unknown ({type(exc).__name__})"
        try:
            result["skills"] = skills_out.status()
        except Exception as exc:  # a status read must never fail
            result["skills"] = {"error": f"{type(exc).__name__}"}
        # the ledger + last assessment (the engine's data files)
        try:
            from . import _engine
            _engine.load()
            data = skills_out.data_dir()
            result["ledger"] = _engine.ledger.report(
                _engine.ledger.load_ledger(data / "ledger.json"))
        except Exception as exc:
            result["ledger"] = {"error": f"{type(exc).__name__}"}
        try:
            import json as _json
            from pathlib import Path as _Path
            opp = _Path(skills_out.data_dir()) / "opportunities.json"
            if opp.is_file():
                result["last_assessment"] = (_json.loads(
                    opp.read_text(encoding="utf-8")) or {}).get("counts")
        except Exception:
            pass
        return json.dumps(result, ensure_ascii=False, default=str)
    except BaseException as exc:  # noqa: BLE001
        return _tool_error(exc)


def review(args: dict, **kwargs) -> str:
    """starlearner_review (read-only)."""
    try:
        from . import skills_out
        args = args or {}
        since = args.get("since")
        category = args.get("category")
        opportunities_only = bool(args.get("opportunities_only"))
        include_skill_md = bool(args.get("include_skill_md"))
        last_run = None
        if not since:
            from . import harvest as _harvest
            last_run = (_harvest._read_run_state()
                        .get("last_run") or {}).get("ts")
        try:
            out = skills_out.review_rows(
                since=since or last_run, category=category,
                opportunities_only=opportunities_only,
                include_skill_md=include_skill_md)
        except Exception as exc:  # a read surface never fails (no hermes /
            # an unavailable store ⇒ the empty table, with the reason)
            out = {"items": [],
                   "counts": {"total": 0, "integrated": 0,
                              "opportunities": 0, "llm_flagged": 0},
                   "error": f"review store unavailable "
                            f"({type(exc).__name__})"}
        out["ok"] = True
        out["filters"] = {"since": since or last_run, "category": category,
                          "opportunities_only": opportunities_only,
                          "include_skill_md": include_skill_md}
        return json.dumps(out, ensure_ascii=False, default=str)
    except BaseException as exc:  # noqa: BLE001
        return _tool_error(exc)


HANDLERS = {"starlearner_sync": sync, "starlearner_status": status,
            "starlearner_review": review}

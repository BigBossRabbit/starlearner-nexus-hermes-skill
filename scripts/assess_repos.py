#!/usr/bin/env python3
"""assess_repos.py — two-track assessment for NEW repositories.

For each NEW item (already filtered by the ledger), produce a deterministic
verdict on two axes:

  Track A — own-makeup integration: is this worth turning into a loadable
            Hermes skill for our own stack? (keyword + star-rank heuristic)
  Track B — business opportunity:   is this a candidate to package for a
            client deliverable? (named client domain + one-line rationale)

No paid API, no LLM: pure rules, mirroring categorize_repos.py. Output is
data/opportunities.json (gitignored) plus a compact per-item verdict list.

Usage:
  python3 assess_repos.py <new_repos.json> <opportunities.json>
"""
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"

# Client-facing domains we can actually sell / build for (OKIN Ent).
# Each maps to a keyword set; a hit flags a business opportunity.
CLIENT_DOMAINS = {
    "bitcoin-lightning": ["bitcoin", "btc", "lightning", "lnd", "satoshi",
                          "wallet", "invoice", "payment", "node", "onchain"],
    "ai-integration": ["ai", "llm", "gpt", "agent", "automation", "rag",
                       "chatbot", "copilot", "workflow", "assistant"],
    "ecommerce": ["ecommerce", "e-commerce", "shop", "store", "cart", "pos",
                  "inventory", "erp", "crm", "order", "checkout"],
    "logistics": ["logistics", "fleet", "routing", "delivery", "warehouse",
                  "supply-chain", "inventory", "tracking", "dispatch"],
    "compliance": ["compliance", "kyc", "aml", "regulatory", "audit", "gdpr",
                   "popia", "fica", "licence", "reporting"],
    "data-analytics": ["analytics", "dashboard", "bi", "reporting", "etl",
                       "visualization", "insights", "metrics"],
}

# Own-makeup integration: repos we'd genuinely want as skills in our stack.
# High-signal keywords that indicate a reusable, tool-like repo.
INTEGRATION_KEYWORDS = [
    "cli", "sdk", "api", "library", "framework", "tool", "sdk", "sdk",
    "automation", "agent", "workflow", "pipeline", "integration", "bot",
    "scraper", "crawler", "parser", "scheduler", "notifier", "dashboard",
]


def _text(repo: dict) -> str:
    parts = [
        repo.get("name", ""),
        repo.get("description", "") or "",
        " ".join(repo.get("topics", []) or []),
    ]
    return " ".join(parts).lower()


def _has_keyword(text: str, keyword: str) -> bool:
    """Word-boundary match for single words, substring for multi-word phrases."""
    import re
    kw = keyword.lower().strip()
    if not kw:
        return False
    if " " in kw:
        return kw in text
    return re.search(r"\b" + re.escape(kw) + r"\b", text) is not None


def assess_integration(repo: dict) -> bool:
    """Track A: worth integrating into our own makeup?"""
    text = _text(repo)
    if any(_has_keyword(text, kw) for kw in INTEGRATION_KEYWORDS):
        return True
    # High-star repos are usually worth a skill regardless of keywords.
    return (repo.get("stargazers_count") or 0) >= 1000


def assess_opportunity(repo: dict) -> tuple:
    """Track B: business opportunity. Returns (domain, rationale) or (None, None)."""
    text = _text(repo)
    for domain, keywords in CLIENT_DOMAINS.items():
        for kw in keywords:
            if _has_keyword(text, kw):
                return domain, f"matches client domain '{domain}' (keyword '{kw}')"
    return None, None


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python3 assess_repos.py <new_repos.json> <opportunities.json>")
        return 1

    input_file, output_file = sys.argv[1], sys.argv[2]
    with open(input_file) as f:
        repos = json.load(f)

    opportunities = []
    integrated = []
    for repo in repos:
        name = repo.get("full_name") or repo.get("name") or "unknown"
        url = repo.get("html_url") or ""
        stars = repo.get("stargazers_count") or 0

        integ = assess_integration(repo)
        domain, rationale = assess_opportunity(repo)

        if integ:
            integrated.append({"name": name, "url": url, "stars": stars})

        if domain:
            opportunities.append({
                "name": name,
                "url": url,
                "stars": stars,
                "domain": domain,
                "rationale": rationale,
            })

    result = {
        "generated_at": __import__("datetime").datetime.now().isoformat(),
        "counts": {
            "assessed": len(repos),
            "integrated": len(integrated),
            "opportunities": len(opportunities),
        },
        "integrated": integrated,
        "opportunities": opportunities,
    }

    out = Path(output_file)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(result, f, indent=2)

    print(f"[assess] assessed {len(repos)} new items")
    print(f"[assess] {len(integrated)} worth integrating into own makeup")
    print(f"[assess] {len(opportunities)} business opportunities")
    for o in opportunities:
        print(f"  OPPORTUNITY: {o['name']} -> {o['domain']} ({o['rationale']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

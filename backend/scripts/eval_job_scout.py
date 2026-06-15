"""Eval harness for JobScoutAgent scoring quality.

Runs the production scoring pipeline (`JobScoutAgent._score_candidates`) against
the labeled (persona × job) sets in `backend/evals/personas/*.yaml` and reports
precision@5, precision@10, recall@10, NDCG@10, false-positive rate, and
false-negative rate.

Usage:
    python -m scripts.eval_job_scout --persona junior_cs_umich
    python -m scripts.eval_job_scout --all
    python -m scripts.eval_job_scout --all --json

Requires `ANTHROPIC_API_KEY` in env. Each run hits the live LLM — scoring runs
on claude-sonnet-4-6 (same model production uses), so budget accordingly.

Promotion gate: a scoring change ships only if precision@5 doesn't regress
on this set, or the regression is justified in `backend/scripts/eval_log.md`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import yaml

# Make `app.*` importable when invoked from backend/ as `python -m scripts.eval_job_scout`
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agents.job_scout import JobScoutAgent  # noqa: E402


# A label >= REL_THRESHOLD counts as "relevant" for precision/recall.
REL_THRESHOLD = 2


def load_persona(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_prefs(data: dict) -> SimpleNamespace:
    """Build a duck-typed UserPreferences-like object from a persona YAML."""
    p = data.get("preferences", {})
    return SimpleNamespace(
        target_roles=p.get("target_roles", []),
        target_companies=p.get("target_companies", []),
        target_locations=p.get("target_locations", []),
        excluded_companies=p.get("excluded_companies", []),
        min_salary=p.get("min_salary"),
    )


def build_context(data: dict) -> dict:
    c = data.get("context") or {}
    return {
        "skills": c.get("skills", []),
        "experience_roles": c.get("experience_roles", []),
        "networked_companies": c.get("networked_companies") or {},
    }


def build_candidates(data: dict) -> list[dict]:
    """Convert persona job entries to the dict shape `_score_candidates` expects."""
    return [
        {
            "external_id": job["id"],
            "source": "eval",
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "location": job.get("location", ""),
            "description": job.get("description", ""),
            "url": job.get("url", ""),
        }
        for job in data.get("jobs", [])
    ]


def labels_by_id(data: dict) -> dict[str, int]:
    return {job["id"]: int(job.get("label", 0)) for job in data.get("jobs", [])}


def precision_at_k(ranked_labels: list[int], k: int) -> float | None:
    if not ranked_labels:
        return None
    k = min(k, len(ranked_labels))
    return sum(1 for lab in ranked_labels[:k] if lab >= REL_THRESHOLD) / k


def recall_at_k(ranked_labels: list[int], all_labels: list[int], k: int) -> float | None:
    total_relevant = sum(1 for lab in all_labels if lab >= REL_THRESHOLD)
    if total_relevant == 0:
        return None
    k = min(k, len(ranked_labels))
    surfaced = sum(1 for lab in ranked_labels[:k] if lab >= REL_THRESHOLD)
    return surfaced / total_relevant


def ndcg_at_k(ranked_labels: list[int], k: int) -> float | None:
    """Normalized Discounted Cumulative Gain."""
    if not ranked_labels:
        return None
    k = min(k, len(ranked_labels))
    dcg = sum((2**lab - 1) / math.log2(i + 2) for i, lab in enumerate(ranked_labels[:k]))
    ideal = sorted(ranked_labels, reverse=True)[:k]
    idcg = sum((2**lab - 1) / math.log2(i + 2) for i, lab in enumerate(ideal))
    if idcg == 0:
        return None
    return dcg / idcg


async def score_persona(data: dict) -> dict:
    """Score every job in a persona file against the production pipeline.

    Items that production filters out (final_score < 0.65) are treated as
    score 0.0 in the metrics — that correctly counts them as not-surfaced
    for recall@K and as false-negatives when label = 3.
    """
    prefs = build_prefs(data)
    ctx = build_context(data)
    candidates = build_candidates(data)
    label_map = labels_by_id(data)

    exp_level = data.get("preferences", {}).get("experience_level", "mid")
    emp_types = data.get("preferences", {}).get("employment_types", ["full_time"])

    # `_score_candidates` only touches `self.complete` (LLM) and `self.client` —
    # neither needs a real DB session. Pass db=None.
    agent = JobScoutAgent(db=None, user_id=uuid.uuid4())  # type: ignore[arg-type]
    scored = await agent._score_candidates(
        candidates=candidates,
        prefs=prefs,
        ctx=ctx,
        experience_level=exp_level,
        employment_types=emp_types,
    )

    scored_by_id = {item["external_id"]: item["match_score"] for item in scored}

    # Rank every labeled job by its production score (0 if filtered out).
    candidate_scores = sorted(
        (
            (job_id, scored_by_id.get(job_id, 0.0), label_map[job_id])
            for job_id in label_map
        ),
        key=lambda x: x[1],
        reverse=True,
    )
    ranked_labels = [lab for _, _, lab in candidate_scores]
    all_labels = list(label_map.values())

    # FP rate among high-confidence scores: scored >= 0.85 but labeled 0–1.
    high_score = [t for t in candidate_scores if t[1] >= 0.85]
    fp_count = sum(1 for _, _, lab in high_score if lab <= 1)
    fp_rate = fp_count / len(high_score) if high_score else None

    # FN rate among perfect-label items: labeled 3 but scored below the surface threshold.
    perfect = [t for t in candidate_scores if t[2] == 3]
    fn_count = sum(1 for _, score, _ in perfect if score < 0.65)
    fn_rate = fn_count / len(perfect) if perfect else None

    return {
        "persona_id": data["persona_id"],
        "display_name": data.get("display_name", data["persona_id"]),
        "n_jobs": len(all_labels),
        "n_relevant": sum(1 for lab in all_labels if lab >= REL_THRESHOLD),
        "precision_at_5": precision_at_k(ranked_labels, 5),
        "precision_at_10": precision_at_k(ranked_labels, 10),
        "recall_at_10": recall_at_k(ranked_labels, all_labels, 10),
        "ndcg_at_10": ndcg_at_k(ranked_labels, 10),
        "fp_rate_high_score": fp_rate,
        "fn_rate_perfect_label": fn_rate,
        "ranked": [
            {"id": jid, "score": round(s, 3), "label": lab}
            for jid, s, lab in candidate_scores
        ],
    }


def _fmt(val: float | None) -> str:
    return "  n/a " if val is None else f"{val:6.3f}"


def _aggregate(results: list[dict]) -> dict | None:
    """Mean across personas, weighted equally (each persona = 1 vote)."""
    if not results:
        return None
    keys = ("precision_at_5", "precision_at_10", "recall_at_10", "ndcg_at_10",
            "fp_rate_high_score", "fn_rate_perfect_label")
    agg: dict = {"persona_id": "AGGREGATE", "display_name": "Aggregate (mean across personas)",
                 "n_jobs": sum(r["n_jobs"] for r in results),
                 "n_relevant": sum(r["n_relevant"] for r in results)}
    for k in keys:
        vals = [r[k] for r in results if r[k] is not None]
        agg[k] = sum(vals) / len(vals) if vals else None
    return agg


def print_text_report(results: list[dict]) -> None:
    print()
    header = (
        f"{'Persona':<48} {'n':>4} {'rel':>4} "
        f"{'P@5':>7} {'P@10':>7} {'R@10':>7} {'NDCG':>7} {'FP':>7} {'FN':>7}"
    )
    print(header)
    print("-" * len(header))
    for r in results:
        print(
            f"{r['display_name'][:47]:<48} "
            f"{r['n_jobs']:>4} {r['n_relevant']:>4} "
            f"{_fmt(r['precision_at_5'])} {_fmt(r['precision_at_10'])} "
            f"{_fmt(r['recall_at_10'])} {_fmt(r['ndcg_at_10'])} "
            f"{_fmt(r['fp_rate_high_score'])} {_fmt(r['fn_rate_perfect_label'])}"
        )
    agg = _aggregate(results)
    if agg and len(results) > 1:
        print("-" * len(header))
        print(
            f"{agg['display_name'][:47]:<48} "
            f"{agg['n_jobs']:>4} {agg['n_relevant']:>4} "
            f"{_fmt(agg['precision_at_5'])} {_fmt(agg['precision_at_10'])} "
            f"{_fmt(agg['recall_at_10'])} {_fmt(agg['ndcg_at_10'])} "
            f"{_fmt(agg['fp_rate_high_score'])} {_fmt(agg['fn_rate_perfect_label'])}"
        )
    print()
    print("Targets (launch gate): precision_at_5 >= 0.80, recall_at_10 >= 0.70")
    print()


async def main() -> int:
    parser = argparse.ArgumentParser(description="Job Scout scoring eval harness")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--persona", help="Persona id, e.g. junior_cs_umich")
    group.add_argument("--all", action="store_true", help="Run every persona file")
    parser.add_argument("--json", action="store_true", help="JSON output instead of text")
    args = parser.parse_args()

    personas_dir = BACKEND_ROOT / "evals" / "personas"
    if not personas_dir.exists():
        print(f"persona directory not found: {personas_dir}", file=sys.stderr)
        return 2

    if args.all:
        files = sorted(personas_dir.glob("*.yaml"))
    else:
        path = personas_dir / f"{args.persona}.yaml"
        if not path.exists():
            print(f"persona file not found: {path}", file=sys.stderr)
            return 2
        files = [path]

    if not files:
        print(f"no persona files in {personas_dir}", file=sys.stderr)
        return 2

    results: list[dict] = []
    for f in files:
        data = load_persona(f)
        if not data.get("jobs"):
            if not args.json:
                print(f"[skip] {data['persona_id']}: no labeled jobs yet", file=sys.stderr)
            continue
        try:
            result = await score_persona(data)
        except Exception as exc:
            print(f"[error] {data['persona_id']}: {exc}", file=sys.stderr)
            continue
        results.append(result)

    if not results:
        print("No personas with labeled jobs — add jobs + labels to evals/personas/*.yaml", file=sys.stderr)
        return 1

    if args.json:
        agg = _aggregate(results) if len(results) > 1 else None
        out: dict = {"personas": results}
        if agg:
            out["aggregate"] = agg
        print(json.dumps(out, indent=2))
    else:
        print_text_report(results)

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

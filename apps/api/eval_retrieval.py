"""Evaluate retrieval and optional answer evidence against locally labeled JSONL cases.

Run from apps/api: python eval_retrieval.py --cases path/to/private-cases.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
from time import perf_counter
from pathlib import Path

from app.assistant import AssistantService
from app.config import settings
from app.repository import Repository


async def evaluate(cases: list[dict], answers: bool) -> dict:
    repository = Repository(settings.database_path)
    repository.initialize()
    assistant = AssistantService(repository, settings)
    results = []
    for case in cases:
        query = case["query"]
        expected = set(case["expected_ids"])
        started = perf_counter()
        sources, _ = assistant.context_for(query)
        retrieval_ms = round((perf_counter() - started) * 1000, 1)
        answer = None
        origin = None
        if answers:
            answer, origin = await assistant.answer(query, sources)
        actual = {source.source_id for source in sources} | {
            source.metadata["message_id"] for source in sources if source.metadata.get("message_id")}
        retrieved = expected <= actual if expected else not sources
        first = sources[0] if sources else None
        top1 = bool(first and (first.source_id in expected or first.metadata.get("message_id") in expected))
        result = {"query": query, "category": case.get("category", "unspecified"),
                  "retrieved": retrieved, "top1": top1 if len(expected) == 1 else None,
                  "retrieval_ms": retrieval_ms, "total_ms": round((perf_counter() - started) * 1000, 1),
                  "expected_ids": sorted(expected), "returned_ids": [source.source_id for source in sources]}
        if answers:
            result["answer_origin"] = origin
            if case.get("answer_contains"):
                result["answer_contains_expected"] = all(
                    phrase.lower() in answer.lower() for phrase in case["answer_contains"])
        results.append(result)
    scored_answers = [item["answer_contains_expected"] for item in results if "answer_contains_expected" in item]
    top1 = [item["top1"] for item in results if item["top1"] is not None]
    latencies = sorted(item["retrieval_ms"] for item in results)
    categories = {name: {"cases": len(group), "retrieval_success_rate": sum(item["retrieved"] for item in group) / len(group),
                          "top1_success_rate": sum(item["top1"] for item in group if item["top1"] is not None) /
                          max(1, sum(item["top1"] is not None for item in group))}
                  for name in sorted({item["category"] for item in results})
                  for group in [[item for item in results if item["category"] == name]]}
    return {"cases": len(results), "retrieval_success_rate": sum(item["retrieved"] for item in results) / len(results),
            "top1_success_rate": sum(top1) / len(top1) if top1 else None,
            "retrieval_p50_ms": statistics.median(latencies),
            "retrieval_p95_ms": latencies[int(.95 * (len(latencies) - 1))], "categories": categories,
            "answer_phrase_success_rate": sum(scored_answers) / len(scored_answers) if scored_answers else None,
            "results": results}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True, help="Private JSONL with query, expected_ids, optional answer_contains")
    parser.add_argument("--answers", action="store_true", help="Also run the configured local model and check expected answer phrases")
    parser.add_argument("--summary-only", action="store_true", help="Print aggregate metrics without private queries or message IDs")
    parser.add_argument("--target", type=float, default=0.90, help="Minimum required retrieval success rate")
    args = parser.parse_args()
    cases = [json.loads(line) for line in args.cases.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not cases:
        parser.error("The case file is empty")
    for case in cases:
        if not isinstance(case.get("query"), str) or not isinstance(case.get("expected_ids"), list):
            parser.error("Each case needs a query string and expected_ids list")
    report = asyncio.run(evaluate(cases, args.answers))
    if args.summary_only:
        report.pop("results")
    print(json.dumps(report, indent=2))
    if report["retrieval_success_rate"] < args.target:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

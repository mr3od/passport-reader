"""Generate benchmark reports in Markdown and CSV."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Any

from passport_benchmark.compare import (
    ALL_FIELDS,
    FIELD_GROUPS,
    FIELD_TO_GROUP,
    CaseResult,
    semantic_mrz_match,
)


def _bias_summary(total_hall: int, total_omit: int, total_misread: int) -> str:
    if total_hall == 0 and total_omit == 0 and total_misread == 0:
        return "**Bias: no errors observed.**"
    if total_hall == 0 and total_omit == 0:
        return "**Bias: misread-only.** No hallucinations or omissions were observed."
    if total_misread > (total_hall + total_omit):
        return (
            "**Bias: misread-dominant.** "
            "Most errors are wrong reads, not hallucinations or omissions."
        )
    if total_hall > total_omit * 1.5:
        return "**Bias: hallucination-heavy.** Tighten 'return null if uncertain' instructions."
    if total_omit > total_hall * 1.5:
        return (
            "**Bias: omission-heavy.** "
            "Model is too conservative — consider loosening null threshold."
        )
    return "**Bias: roughly balanced** between hallucination and omission."


def _usage_totals(results: list[CaseResult]) -> dict[str, int]:
    totals: dict[str, int] = defaultdict(int)
    for r in results:
        usage = r.meta.get("usage")
        if not isinstance(usage, dict):
            continue
        for key, value in usage.items():
            if isinstance(value, int):
                totals[key] += value
    return dict(totals)


def _confidence_stats(results: list[CaseResult]) -> dict[str, Any]:
    correct: list[float] = []
    incorrect: list[float] = []
    overconfident_errors: list[tuple[float, str, str, str]] = []
    field_correct: dict[str, list[float]] = defaultdict(list)
    field_incorrect: dict[str, list[float]] = defaultdict(list)

    for result in results:
        confidence = result.meta.get("confidence")
        if not isinstance(confidence, dict):
            continue
        field_conf = confidence.get("fields")
        if not isinstance(field_conf, dict):
            continue

        for field in result.fields:
            value = field_conf.get(field.field_name)
            if not isinstance(value, (int, float)):
                continue
            score = float(value)
            if field.status == "match":
                correct.append(score)
                field_correct[field.field_name].append(score)
            elif field.status in {"misread", "hallucination", "omission"}:
                incorrect.append(score)
                field_incorrect[field.field_name].append(score)
                overconfident_errors.append((score, result.case_id, field.field_name, field.status))

    overconfident_errors.sort(reverse=True)

    def _avg(values: list[float]) -> float | None:
        return (sum(values) / len(values)) if values else None

    field_rows: list[dict[str, Any]] = []
    for field_name in ALL_FIELDS:
        c = field_correct.get(field_name, [])
        ic = field_incorrect.get(field_name, [])
        if not c and not ic:
            continue
        field_rows.append(
            {
                "field_name": field_name,
                "correct_avg": _avg(c),
                "incorrect_avg": _avg(ic),
                "correct_count": len(c),
                "incorrect_count": len(ic),
            }
        )

    field_rows.sort(
        key=lambda row: (
            row["incorrect_avg"] if row["incorrect_avg"] is not None else -1.0,
            row["incorrect_count"],
        ),
        reverse=True,
    )

    return {
        "correct_avg": _avg(correct),
        "incorrect_avg": _avg(incorrect),
        "count_correct": len(correct),
        "count_incorrect": len(incorrect),
        "overconfident_errors": overconfident_errors[:10],
        "field_rows": field_rows[:10],
    }


def generate_report(
    output_dir: Path,
    results: list[CaseResult],
    *,
    run_metadata: dict[str, Any] | None = None,
) -> None:
    """Write ``benchmark_report.md`` and ``benchmark_results.csv`` into *output_dir*."""
    total = len(results)
    if not total:
        return

    avg_acc = sum(r.accuracy for r in results) / total

    # Aggregates
    total_hall = sum(r.error_counts()["hallucination"] for r in results)
    total_omit = sum(r.error_counts()["omission"] for r in results)
    total_misread = sum(r.error_counts()["misread"] for r in results)

    # Per-field errors
    field_errors: dict[str, dict[str, int]] = {
        f: {"hallucination": 0, "omission": 0, "misread": 0} for f in ALL_FIELDS
    }
    for r in results:
        for fr in r.fields:
            if fr.status in field_errors.get(fr.field_name, {}):
                field_errors[fr.field_name][fr.status] += 1

    # Per-group accuracy
    group_accs: dict[str, list[float]] = defaultdict(list)
    for r in results:
        for group, acc in r.group_accuracy().items():
            if acc is not None:
                group_accs[group].append(acc)

    # Per-layout / per-quality
    layout_accs: dict[str, list[float]] = defaultdict(list)
    quality_accs: dict[str, list[float]] = defaultdict(list)
    for r in results:
        layout_accs[r.meta.get("layout", "unknown")].append(r.accuracy)
        quality_accs[r.meta.get("image_quality", "unknown")].append(r.accuracy)

    # MRZ stats
    mrz_tested = [r for r in results if r.mrz_valid is not None]
    mrz_pass = sum(1 for r in mrz_tested if r.mrz_valid)
    semantic_mrz_total = 0
    semantic_mrz_match_count = 0
    usage_totals = _usage_totals(results)
    confidence_stats = _confidence_stats(results)
    for r in results:
        for fr in r.fields:
            if fr.field_name not in ("MrzLine1", "MrzLine2"):
                continue
            if not isinstance(fr.expected, str) or not isinstance(fr.actual, str):
                continue
            semantic_mrz_total += 1
            if semantic_mrz_match(fr.field_name, fr.expected, fr.actual):
                semantic_mrz_match_count += 1

    # ── Markdown ─────────────────────────────────────────────────
    lines = [
        "# Passport Extractor Benchmark Report",
        "",
    ]
    if run_metadata:
        lines.extend(
            [
                f"**Run ID:** {run_metadata.get('run_id', '')}",
                f"**Model:** {run_metadata.get('model', '')}",
                "",
            ]
        )

    lines.extend(
        [
            f"**Cases evaluated:** {total}",
            f"**Average field accuracy:** {avg_acc:.1%}",
            f"**MRZ check digits:** {mrz_pass}/{len(mrz_tested)} cases pass all checks",
            (
                f"**Semantic MRZ accuracy:** "
                f"{semantic_mrz_match_count}/{semantic_mrz_total} lines match"
                if semantic_mrz_total
                else "**Semantic MRZ accuracy:** n/a"
            ),
            (
                f"**Token usage:** input={usage_totals.get('input_tokens', 0)}, "
                f"output={usage_totals.get('output_tokens', 0)}, "
                f"total={usage_totals.get('total_tokens', 0)}, "
                f"requests={usage_totals.get('requests', 0)}"
                if usage_totals
                else "**Token usage:** n/a"
            ),
            "",
            "---",
            "",
            "## 1. Error Direction (Bias Analysis)",
            "",
            "| Category | Count | Meaning |",
            "|---|---|---|",
            f"| Hallucination | {total_hall} | Model invented a value for a null/missing field |",
            f"| Omission | {total_omit} | Model returned null for a visible field |",
            f"| Misread | {total_misread} | Both have values but they differ |",
            "",
        ]
    )

    lines.append(_bias_summary(total_hall, total_omit, total_misread))

    lines += [
        "",
        "---",
        "",
        "## Run Usage",
        "",
        "| Metric | Total |",
        "|---|---|",
    ]
    if usage_totals:
        for key in sorted(usage_totals):
            lines.append(f"| {key} | {usage_totals[key]} |")
    else:
        lines.append("| usage | n/a |")

    lines += [
        "",
        "---",
        "",
        "## 2. Confidence Calibration",
        "",
    ]
    if confidence_stats["count_correct"] or confidence_stats["count_incorrect"]:
        correct_avg = confidence_stats["correct_avg"]
        incorrect_avg = confidence_stats["incorrect_avg"]
        lines.extend(
            [
                f"**Average confidence on correct fields:** {correct_avg:.2f}"
                if correct_avg is not None
                else "**Average confidence on correct fields:** n/a",
                f"**Average confidence on wrong fields:** {incorrect_avg:.2f}"
                if incorrect_avg is not None
                else "**Average confidence on wrong fields:** n/a",
                "",
                "### Most Overconfident Errors",
                "",
                "| Confidence | Case | Field | Status |",
                "|---|---|---|---|",
            ]
        )
        if confidence_stats["overconfident_errors"]:
            for score, case_id, field_name, status in confidence_stats["overconfident_errors"]:
                lines.append(f"| {score:.2f} | {case_id} | {field_name} | {status} |")
        else:
            lines.append("| n/a | n/a | n/a | n/a |")

        lines.extend(
            [
                "",
                "### Confidence By Field",
                "",
                "| Field | Avg Correct | Avg Wrong | Correct N | Wrong N |",
                "|---|---|---|---|---|",
            ]
        )
        for row in confidence_stats["field_rows"]:
            correct_avg = f"{row['correct_avg']:.2f}" if row["correct_avg"] is not None else "n/a"
            wrong_avg = f"{row['incorrect_avg']:.2f}" if row["incorrect_avg"] is not None else "n/a"
            lines.append(
                f"| {row['field_name']} | {correct_avg} | {wrong_avg} | "
                f"{row['correct_count']} | {row['incorrect_count']} |"
            )
    else:
        lines.extend(["No confidence data available.", ""])

    lines += [
        "---",
        "",
        "## 3. Accuracy by Field Group",
        "",
        "| Group | Avg Accuracy | Fields |",
        "|---|---|---|",
    ]
    for group in FIELD_GROUPS:
        avg = sum(group_accs[group]) / len(group_accs[group]) if group_accs[group] else None
        avg_text = f"{avg:.0%}" if avg is not None else "n/a"
        lines.append(f"| {group} | {avg_text} | {', '.join(FIELD_GROUPS[group])} |")

    lines += [
        "",
        "---",
        "",
        "## 4. Accuracy by Image Layout",
        "",
        "| Layout | Cases | Avg Accuracy |",
        "|---|---|---|",
    ]
    for layout, accs in sorted(layout_accs.items()):
        lines.append(f"| {layout} | {len(accs)} | {sum(accs) / len(accs):.0%} |")

    lines += [
        "",
        "## 5. Accuracy by Image Quality",
        "",
        "| Quality | Cases | Avg Accuracy |",
        "|---|---|---|",
    ]
    for quality, accs in sorted(quality_accs.items()):
        lines.append(f"| {quality} | {len(accs)} | {sum(accs) / len(accs):.0%} |")

    lines += [
        "",
        "---",
        "",
        "## 6. Worst Fields (Most Errors)",
        "",
        "| Field | Group | Halluc. | Omission | Misread | Total |",
        "|---|---|---|---|---|---|",
    ]
    sorted_fields = sorted(ALL_FIELDS, key=lambda f: sum(field_errors[f].values()), reverse=True)
    for f in sorted_fields:
        e = field_errors[f]
        t = sum(e.values())
        if t > 0:
            lines.append(
                f"| {f} | {FIELD_TO_GROUP.get(f, '?')} "
                f"| {e['hallucination']} | {e['omission']} | {e['misread']} | {t} |"
            )

    lines += [
        "",
        "---",
        "",
        "## 7. Per-Case Results",
        "",
        "| Case | Layout | Quality | Accuracy | Errors | MRZ | Worst Fields |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in sorted(results, key=lambda r: r.accuracy):
        ec = r.error_counts()
        err = f"{ec['misread']}m {ec['omission']}o {ec['hallucination']}h"
        mrz = "✓" if r.mrz_valid else ("✗" if r.mrz_valid is False else "—")
        layout = r.meta.get("layout", "?")
        quality = r.meta.get("image_quality", "?")
        worst = ", ".join(f.field_name for f in r.fields if f.status == "misread")[:60]
        lines.append(
            f"| {r.case_id} | {layout} | {quality} | {r.accuracy:.0%} | {err} | {mrz} | {worst} |"
        )

    (output_dir / "benchmark_report.md").write_text("\n".join(lines) + "\n")

    # ── CSV ──────────────────────────────────────────────────────
    csv_path = output_dir / "benchmark_results.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "run_id",
                "model",
                "case_id",
                "layout",
                "quality",
                "accuracy",
                "hallucinations",
                "omissions",
                "misreads",
                "mrz_valid",
                "input_tokens",
                "output_tokens",
                "total_tokens",
                "requests",
                "tool_calls",
                "warnings",
            ]
        )
        for r in results:
            ec = r.error_counts()
            usage = r.meta.get("usage", {})
            writer.writerow(
                [
                    r.meta.get("run_id", ""),
                    r.meta.get("model", ""),
                    r.case_id,
                    r.meta.get("layout", ""),
                    r.meta.get("image_quality", ""),
                    f"{r.accuracy:.3f}",
                    ec["hallucination"],
                    ec["omission"],
                    ec["misread"],
                    r.mrz_valid,
                    usage.get("input_tokens", ""),
                    usage.get("output_tokens", ""),
                    usage.get("total_tokens", ""),
                    usage.get("requests", ""),
                    usage.get("tool_calls", ""),
                    "; ".join(r.warnings),
                ]
            )

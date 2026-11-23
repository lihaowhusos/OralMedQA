"""Compare all model pairs on the complete frozen item set."""

import argparse
import csv
from decimal import Decimal, localcontext
from itertools import combinations
from pathlib import Path

from scoring_input import add_scope_arguments, load_item_constraints, load_matrix, load_scope


def exact_mcnemar(a, b):
    """Calculate the exact binomial tail without binary floating-point underflow."""
    n = a + b
    if n == 0:
        return Decimal(1)
    coefficient = 1
    tail_numerator = 1
    for k in range(1, min(a, b) + 1):
        coefficient = coefficient * (n - k + 1) // k
        tail_numerator += coefficient
    with localcontext() as context:
        context.prec = 100
        return min(Decimal(1), Decimal(2 * tail_numerator) / Decimal(1 << n))


def holm_adjust(pvalues):
    """Adjust a complete family while retaining Decimal precision."""
    order = sorted(range(len(pvalues)), key=pvalues.__getitem__)
    adjusted = [Decimal(0)] * len(pvalues)
    with localcontext() as context:
        context.prec = 100
        running = Decimal(0)
        for rank, index in enumerate(order):
            running = max(running, min(Decimal(1), pvalues[index] * (len(pvalues) - rank)))
            adjusted[index] = running
    return adjusted


FIELDS = (
    "Model_A", "Model_B", "N_common", "A_correct_B_wrong", "A_wrong_B_correct",
    "Accuracy_A", "Accuracy_B", "Accuracy_difference", "McNemar_exact_p", "Holm_adjusted_p",
)


def paired_rows(predictions, gold):
    n = len(gold)
    correct = {
        model: [records[item] == reference for item, reference in gold.items()]
        for model, records in predictions.items()
    }
    accuracy = {model: sum(values) / n for model, values in correct.items()}
    rows = []
    for a, b in combinations(correct, 2):
        a1b0 = a0b1 = 0
        for ac, bc in zip(correct[a], correct[b], strict=True):
            a1b0 += ac and not bc
            a0b1 += bc and not ac
        rows.append({
            "Model_A": a, "Model_B": b, "N_common": n,
            "A_correct_B_wrong": a1b0, "A_wrong_B_correct": a0b1,
            "Accuracy_A": accuracy[a], "Accuracy_B": accuracy[b],
            "Accuracy_difference": accuracy[a] - accuracy[b],
            "McNemar_exact_p": exact_mcnemar(a1b0, a0b1),
        })
    adjusted = holm_adjust([row["McNemar_exact_p"] for row in rows])
    for row, p_adj in zip(rows, adjusted, strict=True):
        row["McNemar_exact_p"] = format(row["McNemar_exact_p"], "E")
        row["Holm_adjusted_p"] = format(p_adj, "E")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("output_csv", type=Path)
    add_scope_arguments(parser)
    args = parser.parse_args()
    try:
        roster, gold = load_scope(args.benchmark, args.models, args.membership, args.analysis_set)
        predictions = load_matrix(args.input_csv, roster, gold, load_item_constraints(args.benchmark))
    except (ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    rows = paired_rows(predictions, gold)
    with args.output_csv.open("x", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()

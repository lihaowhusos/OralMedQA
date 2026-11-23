"""Score the complete archived-response matrix for one frozen analysis set."""

import argparse
import json
import math
from pathlib import Path

from scoring_input import LETTERS, add_scope_arguments, load_item_constraints, load_matrix, load_scope


def divide(numerator, denominator):
    return numerator / denominator if denominator else 0


def score(predictions, reference, labels="ABCDEFG"):
    if not labels or len(set(labels)) != len(labels) or not set(labels) <= LETTERS:
        raise ValueError("Metric labels must be unique uppercase option letters A-J")
    if not set().union(*reference.values()) <= set(labels):
        raise ValueError("Metric labels must cover every frozen reference label in the selected set")
    data = [
        (gold, set(predictions[item].split("|")) if predictions[item] else set())
        for item, gold in reference.items()
    ]
    n = len(reference)
    correct = sum(gold == pred for gold, pred in data)
    n_valid = sum(prediction is not None for prediction in predictions.values())
    counts = []
    for label in labels:
        tp = sum(label in gold and label in pred for gold, pred in data)
        fp = sum(label not in gold and label in pred for gold, pred in data)
        fn = sum(label in gold and label not in pred for gold, pred in data)
        counts.append(dict(
            label=label, TP=tp, FP=fp, FN=fn,
            precision=divide(tp, tp + fp), recall=divide(tp, tp + fn),
            f1=divide(2 * tp, 2 * tp + fp + fn),
        ))
    z = 1.959963984540054
    p = correct / n
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return dict(
        N=n, N_correct=correct, N_valid=n_valid, Accuracy=p,
        Accuracy_Wilson_lower=center - half, Accuracy_Wilson_upper=center + half,
        Valid_response_accuracy=correct / n_valid if n_valid else None,
        Macro_Precision=sum(x["precision"] for x in counts) / len(labels),
        Macro_Recall=sum(x["recall"] for x in counts) / len(labels),
        Macro_F1=sum(x["f1"] for x in counts) / len(labels), label_counts=counts,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("output_json", type=Path)
    parser.add_argument("--labels", default="ABCDEFG", help="Fixed macro-metric labels as unique uppercase letters (default ABCDEFG)")
    add_scope_arguments(parser)
    args = parser.parse_args()
    try:
        roster, gold = load_scope(args.benchmark, args.models, args.membership, args.analysis_set)
        constraints = load_item_constraints(args.benchmark)
        predictions = load_matrix(args.input_csv, roster, gold, constraints)
        reference = {item: set(labels.split("|")) for item, labels in gold.items()}
        metrics = {model: score(predictions[model], reference, args.labels) for model in roster}
    except (ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    with args.output_json.open("x", encoding="utf-8") as handle:
        json.dump(metrics, handle, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()

"""Build a complete model-by-item scoring CSV from aligned archived responses.

The input JSONL follows align.py's file-level output. Each file record supplies
a unique neutral source_id, a canonical model, a dataset hint and mapped rows.
File representation and deterministic selection order must be supplied inline
or in a source manifest. The output contains derived scoring fields only.
"""

import argparse
import csv
import json
import os
import re
import tempfile
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from parser import VERSION, extract
from scoring_input import load_scope, read_json


PARSER_FAILURE_STATUSES = {
    "API_ERROR", "EMPTY_RESPONSE", "REFUSAL", "UNPARSEABLE", "INVALID_FORMAT"
}
SOURCE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
ALIGNMENT_METHODS = {
    "STEM_OPTIONS_EXACT", "STEM_OPTIONS_COMPATIBLE", "STEM_OPTION_TEXT_REMAP",
    "PARAPHRASE_IDENTICAL_OPTIONS", "FULL_SEQUENCE_VERIFIED_ITEM_IDENTITY",
    "STEM_OPTIONS_SEQUENCE_ANCHORED", "PARAPHRASE_OPTIONS_LONG_SEQUENCE",
    "STEM_OPTIONS_NEIGHBOR_ANCHORED", "IDENTICAL_ITEM_OCCURRENCE_VERIFIED_ORDER",
}
FIELDS = [
    "Model", "question_id", "dataset_id", "question_type", "gold",
    "prediction", "status", "correct", "source_id", "source_row",
    "join_method", "parser_rule", "candidate_count", "selected_file_count",
    "duplicate", "representation", "selection_order", "analysis_set",
]


def normalize(value):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value or ""))).strip()


def text_key(value):
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", normalize(value).lower())


def options(row):
    return {label: row["选项" + label] for label in "ABCDEFGHIJ"
            if normalize(row.get("选项" + label, ""))}


def validate_source_id(value):
    if not isinstance(value, str) or not SOURCE_ID.fullmatch(value):
        raise ValueError("Each file requires a unique neutral source_id using letters, digits, dots, underscores or hyphens")
    return value


def load_manifest(path):
    if path is None:
        return {}
    manifest = read_json(path)
    if not isinstance(manifest, dict):
        raise ValueError("The source manifest must be an object keyed by source_id")
    for source_id, metadata in manifest.items():
        validate_source_id(source_id)
        if not isinstance(metadata, dict):
            raise ValueError("Every source-manifest entry must be an object")
    return manifest


def file_metadata(source, manifest):
    source_id = validate_source_id(source.get("source_id"))
    external = manifest.get(source_id, {})
    values = {}
    for field in ("representation", "selection_order"):
        inline = source.get(field)
        supplied = external.get(field)
        if inline is not None and supplied is not None and inline != supplied:
            raise ValueError(f"Conflicting {field} declarations for source_id {source_id}")
        values[field] = inline if inline is not None else supplied
    if values["representation"] not in {"original", "processed"}:
        raise ValueError(f"source_id {source_id} requires representation original or processed")
    order = values["selection_order"]
    if not isinstance(order, int) or isinstance(order, bool) or order < 0:
        raise ValueError(f"source_id {source_id} requires a non-negative integer selection_order")
    return source_id, values["representation"], order


@dataclass(frozen=True)
class Candidate:
    source_id: str
    representation: str
    selection_order: int
    source_row: object
    method: str
    raw: object
    options: dict


def load_candidates(path, benchmark, model_order, manifest):
    by_item = defaultdict(dict)
    candidate_counts = Counter()
    seen_files = set()
    orders = set()
    allowed_models = set(model_order)
    with open(path, encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            source = json.loads(line)
            if not isinstance(source, dict):
                raise ValueError(f"Aligned record {line_number} must be an object")
            source_id, representation, order = file_metadata(source, manifest)
            if source_id in seen_files:
                raise ValueError(f"Repeated file-level source_id {source_id}")
            seen_files.add(source_id)
            model = source.get("model")
            model = model.get("canonical_model") if isinstance(model, dict) else model
            dataset_id = source.get("hint")
            if model not in allowed_models or dataset_id not in benchmark:
                raise ValueError(f"Aligned record {line_number} refers to an unexpected model or dataset")
            order_key = (model, dataset_id, order)
            if order_key in orders:
                raise ValueError("selection_order must be unique within each model and dataset")
            orders.add(order_key)
            mapped = source.get("mapped")
            if not isinstance(mapped, list):
                raise ValueError(f"source_id {source_id} requires a mapped array")
            for entry in mapped:
                if not isinstance(entry, dict):
                    raise ValueError(f"source_id {source_id} has a malformed mapped entry")
                index = entry.get("index")
                if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(benchmark[dataset_id]["rows"]):
                    raise ValueError(f"source_id {source_id} has an out-of-range mapped index")
                row = entry.get("row")
                method = entry.get("method")
                if not isinstance(row, dict) or method not in ALIGNMENT_METHODS:
                    raise ValueError(f"source_id {source_id} requires row and method for every mapped entry")
                raw = row.get("模型原始回答", "")
                if raw is not None and not isinstance(raw, str):
                    raise ValueError(f"source_id {source_id} requires raw responses as strings or null")
                item_key = (model, dataset_id, index)
                candidate_counts[item_key] += 1
                # Array order records the historical first occurrence within a file.
                if source_id not in by_item[item_key]:
                    by_item[item_key][source_id] = Candidate(
                        source_id, representation, order, row.get("_row", ""),
                        method, raw, options(row),
                    )
    return by_item, candidate_counts


def question_type(source, reference, gold):
    inferred = "MULTI" if len(gold.split("|")) > 1 else "SINGLE"
    declared = reference.get("question_type", source.get("question_type", inferred))
    if declared not in {"SINGLE", "MULTI"}:
        raise ValueError("question_type must be SINGLE or MULTI for option-label scoring")
    if declared == "SINGLE" and inferred == "MULTI":
        raise ValueError("A multi-label reference cannot have question_type SINGLE")
    return declared


def parse_selected(candidate, reference_options, qtype):
    remap = candidate.method == "STEM_OPTION_TEXT_REMAP"
    parse_options = candidate.options if remap else {**reference_options, **candidate.options}
    prediction, status, rule = extract(candidate.raw, parse_options, qtype, parse_options)
    if status == "PARSED" and remap:
        source_values = [text_key(value) for value in candidate.options.values()]
        if not all(source_values) or len(set(source_values)) != len(source_values):
            return prediction, "INVALID_FORMAT", rule + ";ambiguous_option_text_remap"
        mapping = {}
        for source_label, text in candidate.options.items():
            targets = [label for label, value in reference_options.items() if text_key(value) == text_key(text)]
            if len(targets) != 1:
                reason = "ambiguous_option_text_remap" if targets else "unmapped_option_text_remap"
                return prediction, "INVALID_FORMAT", rule + ";" + reason
            mapping[source_label] = targets[0]
        if set(mapping.values()) != set(reference_options):
            return prediction, "INVALID_FORMAT", rule + ";incomplete_option_text_remap"
        if any(label not in mapping for label in prediction.split("|")):
            return prediction, "INVALID_FORMAT", rule + ";unmapped_predicted_label"
        prediction = "|".join(sorted(mapping[label] for label in prediction.split("|")))
        rule += ";option_text_remap"
    if status != "PARSED" and status not in PARSER_FAILURE_STATUSES:
        raise ValueError("The parser returned an unsupported response status")
    return prediction, status, rule


def score_item(model, dataset_id, index, source, reference, gold, candidates, count, analysis_set):
    qtype = question_type(source, reference, gold)
    output = dict.fromkeys(FIELDS, "")
    output.update(
        Model=model, question_id=f"{dataset_id}:{index + 1:04d}", dataset_id=dataset_id,
        question_type=qtype, gold=gold, status="MISSING_RESPONSE", correct=0,
        candidate_count=count, selected_file_count=0, duplicate=int(count > 1),
        analysis_set=analysis_set,
    )
    if not candidates:
        return output
    originals = [candidate for candidate in candidates if candidate.representation == "original"]
    pool = sorted(originals or candidates, key=lambda candidate: candidate.selection_order)
    output["selected_file_count"] = len(pool)
    output["representation"] = pool[0].representation
    if len({normalize(candidate.raw) for candidate in pool}) > 1:
        output.update(status="CONFLICTING_DUPLICATE", source_id="|".join(candidate.source_id for candidate in pool))
        return output
    selected = pool[0]
    prediction, status, rule = parse_selected(selected, options(reference), qtype)
    if status == "PARSED":
        status = "VALID_RESPONSE" if prediction == gold else "INCORRECT_RESPONSE"
    output.update(
        prediction=prediction, status=status, correct=int(status == "VALID_RESPONSE"),
        source_id=selected.source_id, source_row=selected.source_row,
        join_method=selected.method, parser_rule=rule, selection_order=selected.selection_order,
    )
    return output


def build_rows(benchmark, models, expected_gold, by_item, counts, analysis_set):
    rows = []
    expected_ids = set(expected_gold)
    for model in models:
        for dataset_id, source in benchmark.items():
            for index, reference in enumerate(source["rows"]):
                question_id = f"{dataset_id}:{index + 1:04d}"
                if question_id in expected_ids:
                    key = (model, dataset_id, index)
                    rows.append(score_item(
                        model, dataset_id, index, source, reference, expected_gold[question_id],
                        list(by_item.get(key, {}).values()), counts[key], analysis_set,
                    ))
    expected_keys = {(model, qid) for model in models for qid in expected_ids}
    observed_keys = {(row["Model"], row["question_id"]) for row in rows}
    if len(rows) != len(expected_keys) or observed_keys != expected_keys:
        raise ValueError("Generated scoring rows do not match the complete requested model-by-item matrix")
    return rows


def validate_output_paths(outputs, inputs):
    resolved_inputs = {Path(path).resolve() for path in inputs if path is not None}
    resolved_outputs = [Path(path).resolve() for path in outputs if path is not None]
    if len(set(resolved_outputs)) != len(resolved_outputs):
        raise ValueError("Matrix and audit outputs must have different destinations")
    if any(path in resolved_inputs for path in resolved_outputs):
        raise ValueError("Output destinations must differ from all input files")
    for path in outputs:
        if path is None:
            continue
        path = Path(path)
        if os.path.lexists(path):
            raise FileExistsError("Output destination already exists")
        if not path.parent.is_dir():
            raise ValueError("Each output parent directory must already exist")


def write_outputs(path, rows, audit_path, summary):
    temporary_files = []
    committed = []
    try:
        for destination in (Path(path), Path(audit_path) if audit_path else None):
            if destination is None:
                continue
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8-sig" if destination == Path(path) else "utf-8",
                                             newline="", dir=destination.parent, prefix=destination.name + ".",
                                             suffix=".tmp", delete=False) as handle:
                temporary_files.append((Path(handle.name), destination))
                if destination == Path(path):
                    writer = csv.DictWriter(handle, fieldnames=FIELDS)
                    writer.writeheader()
                    writer.writerows(rows)
                else:
                    json.dump(summary, handle, ensure_ascii=False, indent=2)
        for temporary, destination in temporary_files:
            # A hard-link commit publishes the completed file and rejects a race
            # that creates the same destination after the initial path checks.
            os.link(temporary, destination)
            committed.append(destination)
    except BaseException:
        for destination in committed:
            destination.unlink()
        raise
    finally:
        for temporary, destination in temporary_files:
            if temporary.exists():
                temporary.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_jsonl")
    parser.add_argument("output_csv")
    parser.add_argument("--benchmark", required=True)
    parser.add_argument("--models", required=True)
    parser.add_argument("--membership")
    parser.add_argument("--analysis-set", choices=["SET_A", "SET_B"], default="SET_A")
    parser.add_argument("--source-manifest")
    parser.add_argument("--audit")
    args = parser.parse_args()
    validate_output_paths(
        [args.output_csv, args.audit],
        [args.input_jsonl, args.benchmark, args.models, args.membership, args.source_manifest],
    )
    models, expected_gold = load_scope(args.benchmark, args.models, args.membership, args.analysis_set)
    benchmark = read_json(args.benchmark)
    manifest = load_manifest(args.source_manifest)
    by_item, counts = load_candidates(args.input_jsonl, benchmark, models, manifest)
    rows = build_rows(benchmark, models, expected_gold, by_item, counts, args.analysis_set)
    summary = {
        "analysis_set": args.analysis_set, "models": len(models), "items_per_model": len(expected_gold),
        "rows": len(rows), "parser_version": VERSION,
        "status_counts": dict(Counter(row["status"] for row in rows)),
    }
    write_outputs(args.output_csv, rows, args.audit, summary)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()

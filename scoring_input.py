"""Validate scoring inputs against independently supplied frozen items and models."""

import csv
import json
from pathlib import Path
import re
import unicodedata


PARSEABLE = {"VALID_RESPONSE", "INCORRECT_RESPONSE"}
STATUSES = PARSEABLE | {
    "MISSING_RESPONSE", "EMPTY_RESPONSE", "API_ERROR", "REFUSAL",
    "INVALID_FORMAT", "UNPARSEABLE", "CONFLICTING_DUPLICATE",
}
LETTERS = frozenset("ABCDEFGHIJ")
CSV_FIELDS = ("Model", "question_id", "gold", "prediction", "status")


def add_scope_arguments(parser):
    parser.add_argument("--benchmark", required=True, type=Path, help="Frozen benchmark JSON")
    parser.add_argument("--models", required=True, type=Path, help="Ordered JSON list of model names")
    parser.add_argument("--membership", type=Path, help="Frozen membership CSV (required for SET_B)")
    parser.add_argument("--analysis-set", choices=("SET_A", "SET_B"), default="SET_A")


def normalize(value):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value or ""))).strip()


def read_json(path):
    def unique_object(pairs):
        result = dict(pairs)
        if len(result) != len(pairs):
            raise ValueError("JSON input contains a duplicate object key")
        return result

    with Path(path).open(encoding="utf-8-sig") as handle:
        return json.load(handle, object_pairs_hook=unique_object)


def require_columns(reader, required):
    fields = reader.fieldnames or []
    if len(fields) != len(set(fields)) or not set(required).issubset(fields):
        raise ValueError("CSV requires unique columns including " + ", ".join(required))


def load_scope(benchmark, models, membership=None, analysis_set="SET_A"):
    """Return the ordered models and canonical gold for the expected item IDs."""
    roster = read_json(models)
    if not isinstance(roster, list) or not roster or any(
        not isinstance(name, str) or not name.strip() or name != name.strip() for name in roster
    ) or len(set(roster)) != len(roster):
        raise ValueError("The model roster must be a nonempty list of unique names")

    reference = read_json(benchmark)
    if not isinstance(reference, dict) or not reference:
        raise ValueError("The benchmark must contain frozen source records")
    gold_by_item = {}
    for source_id, collection in reference.items():
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", source_id) or not collection["rows"]:
            raise ValueError("Each source requires a neutral ID and a nonempty rows list")
        for ordinal, row in enumerate(collection["rows"], 1):
            question_id = f"{source_id}:{ordinal:04}"
            labels = set(normalize(row["正确选项"]))
            if not labels or not labels <= LETTERS:
                raise ValueError(f"Invalid frozen gold labels for {question_id!r}")
            gold_by_item[question_id] = "|".join(sorted(labels))

    if analysis_set not in {"SET_A", "SET_B"}:
        raise ValueError("Expected SET_A or SET_B")
    if membership is None:
        if analysis_set == "SET_B":
            raise ValueError("SET_B requires the frozen membership CSV")
        return roster, gold_by_item

    keep = {}
    with Path(membership).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        require_columns(reader, ("question_id", "SET_A", "SET_B"))
        for row in reader:
            question_id = row["question_id"]
            if question_id in keep or question_id not in gold_by_item:
                raise ValueError("Membership contains an unexpected or duplicate question ID")
            if row["SET_A"].lower() != "true" or row["SET_B"].lower() not in {"true", "false"}:
                raise ValueError("All frozen items must be in SET_A, with true/false flags for SET_B")
            keep[question_id] = row[analysis_set].lower() == "true"
    if keep.keys() != gold_by_item.keys():
        raise ValueError("Membership does not contain the complete frozen question IDs")
    selected = {question_id: gold for question_id, gold in gold_by_item.items() if keep[question_id]}
    if not selected:
        raise ValueError("Selected analysis set is empty")
    return roster, selected


def load_item_constraints(benchmark):
    """Return frozen option labels and SINGLE/MULTI types for CSV validation."""
    constraints = {}
    for source_id, collection in read_json(benchmark).items():
        for ordinal, row in enumerate(collection["rows"], 1):
            question_id = f"{source_id}:{ordinal:04}"
            gold = set(normalize(row["正确选项"]))
            qtype = row.get("question_type", collection.get("question_type", "MULTI" if len(gold) > 1 else "SINGLE"))
            if qtype not in {"SINGLE", "MULTI"} or qtype == "SINGLE" and len(gold) != 1:
                raise ValueError(f"Invalid frozen question_type for {question_id!r}")
            allowed = {label for label in LETTERS if normalize(row.get("选项" + label, ""))}
            constraints[question_id] = (allowed, qtype)
    return constraints


def load_matrix(path, roster, expected_gold, item_constraints=None):
    """Return model/item predictions, with None for statuses given zero credit."""
    groups = {model: {} for model in roster}
    expected_ids = expected_gold.keys()
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        require_columns(reader, CSV_FIELDS)
        for row in reader:
            if None in row or any(row[field] is None for field in CSV_FIELDS):
                raise ValueError(f"Malformed matrix CSV record at line {reader.line_num}")
            model, item = row["Model"], row["question_id"]
            status, pred = row["status"], row["prediction"]
            if model not in groups or item not in expected_ids:
                raise ValueError(f"Unexpected model or item at line {reader.line_num}")
            if item in groups[model]:
                raise ValueError(f"Duplicate model/item record at line {reader.line_num}")
            gold = expected_gold[item]
            if row["gold"] != gold or status not in STATUSES:
                raise ValueError(f"Invalid gold or status at line {reader.line_num}")
            if status in PARSEABLE:
                labels = pred.split("|")
                if not set(labels) <= LETTERS or labels != sorted(set(labels)):
                    raise ValueError(f"Invalid parsed label set at line {reader.line_num}")
                if item_constraints is not None:
                    allowed, qtype = item_constraints[item]
                    if not set(labels) <= allowed or qtype == "SINGLE" and len(labels) != 1:
                        raise ValueError(f"Parsed labels violate frozen options or question type at line {reader.line_num}")
                if (gold == pred) != (status == "VALID_RESPONSE"):
                    raise ValueError(f"Status conflicts with exact-match outcome at line {reader.line_num}")
            if "correct" in row and row["correct"] != str(int(status == "VALID_RESPONSE")):
                raise ValueError(f"Invalid exact-match indicator at line {reader.line_num}")
            groups[model][item] = pred if status in PARSEABLE else None
    incomplete = [model for model, records in groups.items() if records.keys() != expected_ids]
    if incomplete:
        raise ValueError(f"Incomplete model/item matrix: {len(incomplete)} model(s) lack expected records")
    return groups

# Archived response processing and scoring

The scripts run offline with Python 3.10 or later and use the standard library. They align archived responses, assemble the complete scoring matrix, and compute model metrics and paired comparisons for the selected analysis set.

## Private inputs

- **Frozen benchmark JSON** maps each neutral collection ID to a `rows` array in frozen order. Each row has `题目` (stem), lettered `选项A`, `选项B`, etc., and `正确选项` (reference letters, such as `AB`). Each item ID is its neutral collection ID, a colon, and its one-based ordinal padded to four digits. Set `question_type` to `SINGLE` or `MULTI` on a row or collection when the frozen question type requires it. A row-level value takes precedence. In the absence of type metadata, the builder infers the type from the frozen reference set size.
- **Ordered model roster JSON** is an array of the expected canonical model names. Include every evaluated model, including any model without an aligned response.
- **Archived input JSONL** has one object per source file. Each object has a unique neutral `source_id`, the neutral collection `hint`, a `model` object with `model_scope` set to `EXPECTED` and `canonical_model` matching the roster, and a `rows` array in recorded order. Rows use the same stem and option fields as the benchmark, `模型原始回答` for the raw answer and `_row` for the source row number.
- **Source manifest JSON** maps each neutral `source_id` to `representation` (`original` or `processed`) and a non-negative integer `selection_order`. The archive objects can also carry those two fields. Derive metadata from the archived file inventory before anonymizing filenames. For historical replay, assign `selection_order` in the original path-sort order before anonymization. It must be unique within a model and aligned collection.
- **Frozen membership CSV** has `question_id`, `SET_A` and `SET_B` columns with Boolean membership flags. It covers every frozen item. Supply it for SET_B. SET_A defaults to all frozen items.

Keep the private inputs and the working outputs outside the distributed code directory. The reference materials are subject to third-party rights. The alignment outputs contain question text and may contain raw responses. The scoring CSV contains derived labels, statuses and neutral provenance keys.

## Commands

Replace the uppercase placeholders with your own paths. Use a fresh private directory for the first command and distinct output paths for each analysis set.

```text
python align.py PRIVATE_BENCHMARK PRIVATE_ARCHIVES PRIVATE_ALIGN_DIR
python build_scoring_matrix.py PRIVATE_ALIGNED_JSONL SET_A_MATRIX --benchmark PRIVATE_BENCHMARK --models PRIVATE_MODELS --source-manifest PRIVATE_SOURCE_MANIFEST
python build_scoring_matrix.py PRIVATE_ALIGNED_JSONL SET_B_MATRIX --benchmark PRIVATE_BENCHMARK --models PRIVATE_MODELS --source-manifest PRIVATE_SOURCE_MANIFEST --membership PRIVATE_MEMBERSHIP --analysis-set SET_B
python score_aligned.py SET_A_MATRIX SET_A_METRICS --benchmark PRIVATE_BENCHMARK --models PRIVATE_MODELS --labels ABCDEFG
python score_aligned.py SET_B_MATRIX SET_B_METRICS --benchmark PRIVATE_BENCHMARK --models PRIVATE_MODELS --membership PRIVATE_MEMBERSHIP --analysis-set SET_B --labels ABCDEFG
python paired_stats.py SET_B_MATRIX SET_B_PAIRS --benchmark PRIVATE_BENCHMARK --models PRIVATE_MODELS --membership PRIVATE_MEMBERSHIP --analysis-set SET_B
```

`PRIVATE_ALIGNED_JSONL` is the `aligned_sources.jsonl` file in `PRIVATE_ALIGN_DIR`. To compute both metrics and paired comparisons for either set, pass the same matrix and scope arguments to the respective scripts.

## From aligned records to scores

The matrix builder retains the first mapped occurrence per item within each source file. Across files it gives priority to original representations, groups matching raw answers after Unicode and whitespace normalization, and records remaining differences as `CONFLICTING_DUPLICATE`. For agreeing records it uses the declared source order to choose a representation. The parser extracts the answer from that representation. For reordered options, each normalized source option text must be unique and identify exactly one frozen label, with the full option set covered. A successful mapping receives `option_text_remap` in `parser_rule`. Ambiguous, absent or incomplete mappings receive `INVALID_FORMAT` with a corresponding `ambiguous_option_text_remap`, `unmapped_option_text_remap` or `incomplete_option_text_remap` rule. The extracted source prediction is retained for these zero-credit records.

The builder fills the full model-by-item grid, writing `MISSING_RESPONSE` for items without a matched record. It writes one record for each model and each item in the chosen set. Core columns are `Model`, `question_id`, `gold`, `prediction` and `status`. Multiple labels are separated by `|`. `VALID_RESPONSE` denotes a correct parseable answer, and `INCORRECT_RESPONSE` denotes an incorrect parseable answer. The other statuses count in the fixed denominator and receive zero exact-match credit.

The scoring and paired-comparison scripts validate each model's item IDs, reference labels and scoring statuses against the supplied roster and frozen set. Parseable predictions must use the frozen item's option labels and satisfy its `SINGLE` or `MULTI` constraint. Frozen reference-key/option anomalies remain part of the supplied primary benchmark. Predictions retained under non-parseable statuses receive zero credit. A duplicate or missing row fails validation even when all models share the same incomplete subset. The fixed-denominator score uses the complete expected set. Conditional accuracy uses the model's parseable responses.

Macro-Precision, Macro-Recall and Macro-F1 use the explicit `--labels` universe, which defaults to the fixed labels `ABCDEFG`. Use `--labels ABCDEFG` for overall SET_A, SET_B and the Supplementary Methods S6 example. Labels absent from the example's reference answers remain in the macro average, with undefined component ratios set to zero. The supplied label universe must contain every reference label in the selected set. For a source-level analysis, pass that source's frozen label universe explicitly, such as `--labels ABCDE`. Changing `--labels` changes the macro average's denominator and leaves exact-match accuracy unchanged.

For source-level scoring, supply that source's benchmark and complete model-by-item matrix, the same model roster, and its membership-table slice for SET_B, together with the explicit frozen label universe (for example, `--labels ABCDE`).

For the three S6 examples, reference/prediction sets are `A`/`B`, `A|C`/`A`, and `B`/`B`. With labels A–G, accuracy is `1/3`, Macro-Precision and Macro-Recall are each `1.5/7 = 0.21428571428571427`, and Macro-F1 is `(2/3 + 2/3)/7 = 0.19047619047619047`.

Each McNemar comparison uses every expected item in the selected set. The exact calculation uses integer binomial-tail numerators and 100-digit Decimal arithmetic. Holm adjustment applies to the complete model-pair family for that set. P values are exported in scientific notation and should be preserved as text or Decimal on import.

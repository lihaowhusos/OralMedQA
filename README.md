# OralMedBench — scoring code

Code for *"Benchmarking large language models for dental knowledge assessment in oral
health education: a bilingual OralMedQA study"*.

Aligns archived model responses to frozen items, parses answers, and computes
fixed-denominator accuracy, option-label macro metrics, Wilson intervals, and exact
McNemar tests with Holm adjustment.

## Note

This is a cleaned, anonymized re-implementation, not the original execution snapshot.
**No data are included**: benchmark items and model responses are third-party material,
available from the corresponding author on reasonable request.

## Files

| File | Purpose |
| --- | --- |
| `align.py` | Align archived responses to frozen items |
| `build_scoring_matrix.py` | Build the complete model × item scoring matrix |
| `parser.py` | Extract the predicted label(s) from a raw response |
| `score_aligned.py` | Accuracy, Macro-P/R/F1, Wilson CI |
| `paired_stats.py` | Exact McNemar + Holm |
| `scoring_input.py` | Input validation |
| `Prompt_Construction/` | Historical prompt templates and provenance |
| `examples/`, `tests/` | Synthetic run and smoke tests |

## Run

Python 3.10+. Scoring scripts use only the standard library.

```bash
python examples/make_example.py
python align.py example/benchmark.json example/archives.jsonl align_out
python build_scoring_matrix.py align_out/aligned_sources.jsonl SET_A.csv \
    --benchmark example/benchmark.json --models example/models.json \
    --source-manifest example/manifest.json
python score_aligned.py SET_A.csv metrics.json \
    --benchmark example/benchmark.json --models example/models.json
python paired_stats.py SET_A.csv pairs.csv \
    --benchmark example/benchmark.json --models example/models.json
```

```bash
python -m unittest discover -s tests -v
```

## Not included

- Benchmark items, responses, and membership tables (third-party material).
- Historical notebooks (contain credentials and copyrighted item text).
- Resampling code for the Macro-F1 bootstrap, permutation tests, and Spearman
  estimates. Procedures and seed (`20260912`) are in Supplementary Methods S5, S7, S10.

## Caveats

Parser rules were developed iteratively (v1.1.0) and matter most for weak models that
answer in prose; read low scores together with the parseable-response rate in Table S3.
Models were queried February–August 2025 through different clients, so this is an
exploratory retrospective benchmark, not a controlled head-to-head evaluation.

## License

MIT. No third-party question text is distributed.

## Citation

```bibtex
@article{oralmedqa2026,
  title   = {Benchmarking large language models for dental knowledge assessment in
             oral health education: a bilingual OralMedQA study},
  author  = {Che, Yun-Ting and Huang, Ze-Yu and Zhou, Cheng-Ke and Zhang, Lan-Yi and
             Li, Le-Jia and Su, Xuan-Yu and Li, Shu-Jin and Li, Hao},
  journal = {BMC Oral Health},
  year    = {2026}
}
```

Contact: Hao Li — lihaowhusos@whu.edu.cn

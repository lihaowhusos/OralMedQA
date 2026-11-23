"""Archived item-alignment logic with source identifiers anonymized.

Supply the reference JSON, archived-response JSONL and a new private output
directory as arguments. Each source record carries a stable neutral file ID.
"""
import argparse
import json
import re
import unicodedata
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

STOP = set(
    "the a an of to in and or which following is are be for from with as by that "
    "this does do what most would should can it on at all except not".split()
)
TOKENS = {}


def norm(value):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value or ""))).strip()


def key(value):
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", norm(value).lower())


def stem(value):
    return key(re.sub(r"^\s*(?:Question\s*)?\d+\s*[:.、]\s*", "", norm(value), flags=re.I))


def opts(row):
    return tuple((c, key(row.get("选项" + c, ""))) for c in "ABCDEFGHIJ" if key(row.get("选项" + c, "")))


refs = {}


def register(text):
    TOKENS[stem(text)] = set(re.findall(r"[a-z]{3,}", norm(text).lower())) - STOP


def similarity(q, g):
    ratio = SequenceMatcher(None, q, g, autojunk=False).ratio()
    a = TOKENS.get(q, set())
    b = TOKENS.get(g, set())
    if len(a & b) >= 2:
        ratio = max(ratio, 2 * len(a & b) / (len(a) + len(b)))
    return ratio


ix, oi, si = {}, {}, {}
def index_references(reference):
    refs.update(reference)
    for source_id, value in refs.items():
        ix[source_id] = defaultdict(list)
        oi[source_id] = defaultdict(list)
        si[source_id] = defaultdict(list)
        for i, row in enumerate(value["rows"]):
            register(row["题目"])
            ix[source_id][(stem(row["题目"]), opts(row))].append(i)
            oi[source_id][opts(row)].append(i)
            si[source_id][stem(row["题目"])].append(i)


@lru_cache(None)
def match(source_id, q, o):
    exact = ix[source_id].get((q, o), [])
    if exact:
        return tuple(exact), "STEM_OPTIONS_EXACT", 1.0

    compatible = [
        i
        for i in si[source_id].get(q, [])
        if all(dict(opts(refs[source_id]["rows"][i])).get(c) == v for c, v in o)
    ]
    if compatible and len(o) >= 2:
        return tuple(compatible), "STEM_OPTIONS_COMPATIBLE", 1.0

    remappable = [
        i
        for i in si[source_id].get(q, [])
        if len(set(v for _, v in o)) == len(o)
        and len({v for _, v in opts(refs[source_id]["rows"][i])}) == len(opts(refs[source_id]["rows"][i]))
        and set(v for _, v in o) == set(v for _, v in opts(refs[source_id]["rows"][i]))
    ]
    if remappable and len(o) >= 2:
        return tuple(remappable), "STEM_OPTION_TEXT_REMAP", 1.0

    candidates = oi[source_id].get(o, []) if len(o) >= 3 else []
    ranked = sorted(
        [(similarity(q, stem(refs[source_id]["rows"][i]["题目"])), i) for i in candidates],
        reverse=True,
    )
    if ranked and ranked[0][0] >= 0.60:
        topstem = stem(refs[source_id]["rows"][ranked[0][1]]["题目"])
        top = [i for _, i in ranked if stem(refs[source_id]["rows"][i]["题目"]) == topstem]
        other = [z for z, i in ranked if i not in top]
        if not other or ranked[0][0] - other[0] >= 0.12:
            return tuple(top), "PARAPHRASE_IDENTICAL_OPTIONS", ranked[0][0]
    return (), "UNMATCHED", ranked[0][0] if ranked else 0.0


def public_source_id(record):
    """Return only a neutral identifier; never write original local paths to outputs."""
    identifier = record.get("source_id")
    if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", identifier):
        raise ValueError("Each archive record requires a neutral file-level source_id")
    return identifier


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("benchmark", type=Path)
    parser.add_argument("archives", type=Path)
    parser.add_argument("private_output_directory", type=Path)
    args = parser.parse_args()
    index_references(json.loads(args.benchmark.read_text(encoding="utf-8-sig")))
    destination = args.private_output_directory
    destination.mkdir()
    audit, pairs, unmatched = [], {}, []
    file_ids = set()
    with args.archives.open(encoding="utf-8-sig") as archives, (destination / "aligned_sources.jsonl").open("x", encoding="utf-8") as out:
        for line in archives:
            source = json.loads(line)
            if source["model"].get("model_scope") != "EXPECTED":
                continue
            file_id = public_source_id(source)
            if file_id in file_ids:
                raise ValueError("An archive file ID occurs in more than one input record")
            file_ids.add(file_id)
            source_id = source["hint"]
            groups, rowmatch, possibilities = defaultdict(list), {}, {}
            content_counts = {
                ds: sum(stem(r.get("题目", "")) in si[ds] for r in source["rows"])
                for ds in refs
            }
            best = max(content_counts, key=content_counts.get)
            if content_counts[best] > max(20, content_counts[source_id] * 2):
                source["original_hint"] = source_id
                source_id = best
                source["hint"] = source_id

            for k, row in enumerate(source["rows"]):
                register(row.get("题目", ""))
                q, o = stem(row.get("题目", "")), opts(row)
                ids, method, sim = match(source_id, q, o)
                possibilities[k] = (ids, method, sim)
                if len(ids) == 1:
                    rowmatch[k] = (ids[0], method, sim)
                elif len(ids) > 1:
                    groups[ids].append(k)
                if method == "PARAPHRASE_IDENTICAL_OPTIONS":
                    pairs[(source_id, q, o)] = dict(
                        dataset=source_id,
                        source_stem=row["题目"],
                        frozen_stem=refs[source_id]["rows"][ids[0]]["题目"],
                        options=o,
                        similarity=sim,
                    )

            nref = len(refs[source_id]["rows"])
            verified_prefix = (
                len(source["rows"]) >= nref
                and sum(i in possibilities[i][0] for i in range(nref)) / nref >= 0.98
            )
            locked = set()
            if verified_prefix:
                for k in range(nref):
                    ids, method, sim = possibilities[k]
                    if k in ids:
                        rowmatch[k] = (
                            k,
                            method if len(ids) == 1 else "FULL_SEQUENCE_VERIFIED_ITEM_IDENTITY",
                            sim,
                        )
                        locked.add(k)

            srcopts = [opts(r) for r in source["rows"]]
            goldopts = [opts(r) for r in refs[source_id]["rows"]]
            for block in SequenceMatcher(None, srcopts, goldopts, autojunk=False).get_matching_blocks():
                if block.size < 3 or len(set(srcopts[block.a : block.a + block.size])) < 3:
                    continue
                for off in range(block.size):
                    k, i = block.a + off, block.b + off
                    ids, method, sim = possibilities[k]
                    if k in locked:
                        continue
                    if i in ids:
                        rowmatch[k] = (
                            i,
                            method if len(ids) == 1 else "STEM_OPTIONS_SEQUENCE_ANCHORED",
                            sim,
                        )
                    elif not ids and len(srcopts[k]) >= 3:
                        q = stem(source["rows"][k].get("题目", ""))
                        g = stem(refs[source_id]["rows"][i]["题目"])
                        sim = similarity(q, g)
                        if block.size >= 10 and sim >= 0.45:
                            rowmatch[k] = (i, "PARAPHRASE_OPTIONS_LONG_SEQUENCE", sim)
                            pairs[(source_id, q, srcopts[k])] = dict(
                                dataset=source_id,
                                source_stem=source["rows"][k]["题目"],
                                frozen_stem=refs[source_id]["rows"][i]["题目"],
                                options=srcopts[k],
                                similarity=sim,
                            )

            for _ in range(2):
                ordered = sorted(rowmatch)
                import bisect

                for k, (ids, _, sim) in possibilities.items():
                    if k in rowmatch or len(ids) < 2:
                        continue
                    pos = bisect.bisect_left(ordered, k)
                    lo = rowmatch[ordered[pos - 1]][0] if pos else -1
                    hi = rowmatch[ordered[pos]][0] if pos < len(ordered) else len(refs[source_id]["rows"])
                    fitting = [i for i in ids if lo < i < hi]
                    if len(fitting) == 1:
                        rowmatch[k] = (fitting[0], "STEM_OPTIONS_NEIGHBOR_ANCHORED", sim)

            anchors = [i for i, _, _ in rowmatch.values()]
            monotonic = all(a <= b for a, b in zip(anchors, anchors[1:]))
            for ids, ks in groups.items():
                if len(ids) == len(ks) and monotonic:
                    for k, i in zip(ks, sorted(ids)):
                        if k not in rowmatch:
                            rowmatch[k] = (i, "IDENTICAL_ITEM_OCCURRENCE_VERIFIED_ORDER", 1.0)

            mapped = []
            for k, row in enumerate(source["rows"]):
                if k in rowmatch:
                    i, method, sim = rowmatch[k]
                    mapped.append(dict(index=i, method=method, similarity=sim, row=row))
                else:
                    unmatched.append(
                        dict(
                            source_id=public_source_id(source),
                            model=source["model"]["canonical_model"],
                            dataset=source_id,
                            row=row["_row"],
                            stem=row.get("题目", "")[:1000],
                            options=opts(row),
                            has_raw=bool(row.get("模型原始回答")),
                        )
                    )

            audit.append(
                dict(
                    source_id=public_source_id(source),
                    model=source["model"]["canonical_model"],
                    dataset=source_id,
                    rows=len(source["rows"]),
                    mapped=len(mapped),
                    unique=len(set(x["index"] for x in mapped)),
                    monotonic=monotonic,
                    unmatched=len(source["rows"]) - len(mapped),
                    methods=dict(Counter(x["method"] for x in mapped)),
                )
            )
            metadata = {key: source[key] for key in ("original_hint", "representation", "selection_order") if key in source}
            metadata.update(source_id=file_id, hint=source_id, model={
                "canonical_model": source["model"]["canonical_model"],
                "model_scope": "EXPECTED"
            }, mapped=mapped)
            out.write(json.dumps(metadata, ensure_ascii=False) + "\n")

    (destination / "join_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf8")
    (destination / "paraphrase_pairs.json").write_text(json.dumps(list(pairs.values()), ensure_ascii=False, indent=2), encoding="utf8")
    (destination / "unmatched_rows.json").write_text(json.dumps(unmatched, ensure_ascii=False), encoding="utf8")
    print("mapped", sum(x["mapped"] for x in audit), "paraphrase unique", len(pairs), "unmatched", len(unmatched))


if __name__ == "__main__":
    main()

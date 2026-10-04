#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
.gram 自检：把构建输入里的每个 n-gram 逐条查回，验证 value 完全一致。

这是对「自己实现的构建器是否真的可用」最直接的证据：
若 Darts 双数组有任何位域或寻址错误，逐条回查必然大面积失败。
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gram_format import Gram, encode  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=".gram 逐条回查自检")
    ap.add_argument("--gram", required=True)
    ap.add_argument("--tsv", required=True,
                    help="构建时用的 TSV（未过滤的原始统计）")
    ap.add_argument("--min-count-2", type=int, default=2)
    ap.add_argument("--min-count-3", type=int, default=2)
    ap.add_argument("--min-count-4", type=int, default=2)
    ap.add_argument("--min-count-5", type=int, default=2)
    ap.add_argument("--min-count-6", type=int, default=2)
    ap.add_argument("--value-multiplier", type=float, default=1.0)
    ap.add_argument("--limit", type=int, default=0,
                    help="只抽查前 N 条（0 表示全查）")
    args = ap.parse_args()

    import math
    mins = [args.min_count_2, args.min_count_3, args.min_count_4,
            args.min_count_5, args.min_count_6]

    g = Gram(args.gram)
    print("模型 %s: %d 单元, 数组起点 %d, 大小校验 %s"
          % (Path(args.gram).name, g.size, g.array_off,
             "OK" if g.size_ok else "FAIL"))

    checked = ok = 0
    fails = []
    for line in Path(args.tsv).open(encoding="utf-8", errors="ignore"):
        line = line.rstrip("\n")
        if not line or "\t" not in line:
            continue
        text, cnt = line.split("\t")
        try:
            n = int(float(cnt))
        except ValueError:
            continue
        order = len(text)
        if order < 2 or order > 6:
            continue
        if n < mins[order - 2]:
            continue
        scaled = n * args.value_multiplier
        expect = int(math.log(scaled) * 10000) if scaled > 0 else 0
        expect = max(0, expect)

        key = encode(text)
        hits = g.lookup("", text)
        got = None
        for val, length in hits:
            if length == len(key):
                got = val
                break
        checked += 1
        if got == expect:
            ok += 1
        elif len(fails) < 10:
            fails.append((text, expect, got))
        if args.limit and checked >= args.limit:
            break

    print("逐条回查: %d / %d 通过 (%.2f%%)"
          % (ok, checked, 100.0 * ok / max(1, checked)))
    for text, expect, got in fails:
        print("  FAIL %s expect=%s got=%s" % (text, expect, got))
    return 0 if ok == checked else 1


if __name__ == "__main__":
    raise SystemExit(main())

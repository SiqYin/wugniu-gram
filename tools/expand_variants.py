#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把一个字形的 n-gram 表扩展成「多輸出字形標準」都能命中的表。

爲什麼需要這個
--------------
librime 查語法模型時，上下文與候選詞的來源字形**不是同一套**。
看 librime/plugins/octagram 與 src/rime/gear/poet.cc：

    const string& context =
        candidate.empty() ? preceding_text : candidate.context();
    double weight = candidate.weight +
                    Grammar::Evaluate(context, entry->text, entry->weight,
                                      is_rear, grammar_.get());

* `preceding_text` 來自
  `engine->context()->commit_history().latest_text()` 或
  `composition().GetTextBefore(start)` —— 即**已上屏的文字**，
  已經過 simplifier / opencc 濾鏡轉換，是**用戶選定个字形標準**。
* `entry->text` 是 `DictEntry` 的原文 —— **詞庫原生字形**，
  濾鏡在 poet 之後才跑，所以候選詞這一側**未經轉換**。

濾鏡在 translator（含 poet 句子合成）之後才執行，故查表發生在「已轉換的
上文 ＋ 未轉換的候選詞」之間。若模型只存一種字形，用戶切到別个字形標準
就會大批查不到 —— 表現爲模型「忽然不靈」，但不報錯。

本腳本的做法
------------
對每條長度 k 的 n-gram，枚舉「前 j 字已轉換、後 k-j 字保持詞庫原形」的
全部切分（j = 0..k），分別套用各目標字形表：

    變體 = { 前 j 字轉成字形 F + 其餘保持原形 | j = 0..k, F ∈ 各目標字形 }

j=0 即原形，故原形天然包含在內。`$` 句末標記不參與轉換。

用法
----
  python expand_variants.py --input ngram.tsv --output ngram_multi.tsv \
      --table wy=wugniu_suwu/opencc/SWCharacters.txt \
      --table hans=wugniu_suwu/opencc/TSCharacters.txt

  --table NAME=PATH 可重複；NAME 只用于報告。
"""
import argparse
import collections
import sys
from pathlib import Path

SENTENCE_END = "$"


def load_table(path):
    """讀 OpenCC 文本字表。值含多候選時取首項（OpenCC 實際生效項）。"""
    table = {}
    skipped = 0
    for line in Path(path).open(encoding="utf-8", errors="ignore"):
        parts = line.rstrip("\n").split("\t")
        if len(parts) != 2:
            continue
        src, dst = parts
        if len(src) != 1:
            skipped += 1          # 詞組條目：需要分詞，本腳本只做逐字轉換
            continue
        dst = dst.split(" ")[0]   # 多候選取首項
        if len(dst) == 1:
            table[src] = dst
    return table, skipped


def variants(ngram, table):
    """前 j 字轉換、後 k-j 字保持原形；j = 0..k。返回集合。"""
    core = ngram
    tail = ""
    if core.endswith(SENTENCE_END):
        core = core[:-1]
        tail = SENTENCE_END
    k = len(core)
    out = set()
    for j in range(k + 1):
        out.add("".join(table.get(c, c) if i < j else c
                        for i, c in enumerate(core)) + tail)
    return out


def main():
    ap = argparse.ArgumentParser(description="n-gram 多字形標準擴展")
    ap.add_argument("--input", required=True, help="text<TAB>count 的 TSV")
    ap.add_argument("--output", required=True)
    ap.add_argument("--table", action="append", default=[],
                    help="NAME=PATH，可重複。PATH 爲 OpenCC 風格文本字表")
    ap.add_argument("--max-order", type=int, default=6)
    args = ap.parse_args()

    if not args.table:
        ap.error("至少需要一個 --table")

    tables = []
    for spec in args.table:
        if "=" not in spec:
            ap.error("--table 需爲 NAME=PATH 形式: %s" % spec)
        name, path = spec.split("=", 1)
        tab, skipped = load_table(path)
        tables.append((name, tab))
        print("字表 %-8s %d 条逐字映射（跳过 %d 条词组）"
              % (name, len(tab), skipped))

    counts = collections.Counter()
    n_in = 0
    for line in Path(args.input).open(encoding="utf-8", errors="ignore"):
        line = line.rstrip("\n")
        if not line or "\t" not in line:
            continue
        text, cnt = line.split("\t")
        if not (2 <= len(text) <= args.max_order):
            continue
        n_in += 1
        c = int(cnt)
        forms = {text}
        for _name, tab in tables:
            forms |= variants(text, tab)
        for f in forms:
            # 同一 key 取最大次數，避免多來源相加造成虛高
            if c > counts[f]:
                counts[f] = c

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with Path(args.output).open("w", encoding="utf-8") as fh:
        for text, c in sorted(counts.items(),
                              key=lambda kv: (len(kv[0]), -kv[1], kv[0])):
            fh.write("%s\t%d\n" % (text, c))

    print("\n輸入 %d 條 -> 擴展後 %d 條（%.2f 倍）"
          % (n_in, len(counts), len(counts) / max(1, n_in)))
    by_order = collections.Counter(len(t) for t in counts)
    for k in sorted(by_order):
        print("  %d-gram: %d" % (k, by_order[k]))
    print("已寫出 %s" % Path(args.output).resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

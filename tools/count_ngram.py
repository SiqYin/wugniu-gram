#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
吳語語料 → 字符 n-gram 頻次（TSV）

计数逻辑严格对齐 rime-corpus-processing 的 Rust 工具
(rime-gram/src/main.rs::count_text / finish_han_run)：

  * 只在「漢字連續段」内统计，非漢字字符（標點、拉丁、假名）作爲分隔
  * 每遇到一個漢字，統計所有以它結尾、長度 2..6 的 n-gram
  * 每段漢字結束時，追加 (末尾 size-1 字 + "$") 的 n-gram，size=2..6
    —— 這批 "$" 條目供 octagram 的 is_rear 判斷句末位置

字形：語料採用戶 schema 的 0 選項（漢字 / noop，即詞庫原生繁體標準）。
本腳本把混入的簡體殘留統一轉為詞庫標準繁體。

用法：
  python count_ngram.py --input a.txt --input b.txt --output ngram.tsv
"""
import argparse
import collections
import sys
from pathlib import Path

MAX_N = 6
SENTENCE_END = "$"

# 漢字區段：與 Rust 工具 encode_character 支持範圍一致
#   0x3400-0x4DBF 擴展A / 0x4E00-0x9FFF 基本區 / 0xF900-0xFAFF 兼容區
# 注意：Rust 工具不含擴展B(>=0x20000)，此處保持一致以免行爲分叉。
HAN_RANGES = ((0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF))

# 簡 → 詞庫標準繁體。僅覆蓋語料中實際出現的殘留簡體字。
# 候選均已在 wugniu_suwu 詞庫字集中核驗存在。
SIMP_TO_TRAD = {
    "吴": "吳", "语": "語", "装": "裝", "输": "輸", "苏": "蘇",
    "沪": "滬", "对": "對", "体": "體", "终": "終", "风": "風",
    "鹭": "鷺", "鸥": "鷗", "泼": "潑", "够": "夠", "即": "即",
    "卽": "即", "仓": "倉", "库": "庫", "标": "標", "让": "讓",
    "鹅": "鵝", "动": "動", "内": "內", "词": "詞", "转": "轉",
    "换": "換", "从": "從", "运": "運", "产": "產", "设": "設",
    "备": "備", "应": "應", "统": "統", "启": "啟", "韵": "韻",
    "虚": "虛", "没": "沒", "并": "並", "为": "爲", "来": "來",
}


def is_han(ch):
    o = ord(ch)
    return any(lo <= o <= hi for lo, hi in HAN_RANGES)


def to_trad(text):
    return "".join(SIMP_TO_TRAD.get(c, c) for c in text)


def han_runs(text):
    """把文本切成漢字連續段，非漢字作分隔。"""
    cur = []
    for ch in text:
        if is_han(ch):
            cur.append(ch)
        else:
            if cur:
                yield "".join(cur)
                cur = []
    if cur:
        yield "".join(cur)


def count_runs(text, counts, sentence_end=True):
    for run in han_runs(text):
        n = len(run)
        for i in range(n):
            for size in range(2, min(i + 1, MAX_N) + 1):
                counts[run[i - size + 1:i + 1]] += 1
        if not sentence_end:
            continue
        for size in range(2, min(n + 1, MAX_N) + 1):
            counts[run[n - (size - 1):] + SENTENCE_END] += 1


def read_words(path):
    """把 Rime 詞庫的詞頭逐行輸出（作爲補充語料）。"""
    words = []
    for line in Path(path).open(encoding="utf-8", errors="ignore"):
        if line.startswith("#") or line.startswith("---") or not line.strip():
            continue
        w = line.split("\t")[0].strip()
        if w:
            words.append(w)
    return words


def main():
    ap = argparse.ArgumentParser(description="漢字 n-gram 頻次統計")
    ap.add_argument("--input", action="append", default=[],
                    help="原始語料文本，可多次指定")
    ap.add_argument("--weight", action="append", type=int, default=[],
                    help="對應 --input 的重複次數（默認 1）")
    ap.add_argument("--dict-words", action="append", default=[],
                    help="Rime 詞庫，取詞頭作補充語料")
    ap.add_argument("--dict-weight", type=int, default=1,
                    help="詞庫語料重複次數（默認 1）")
    ap.add_argument("--no-trad", action="store_true",
                    help="不做簡→繁歸一（默認會做）")
    ap.add_argument("--dict-sentence-end", action="store_true",
                    help="爲詞庫補充語料生成 '$' 句末標記（默認關閉）。"
                         "詞庫是離散詞條，若每個詞條都標句末，"
                         "會讓 is_rear 判斷失效，故默認不生成")
    ap.add_argument("--output", required=True, help="輸出 TSV 路徑")
    args = ap.parse_args()

    if not args.input and not args.dict_words:
        ap.error("至少需要一個 --input 或 --dict-words")

    weights = list(args.weight)
    while len(weights) < len(args.input):
        weights.append(1)

    counts = collections.Counter()
    total_chars = 0

    for path, w in zip(args.input, weights):
        text = Path(path).read_text(encoding="utf-8", errors="ignore")
        if not args.no_trad:
            text = to_trad(text)
        n_han = sum(1 for c in text if is_han(c))
        for _ in range(max(1, w)):
            count_runs(text, counts)
        total_chars += n_han
        print("  [%s] %d 漢字, 權重 x%d" % (Path(path).name, n_han, w))

    sup_sentence_end = args.dict_sentence_end
    for path in args.dict_words:
        words = read_words(path)
        n_han = sum(1 for w in words for c in w if is_han(c))
        text = "\n".join(to_trad(w) for w in words) if not args.no_trad \
            else "\n".join(words)
        for _ in range(max(1, args.dict_weight)):
            count_runs(text, counts, sentence_end=sup_sentence_end)
        print("  [%s] %d 詞條 / %d 漢字, 權重 x%d%s"
              % (Path(path).name, len(words), n_han, args.dict_weight,
                 "" if sup_sentence_end else " (無句末標記)"))

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    by_order = collections.Counter()
    with out.open("w", encoding="utf-8") as f:
        for text, c in sorted(counts.items(),
                              key=lambda kv: (len(kv[0]), -kv[1], kv[0])):
            f.write("%s\t%d\n" % (text, c))
            by_order[len(text)] += 1

    print("\n語料共 %d 漢字，產出 n-gram 類型 %d："
          % (total_chars, len(counts)))
    for k in sorted(by_order):
        print("  %d-gram: %d" % (k, by_order[k]))
    print("已寫出 %s" % out.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

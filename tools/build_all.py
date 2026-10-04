#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一條命令走完整條流水線：抽取語料 → 統計 n-gram → 構建 .gram → 自檢。

用法：
  # 用倉庫自帶的語料（corpus/*.txt）
  python tools/build_all.py

  # 從 .docx 重新抽取（語料是私有的，不入庫）
  python tools/build_all.py --docx-dir "D:/Wu/Chrome/吳語語料"

  # 指定補充詞庫（吳語詞庫，用於補高頻搭配）
  python tools/build_all.py --dict /path/wuphin.word.dict.yaml
"""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
TOOLS = ROOT / "tools"


def run(args, label):
    print("\n" + "=" * 62)
    print(">> " + label)
    print("=" * 62)
    r = subprocess.run([PY] + [str(a) for a in args])
    if r.returncode != 0:
        print("!! 步驟失敗：%s" % label, file=sys.stderr)
        raise SystemExit(r.returncode)


def main():
    ap = argparse.ArgumentParser(description="蘇滬混合腔語法模型：一鍵構建")
    ap.add_argument("--docx-dir",
                    help="含 .docx 的目錄；給出時先抽取為 corpus/*.txt")
    ap.add_argument("--corpus", action="append", default=[],
                    help="語料 txt，可多次指定（默認用 corpus/wu_*.txt）")
    ap.add_argument("--dict", action="append", default=[],
                    help="補充 Rime 詞庫，可多次指定")
    ap.add_argument("--table", action="append", default=[],
                    help="OpenCC 字形表 NAME=PATH，可多次指定。"
                         "給出時會把 n-gram 擴展成多種輸出字形標準都能命中"
                         "（見 expand_variants.py 的說明）")
    ap.add_argument("--language", default="wugniu_suwu")
    ap.add_argument("--min-count", type=int, default=2,
                    help="各階統一的 min-count（默認 2）")
    args = ap.parse_args()

    (ROOT / "work").mkdir(exist_ok=True)
    (ROOT / "out").mkdir(exist_ok=True)
    (ROOT / "corpus").mkdir(exist_ok=True)

    # 1. 抽取 docx
    if args.docx_dir:
        d = Path(args.docx_dir)
        pairs = [("吳語文本.docx", "wu_text.txt"),
                 ("吳語歌詞.docx", "wu_lyrics.txt")]
        for src, dst in pairs:
            if (d / src).is_file():
                run([TOOLS / "docx_to_txt.py", d / src,
                     ROOT / "corpus" / dst], "抽取語料 %s" % src)
            else:
                print("  ! 找不到 %s，跳過" % (d / src))

    corpus = [Path(c) for c in args.corpus] or sorted(
        (ROOT / "corpus").glob("wu_*.txt"))
    if not corpus:
        print("!! 沒有語料。請用 --corpus 指定，或用 --docx-dir 抽取。",
              file=sys.stderr)
        return 2
    print("\n語料文件：")
    for c in corpus:
        print("  " + str(c))

    # 2. 統計 n-gram
    ngram_tsv = ROOT / "work" / "ngram.tsv"
    cmd = [TOOLS / "count_ngram.py"]
    for c in corpus:
        cmd += ["--input", c]
    for d in args.dict:
        cmd += ["--dict-words", d]
    cmd += ["--output", ngram_tsv]
    run(cmd, "統計字符 n-gram")

    # 2.5 多字形標準擴展
    build_tsv = ngram_tsv
    if args.table:
        build_tsv = ROOT / "work" / "ngram_multi.tsv"
        cmd = [TOOLS / "expand_variants.py", "--input", ngram_tsv,
               "--output", build_tsv]
        for t in args.table:
            cmd += ["--table", t]
        run(cmd, "擴展多字形標準（吳語漢字 / 簡體 等）")

    # 3. 構建 .gram
    gram = ROOT / "out" / (args.language + ".gram")
    m = args.min_count
    cmd = [TOOLS / "build_gram.py", "--input", build_tsv,
           "--language", args.language, "--output", gram]
    for o in range(2, 7):
        cmd += ["--min-count-%d" % o, str(m)]
    run(cmd, "構建 .gram")

    # 4. 自檢
    cmd = [TOOLS / "verify_gram.py", "--gram", gram, "--tsv", build_tsv]
    for o in range(2, 7):
        cmd += ["--min-count-%d" % o, str(m)]
    run(cmd, "逐條回查自檢")

    print("\n" + "=" * 62)
    print("完成。產物：%s" % gram)
    print("部署：把 %s 與 grammar.yaml 複製到 %%APPDATA%%\\Rime，"
          % gram.name)
    print("      並按 wugniu_suwu.custom.yaml 配置後「重新部署」。")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

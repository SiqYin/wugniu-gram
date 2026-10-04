#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 .docx 抽取纯文本（每段一行）。

docx 是 zip，正文在 word/document.xml。不依赖 python-docx，
只用标准库，避免额外依赖。
"""
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def extract(path):
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml")
    root = ET.fromstring(xml)
    paras = []
    for p in root.iter(W + "p"):
        text = "".join(t.text or "" for t in p.iter(W + "t"))
        paras.append(text)
    return paras


def main():
    if len(sys.argv) < 3:
        print("usage: docx_to_txt.py <in.docx> <out.txt>")
        return 2
    src, dst = sys.argv[1], sys.argv[2]
    paras = extract(src)
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    with Path(dst).open("w", encoding="utf-8") as f:
        for p in paras:
            f.write(p + "\n")
    nonempty = sum(1 for p in paras if p.strip())
    print("%s -> %s : %d 段（非空 %d）"
          % (Path(src).name, dst, len(paras), nonempty))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

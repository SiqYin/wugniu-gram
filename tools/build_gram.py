#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从字符 n-gram 频次构建 Rime octagram .gram 文件。

替代官方 build_grammar.exe（该二进制约 MinGW 运行库，本机无法运行）。
本实现按 darts.h 的 DoubleArrayBuilderUnit 位域与读写语义复刻，
输出格式与官方工具一致：44 字节头 + Darts 双数组。

用法：
  python build_gram.py --input ngram.tsv --language wu-suhu --output wu-suhu.gram
"""
import argparse
import math
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gram_format import (  # noqa: E402
    GRAM_FORMAT, KFORMAT_MAX, encode, make_leaf_unit, make_node_unit)


class TrieNode:
    __slots__ = ("children", "value", "base")

    def __init__(self):
        self.children = {}
        self.value = None
        self.base = 0


def build_trie(entries):
    """entries: iterable of (text, value). 返回 root 与节点总数。"""
    root = TrieNode()
    n_nodes = 1
    for text, value in entries:
        key = encode(text)
        if b"\x00" in key:
            raise ValueError("encoded key contains NUL: %r" % text)
        node = root
        for b in key:
            nxt = node.children.get(b)
            if nxt is None:
                nxt = TrieNode()
                node.children[b] = nxt
                n_nodes += 1
            node = nxt
        node.value = value
    return root, n_nodes


class DoubleArrayBuilder:
    def __init__(self, capacity):
        self.used = bytearray(capacity)
        self.units = [0] * capacity
        self.used[0] = 1          # 索引 0 归根节点
        self.cursor = 1

    def _grow(self, need):
        if need <= len(self.used):
            return
        size = len(self.used)
        while size < need:
            size *= 2
        self.used.extend(bytearray(size - len(self.used)))
        self.units.extend([0] * (size - len(self.units)))

    def find_base(self, labels, terminal):
        """找一个 base，使 {base} ∪ {base^c} 全部空闲。"""
        b = self.cursor
        used = self.used
        while True:
            need = [b ^ c for c in labels]
            if terminal:
                need.append(b)
            hi = max(need) if need else b
            self._grow(hi + 2)
            used = self.used
            if not any(used[p] for p in need):
                return b
            b += 1

    def assign(self, node, index, label):
        """index: 本节点在数组中的位置; label: 入边字节（根为 0）。"""
        labels = list(node.children.keys())
        labels.sort()
        terminal = node.value is not None
        b = self.find_base(labels, terminal)
        node.base = b
        if b >= self.cursor:
            self.cursor = b
        self.units[index] = make_node_unit(label, terminal, index ^ b)
        if terminal:
            self.used[b] = 1
            self.units[b] = make_leaf_unit(node.value)
        for c in labels:
            p = b ^ c
            self.used[p] = 1
        for c in labels:
            child = node.children[c]
            self.assign(child, b ^ c, c)

    def finish(self):
        # 去掉尾部空洞
        last = len(self.units)
        while last > 1 and self.units[last - 1] == 0 and not self.used[last - 1]:
            last -= 1
        return self.units[:last]


def write_gram(path, units):
    buf = bytearray()
    fmt = GRAM_FORMAT.encode("ascii")
    buf += fmt + b"\x00" * (KFORMAT_MAX - len(fmt))
    buf += struct.pack("<II", 0, len(units))
    buf += struct.pack("<i", 4)          # array 起点 = 40 + 4 = 44
    for u in units:
        buf += struct.pack("<I", u)
    Path(path).write_bytes(buf)
    return len(buf)


def load_entries(path, min_counts):
    """读取 'text<TAB>count' 格式，按阶应用 min_count 过滤。"""
    out = []
    skipped = 0
    for line in Path(path).open(encoding="utf-8", errors="ignore"):
        line = line.rstrip("\n")
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) != 2:
            continue
        text, cnt = parts[0], parts[1]
        try:
            n = int(float(cnt))
        except ValueError:
            continue
        order = len(text)
        if order < 2 or order > 6:
            continue
        if n < min_counts[order - 2]:
            skipped += 1
            continue
        out.append((text, n))
    return out, skipped


def main():
    ap = argparse.ArgumentParser(
        description="从 n-gram TSV 构建 Rime .gram（纯 Python 实现）")
    ap.add_argument("--input", required=True, help="text<TAB>count 格式的 TSV")
    ap.add_argument("--language", default="wu-suhu", help=".gram 文件名前缀")
    ap.add_argument("--output", help="输出路径，默认 <language>.gram")
    ap.add_argument("--min-count-2", type=int, default=2)
    ap.add_argument("--min-count-3", type=int, default=2)
    ap.add_argument("--min-count-4", type=int, default=2)
    ap.add_argument("--min-count-5", type=int, default=2)
    ap.add_argument("--min-count-6", type=int, default=2)
    ap.add_argument("--value-multiplier", type=float, default=1.0,
                    help="value 前对 count 乘的系数，>1 让模型更强势")
    ap.add_argument("--capacity", type=int, default=None)
    args = ap.parse_args()

    min_counts = [args.min_count_2, args.min_count_3, args.min_count_4,
                  args.min_count_5, args.min_count_6]
    entries, skipped = load_entries(args.input, min_counts)
    if not entries:
        print("ERROR: 没有通过阈值的条目，请降低 min-count", file=sys.stderr)
        return 1

    print("输入条目 %d 条（低于阈值被滤 %d 条）" % (len(entries), skipped))
    by_order = {}
    for text, cnt in entries:
        by_order.setdefault(len(text), 0)
        by_order[len(text)] += 1
    for k in sorted(by_order):
        print("  %d-gram: %d 条" % (k, by_order[k]))

    mult = args.value_multiplier
    prepared = []
    for text, cnt in entries:
        scaled = cnt * mult
        v = int(math.log(scaled) * 10000) if scaled > 0 else 0
        prepared.append((text, max(0, v)))

    root, n_nodes = build_trie(prepared)
    print("trie 节点数 %d" % n_nodes)
    cap = args.capacity or max(1024, n_nodes * 3)
    builder = DoubleArrayBuilder(cap)
    builder.assign(root, 0, 0)
    units = builder.finish()
    print("双数组单元数 %d (%.2f MiB)" % (len(units), len(units) * 4 / 1048576))

    # darts.h 的 set_offset 在 offset >= 2^21 时会切到「左移 8」的编码，
    # 该编码会丢弃低 8 位，必须配合 256 对齐才正确。本实现未做块对齐，
    # 因此在 2^21 单元（约 8 MiB 数组）以内是安全的。
    if len(units) >= (1 << 21):
        print("ERROR: 数组 %d 单元，已达到 darts offset 编码的 2^21 边界。"
              % len(units), file=sys.stderr)
        print("       需为 set_offset 增加 256 对齐逻辑后才能构建更大模型。",
              file=sys.stderr)
        return 1

    out = args.output or (args.language + ".gram")
    size = write_gram(out, units)
    print("已写出 %s (%d 字节)" % (out, size))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

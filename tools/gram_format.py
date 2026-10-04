#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rime octagram .gram 文件格式读写（Darts 双数组 trie）

格式（依据 librime-octagram/src/gram_db.{h,cc} + darts.h 复刻）：

  偏移 0    : char format[32]      "Rime::Grammar/1.0" 零填充
  偏移 32   : uint32 db_checksum   实测恒为 0
  偏移 36   : uint32 unit_count    双数组单元个数（不是字节数）
  偏移 40   : int32  offset_rel    相对本字段的偏移，实测恒为 4 -> 数据在 44
  偏移 44   : unit[unit_count]     每单元 4 字节小端

  文件大小恒等于 44 + unit_count * 4（已用两个真实模型验证）

单元（uint32）位域，来自 darts.h 的 DoubleArrayBuilderUnit：
  bit31    : 叶子标志（该单元存 value）
  bit8     : has_leaf（本节点是某个 key 的结尾）
  bit0-7   : label（边上的字节）
  bit10+   : offset；若 bit9 置位则再左移 8
  节点寻址：base = node ^ offset(node)；子节点 = base ^ label
"""
import struct
import sys
from pathlib import Path

KFORMAT_MAX = 32
GRAM_FORMAT = "Rime::Grammar/1.0"
KVALUE_SCALE = 10000
KMAX_RESULTS = 8
KSENTENCE_END = "$"
KMAX_ENCODED_UNICODE = 8


def encode(s):
    """复刻 librime-octagram/src/gram_encoding.cc 的 grammar::encode()。

    这是 .gram 的 key 编码，不是 UTF-8。基本区汉字占 2 字节，
    扩展 A/B 区汉字占 4 字节，非 BMP 最高 4 字节。
    以 0xE0|n 前缀区分变长序列，因此编码结果不含 0x00，可作 C 字符串。
    """
    out = bytearray()
    for ch in s:
        u = ord(ch)
        if u < 0x80:
            out.append(0xE0 if u == 0 else u)
        elif 0x4000 <= u < 0xA000:
            if (u & 0xFF) == 0:
                out.append(0xE1)
                out.append((u >> 8) + 0x40)
            else:
                out.append((u >> 8) + 0x40)
                out.append(u & 0xFF)
        else:
            bits = 32
            uu = u
            while bits > 0 and (uu & 0xFE000000) == 0:
                bits -= 7
                uu <<= 7
            n = (bits + 6) // 7
            out.append(0xE0 | n)
            while n > 0:
                n -= 1
                out.append(((uu >> 25) & 0x7F) | 0x80)
                uu <<= 7
    return bytes(out)


def u_label(u):
    return u & ((1 << 31) | 0xFF)


def u_has_leaf(u):
    return (u >> 8) & 1


def u_value(u):
    return u & ((1 << 31) - 1)


def u_offset(u):
    return (u >> 10) << (((u & (1 << 9)) >> 6))


def make_node_unit(label, has_leaf, offset):
    """按 darts.h 的 set_label/set_has_leaf/set_offset 顺序组装单元。"""
    if offset >= (1 << 29):
        raise ValueError("offset too large: %d" % offset)
    unit = 0
    unit = (unit & ~0xFF) | (label & 0xFF)          # set_label
    if has_leaf:                                     # set_has_leaf
        unit |= 1 << 8
    unit &= (1 << 31) | (1 << 8) | 0xFF              # set_offset 的保留掩码
    if offset < (1 << 21):
        unit |= offset << 10
    else:
        unit |= (offset << 2) | (1 << 9)
    return unit


def make_leaf_unit(value):
    """叶子单元：bit31 置位，低 31 位存 value。"""
    v = int(value)
    if v < 0:
        v = 0
    if v >= (1 << 31):
        raise ValueError("value too large: %d" % v)
    return v | (1 << 31)


def count_to_value(count):
    """复刻 GramDb::Build 的 value = max(0, int(log(count) * 10000))。"""
    import math
    if count < 1:
        return 0
    return int(math.log(count) * KVALUE_SCALE)


def value_to_count(value):
    import math
    return math.exp(value / KVALUE_SCALE)


class Gram:
    """只读的 .gram 解析器，用于校验构建结果。"""

    def __init__(self, path):
        self.path = str(path)
        data = Path(path).read_bytes()
        self.data = data
        self.format = data[:KFORMAT_MAX].split(b"\x00")[0].decode("ascii", "replace")
        self.checksum, self.size = struct.unpack_from("<II", data, KFORMAT_MAX)
        rel = struct.unpack_from("<i", data, KFORMAT_MAX + 8)[0]
        self.array_off = KFORMAT_MAX + 8 + rel
        expect = self.array_off + self.size * 4
        self.size_ok = (expect == len(data))
        if not self.size_ok:
            raise ValueError(
                "size mismatch: header implies %d bytes, file has %d"
                % (expect, len(data)))

    def unit(self, i):
        return struct.unpack_from("<I", self.data, self.array_off + i * 4)[0]

    def traverse(self, ctx_bytes):
        """返回 (node_pos, 已匹配字节数)。"""
        node = 0
        u = self.unit(0)
        for i, c in enumerate(ctx_bytes):
            node ^= u_offset(u) ^ c
            if node >= self.size:
                return 0, i
            u = self.unit(node)
            if u_label(u) != c:
                return 0, i
        return node, len(ctx_bytes)

    def common_prefix(self, node, word_bytes, limit=KMAX_RESULTS):
        """从 node 出发做前缀检索，返回 [(value, 匹配字节数), ...]。"""
        res = []
        u = self.unit(node)
        node ^= u_offset(u)
        for i, c in enumerate(word_bytes):
            node ^= c
            if node >= self.size:
                return res
            u = self.unit(node)
            if u_label(u) != c:
                return res
            node ^= u_offset(u)
            if u_has_leaf(u) and len(res) < limit:
                res.append((u_value(self.unit(node)), i + 1))
        return res

    def lookup(self, context, word):
        """对齐 octagram 的查表：先用 context 走到底，再搜 word 的前缀。"""
        ctx = encode(context)
        node, matched = self.traverse(ctx)
        if matched != len(ctx):
            return []
        return self.common_prefix(node, encode(word))


def _main():
    if len(sys.argv) < 3:
        print("usage: gram_format.py <file.gram> <str> [str...]")
        raise SystemExit(2)
    g = Gram(sys.argv[1])
    print("format  :", g.format)
    print("checksum:", g.checksum)
    print("units   : %d (%.1f MiB array)" % (g.size, g.size * 4 / 1048576))
    print("layout  : array starts at %d, size check %s"
          % (g.array_off, "OK" if g.size_ok else "FAIL"))
    for q in sys.argv[2:]:
        hits = g.lookup("", q)
        if not hits:
            print("  %-8s : (miss)" % q)
        for val, length in hits:
            print("  %-8s : bytes=%d value=%d count~%.1f"
                  % (q, length, val, value_to_count(val)))
    # 顺带统计有多少 key 以句子结尾标记结尾
    print("  '$' =", g.lookup("", "$"))


if __name__ == "__main__":
    _main()

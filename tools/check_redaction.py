#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""提交前自检：扫描仓库内文件，确认没有本地环境指纹或个人账号数据。

大赛要求提交公开仓库，公开前必须确保不泄漏：
    - 本机系统用户名 / 家目录路径
    - 完整会话 ID
    - 账号余额等个人数据
    - 真实 MCP 凭证

用法：
    python tools/check_redaction.py           # 扫描当前目录
    python tools/check_redaction.py --root .. # 扫描指定目录

退出码 0 表示干净，1 表示发现残留。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SKIP_DIRS = {".git", "__pycache__", ".idea", ".vscode", ".venv", "node_modules"}
SKIP_SUFFIX = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pyc", ".woff", ".woff2"}

# 只匹配「真实的本地指纹」，而不是代码里的通用正则字面量。
# 例如脚本里出现 r"[A-Za-z]:[\\/]Users[\\/]" 属于通用模式，不算泄漏；
# 但出现「盘符 + 用户目录 + 具体用户名」的完整路径就是泄漏。
PATTERNS: dict[str, re.Pattern[str]] = {
    "Windows 用户路径（含具体用户名）": re.compile(r"[A-Za-z]:[\\/]Users[\\/][A-Za-z0-9_.-]+"),
    "类 Unix 家目录路径": re.compile(r"/(?:Users|home)/[A-Za-z0-9_.-]+"),
    "完整会话 UUID": re.compile(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    ),
    "账号积分余额": re.compile(r"(?:累计|可用)\s*\d+(?:\.\d+)?\s*分"),
    "疑似真实令牌": re.compile(r"Bearer\s+[A-Za-z0-9\-_.]{20,}"),
    "环境变量以外的密钥字段": re.compile(
        r"[\"'](?:token|secret|apiKey|api_key|password)[\"']\s*:\s*[\"'][^\"'$<{]{8,}[\"']",
        re.I,
    ),
}


def main() -> int:
    ap = argparse.ArgumentParser(description="提交前的脱敏与凭证自检")
    ap.add_argument("--root", default=".", help="要扫描的目录")
    args = ap.parse_args()

    root = Path(args.root)
    hits: list[tuple[Path, str, str]] = []
    scanned = 0

    for f in sorted(root.rglob("*")):
        if not f.is_file():
            continue
        if any(part in SKIP_DIRS for part in f.parts):
            continue
        if f.suffix.lower() in SKIP_SUFFIX:
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        scanned += 1
        for name, pat in PATTERNS.items():
            m = pat.search(text)
            if m:
                hits.append((f, name, m.group(0)))

    print(f"已扫描 {scanned} 个文本文件（{root.resolve()}）")
    if hits:
        print("\n发现以下需要处理的内容：")
        for f, name, sample in hits:
            print(f"  [残留] {f}  →  {name}：{sample[:60]!r}")
        print("\n请先处理后再提交公开仓库。")
        return 1

    print("[OK] 未发现本地路径、用户名、会话 ID、账号数据或真实凭证。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

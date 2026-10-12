#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""扫描麦当劳大赛的报名 Issue，做参赛规模与选题拥挤度统计。

主办方读取报名 Issue 用的是 GitHub 公开 REST API，本脚本用的是同一个接口，
所以任何人都能在本地复现这组数字，不需要任何凭证。

用法:
    python tools/scan_issues.py
    python tools/scan_issues.py --json out.json
"""
from __future__ import annotations

import argparse
import collections
import http.client
import json
import sys
import time
import urllib.error
import urllib.request

REPO = "M-China/mcd-developer-innovation-challenge"
API = f"https://api.github.com/repos/{REPO}/issues"
HEADERS = {
    "User-Agent": "mcrewind-issue-scanner/1.0",
    "Accept": "application/vnd.github+json",
}

THEMES = {
    "年报 / 复盘": ["年报", "复盘", "wrapped", "年度报告", "画像", "战绩", "账单"],
    "省钱 / 核价": ["省钱", "划算", "最优", "核价", "比价", "凑单", "满减", "省钱助"],
    "健康 / 营养": ["营养", "健康", "热量", "控卡", "碳水", "蛋白质", "减脂"],
    "积分 / 权益": ["积分", "兑换", "权益", "点数"],
    "情绪 / 人格": ["情绪", "人格", "mbti", "mcti", "玄学", "算命", "疗愈", "星座"],
    "无障碍 / 适老": ["无障碍", "适老", "a11y", "大字", "语音点餐"],
    "拼单 / 团餐": ["拼单", "团餐", "派对", "团长", "社交点餐", "一起点"],
    "时间 / 通勤": ["通勤", "jit", "深夜", "早餐", "时段", "预约", "零等待"],
    "地图 / 门店": ["地图", "门店", "打卡", "周边", "导航"],
    "游戏 / 娱乐": ["游戏", "arcade", "电影", "乐园", "博物馆", "盲盒", "抽奖"],
}


def fetch_page(page: int, per_page: int = 50, retries: int = 6) -> list[dict]:
    url = f"{API}?state=all&per_page={per_page}&page={page}"
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=60) as resp:
                chunks: list[bytes] = []
                while True:
                    block = resp.read(65536)
                    if not block:
                        break
                    chunks.append(block)
            return json.loads(b"".join(chunks).decode("utf-8"))
        except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError, ValueError) as exc:
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"第 {page} 页抓取失败: {last}")


def fetch_all(per_page: int = 50) -> list[dict]:
    out: list[dict] = []
    for page in range(1, 20):
        batch = fetch_page(page, per_page=per_page)
        if not batch:
            break
        out.extend(batch)
        if len(batch) < per_page:
            break
        time.sleep(0.4)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="把原始数据另存为 JSON")
    args = ap.parse_args()

    try:
        raw = fetch_all()
    except RuntimeError as exc:
        print(f"[失败] {exc}", file=sys.stderr)
        return 1

    issues = [i for i in raw if "pull_request" not in i]
    if not issues:
        print("[失败] 未抓到任何 Issue")
        return 1

    issues.sort(key=lambda i: i["number"])
    nums = [i["number"] for i in issues]
    print(f"仓库            : {REPO}")
    print(f"Issue 总数      : {len(issues)}（另有 PR {len(raw) - len(issues)} 条）")
    print(f"编号区间        : #{min(nums)} - #{max(nums)}")
    print(f"最早创建        : {min(i['created_at'] for i in issues)}")
    print(f"最晚创建        : {max(i['created_at'] for i in issues)}")

    authors = collections.Counter(i["user"]["login"] for i in issues)
    print(f"独立报名账号    : {len(authors)}")
    multi = [(a, c) for a, c in authors.most_common() if c > 1]
    if multi:
        print(f"提交多个项目的账号: {len(multi)} 个")
        for a, c in multi[:10]:
            print(f"    {a}: {c} 个")

    cmt = collections.Counter(i.get("comments", 0) for i in issues)
    print(f"评论数分布      : {dict(sorted(cmt.items()))}")
    print("                  （系统会在报名 Issue 下回复成功/失败，0 条=尚未被处理）")

    texts = [((i.get("title") or "") + " " + (i.get("body") or "")).lower() for i in issues]
    print("\n选题拥挤度（一个项目可命中多个主题）:")
    ranked = sorted(THEMES.items(), key=lambda kv: -sum(1 for t in texts if any(w in t for w in kv[1])))
    for name, words in ranked:
        n = sum(1 for t in texts if any(w in t for w in words))
        bar = "█" * min(40, n)
        print(f"    {name:<14} {n:>4}  {bar}")

    by_day = collections.Counter(i["created_at"][:10] for i in issues)
    print("\n按日新增（UTC，+8 为北京时间）:")
    for d in sorted(by_day):
        print(f"    {d}  {by_day[d]:>4}  {'█' * min(60, by_day[d])}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(issues, fh, ensure_ascii=False, indent=2)
        print(f"\n[输出] 原始数据已写入 {args.json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

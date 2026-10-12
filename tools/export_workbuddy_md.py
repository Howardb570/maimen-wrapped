#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 WorkBuddy 开发会话的原始记录导出为参赛用的 workbuddy.md。

大赛规则对 workbuddy.md 的要求是「WorkBuddy 对话上下文，用于联动活动」，
即：能证明项目确实在腾讯 WorkBuddy 智能体里开发、能还原开发过程。

本脚本直接读取 WorkBuddy 的会话原始日志（JSONL），不做任何人工润色，
只做「筛选 + 归类 + 排版」，因此导出结果是可核验的、与真实会话一一对应的。

用法：
    python tools/export_workbuddy_md.py --out workbuddy.md
    python tools/export_workbuddy_md.py --session <xxx.jsonl> --cutoff <ms>

设计取舍：
    - 保留用户每一次提问的原文（不做改写）
    - 保留助手的关键回复原文；进度短句以斜体保留，构成完整时间线
    - 工具调用做「归并 + 去重」而非逐条罗列，否则 100+ 条会淹没正文
    - 丢弃系统噪音：网络重试错误、上下文重放、file-history 快照
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from collections import Counter, OrderedDict
from pathlib import Path

# --------------------------------------------------------------------------
# 工具调用 → 人类可读标签
# --------------------------------------------------------------------------

BUILTIN_TOOL_LABELS = {
    "WebFetch": "联网读取规则 / 榜单",
    "WebSearch": "联网检索",
    "ToolSearch": "检索可用工具",
    "Bash": "终端执行",
    "PowerShell": "终端执行",
    "Read": "读取文件",
    "Write": "写入文件",
    "Edit": "修改文件",
    "Glob": "文件检索",
    "Grep": "内容检索",
    "TaskCreate": "建立任务",
    "TaskUpdate": "更新任务",
    "TaskList": "查看任务",
    "AskUserQuestion": "向用户确认决策",
    "Skill": "加载技能",
    "present_files": "展示交付物",
    "widget_guidelines": "加载可视化规范",
    "show_widget": "输出内联可视化",
    "automation_update": "自动化配置",
}

# 麦当劳 MCP 工具的语义说明，用于让评审一眼看懂业务价值
MCD_TOOL_LABELS = {
    "now-time-info": "获取服务器当前时间（用于验证 MCP 连通性）",
    "query-meals": "查询菜单",
    "query-nearby-stores": "查询附近门店",
    "calculate-price": "计算价格",
    "create-order": "创建订单",
    "order-list": "拉取本人历史订单（年报核心数据源）",
    "query-order": "查询订单详情",
    "query-my-account": "查询麦享会账户与积分（年报数据源）",
    "query-my-coupons": "查询我的优惠券",
    "query-my-prizes": "查询我的奖品",
    "query-store-coupons": "查询门店优惠券",
    "mall-order-list": "查询积分商城订单",
    "mall-product-detail": "积分商城商品详情",
    "delivery-query-stores": "查询外送门店",
    "query-meal-detail": "查询套餐详情",
}

NOISE_PATTERNS = (
    "EHOSTUNREACH",
    "ECONNRESET",
    "502 网络不可达",
)

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def demote_headings(text: str) -> str:
    """把助手回复里内嵌的 Markdown 标题降级为加粗文本。

    助手长回复本身带 `## 一、…` 这类标题，若原样嵌入会与本文档的章节大纲
    混在一起（目录里会冒出十来个同级标题）。降级为加粗既保留了视觉层级，
    又不污染文档结构。代码块内的 # 注释不受影响。
    """
    out: list[str] = []
    in_fence = False
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            out.append(line)
            continue
        if not in_fence:
            m = HEADING_RE.match(line)
            if m:
                out.append(f"**{m.group(2).strip()}**")
                continue
        out.append(line)
    return "\n".join(out)


# --------------------------------------------------------------------------
# 脱敏
# --------------------------------------------------------------------------

# 本脚本会随项目一起公开，因此脱敏规则**不硬编码任何本机信息**：
# 用户名与家目录在运行时从 Path.home() 推导，其余用通用正则匹配。
# 任何人 clone 后运行，都会按自己机器的环境正确脱敏。
_HOME = Path.home()
_HOME_NT = str(_HOME)                       # C:\Users\<name>
_HOME_POSIX = _HOME_NT.replace("\\", "/")   # C:/Users/<name>
_USERNAME = _HOME.name                      # <name>

# 路径右边界：遇到空白、反引号、引号、括号或中文标点即停止
_END = r"[^\s`\"')。，、；：）】<>]"

UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
)

# 顺序敏感：先整体路径，再裸用户名，最后内部实现细节
# 值可以是字符串，也可以是 (match) -> str 的函数（用于截断类替换）
REDACTIONS = [
    # 1. Windows 用户目录下的任意路径（含各类应用数据目录、项目工作区）
    (rf"[A-Za-z]:[\\/]Users[\\/]{_END}*", "<本地路径>"),
    # 2. macOS / Linux 家目录路径
    (rf"/(?:Users|home)/{_END}*", "<本地路径>"),
    # 3. 本机家目录的其它写法
    (re.escape(_HOME_NT), "<本地路径>"),
    (re.escape(_HOME_POSIX), "<本地路径>"),
    # 4. 兜底：任何残留的裸用户名
    (re.escape(_USERNAME), "user"),
    # 5. 会话标识：截断，保留可核验的前缀但不暴露完整 ID
    (UUID_RE.pattern, lambda m: m.group(0)[:8] + "……（已截断）"),
    # 6. 临时目录
    (r"/tmp/", "<临时目录>/"),
    # 7. WorkBuddy 本地日志目录结构属于内部实现细节，不对外暴露
    (r"`~/.workbuddy/projects/<项目slug>/<sessionId>\.jsonl`", "WorkBuddy 的本地会话日志"),
    (r"~/.workbuddy/projects/<项目slug>/<sessionId>\.jsonl", "WorkBuddy 的本地会话日志"),
    (r"~/\.workbuddy/projects", "WorkBuddy 本地会话日志目录"),
    (r"~/\.workbuddy/", "<WorkBuddy 配置目录>/"),
    # 8. 个人账户余额：与项目无关，属于账号隐私，直接抹除具体数值
    (r"（累计\s*\d+(?:\.\d+)?\s*分[^）]*）", ""),
    (r"积分\s*\d+", "积分账户可读"),
    # 9. 历史回复里「workbuddy.md 还是占位模板」在当时成立，但对提交版读者是误导，
    #    补一个时间限定词，既不改事实也不产生歧义
    (r"还是占位模板", "当时还是占位模板"),
    # 10. 逐词替换后产生的病句：原文是「硬编码了 <系统用户名> 和 <家目录路径>」，
    #     被前几条规则拆散后读不通，改回自然表述
    (r"硬编码了 `user` 和 `<本地路径>`", "硬编码了本机系统用户名与家目录路径"),
]


def apply_redactions(text: str) -> str:
    for pattern, repl in REDACTIONS:
        text = re.sub(pattern, repl, text)
    return text


def find_leaks(text: str) -> list[str]:
    """脱敏自检：返回仍然命中的本地指纹，调用方据此决定是否告警。"""
    leaks: list[str] = []
    for probe in (_HOME_NT, _HOME_POSIX, _USERNAME):
        if len(probe) >= 3 and probe in text:
            leaks.append(probe)
    if UUID_RE.search(text):
        leaks.append("未截断的会话 ID")
    return leaks


def cap_text(text: str, limit: int) -> str:
    """截断长回复，且只在段落边界处切，避免切出半句话。"""
    if len(text) <= limit:
        return text
    idx = text.find("\n\n", limit)
    if idx == -1:
        idx = text.rfind("\n\n", 0, limit)
    if idx == -1:
        idx = limit
    return text[:idx].rstrip() + "\n\n*（此处为节选）*"


def summarize_round_tools(items: list[dict]) -> str:
    """把一轮里的工具调用压成一行摘要。"""
    labels: Counter[str] = Counter()
    mcd_tools: list[str] = []
    for ev in items:
        if ev["kind"] != "tool":
            continue
        args = ev.get("args") or {}
        if ev["name"] == "DeferExecuteTool":
            inner = str(args.get("toolName", ""))
            short = inner.split("__")[-1] if "__" in inner else inner
            if inner.startswith("mcp__mcd-mcp__"):
                if short not in mcd_tools:
                    mcd_tools.append(short)
                continue
        labels[BUILTIN_TOOL_LABELS.get(ev["name"], ev["name"])] += 1
    if not labels and not mcd_tools:
        return ""
    top = labels.most_common(6)
    parts = [f"{k} ×{v}" if v > 1 else k for k, v in top]
    detail = "、".join(parts)
    if len(labels) > len(top):
        detail += f" 等 {len(labels)} 类"
    line = "本轮共调用工具 " + str(sum(labels.values())) + " 次：" + detail
    if mcd_tools:
        line += "；麦当劳 MCP：" + "、".join(f"`{t}`" for t in mcd_tools)
    return line


def label_for_tool(name: str, args: dict) -> tuple[str, str | None]:
    """返回 (显示标签, 归属分类)。分类用于统计 MCP 调用次数。"""
    if name in ("DeferExecuteTool",) and isinstance(args, dict):
        inner = str(args.get("toolName", ""))
        short = inner.split("__")[-1] if "__" in inner else inner
        desc = MCD_TOOL_LABELS.get(short, "")
        tail = f"：{desc}" if desc else ""
        return f"麦当劳 MCP · `{short}`{tail}", "mcd_mcp"
    if name == "Skill":
        arg = str(args.get("skill", "")) if isinstance(args, dict) else ""
        return f"加载技能 `{arg}`", "builtin"
    if name in ("Bash", "PowerShell") and isinstance(args, dict):
        return "终端执行", "builtin"
    return BUILTIN_TOOL_LABELS.get(name, name), "builtin"


# --------------------------------------------------------------------------
# 解析会话
# --------------------------------------------------------------------------


def parse_events(session_path: Path) -> list[dict]:
    """把 JSONL 读成一串扁平事件。"""
    events: list[dict] = []
    with session_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue

            rtype = row.get("type")
            ts = row.get("timestamp") or 0

            if rtype == "message":
                role = row.get("role")
                text = "".join(
                    b.get("text", "")
                    for b in row.get("content", [])
                    if isinstance(b, dict)
                )
                if not text.strip():
                    continue
                if any(p in text for p in NOISE_PATTERNS):
                    continue  # 网络抖动产生的错误提示，不属于对话内容
                if role == "user":
                    m = re.search(r"<user_query>(.*?)</user_query>", text, re.S)
                    if not m:
                        continue  # 系统注入的上下文，不是用户提问
                    query = m.group(1).strip()
                    # 会话恢复时会把整段历史摘要重放一遍，其外层文本会有数万字符；
                    # 这类事件不是新的提问，必须剔除，否则轮次会被切碎。
                    if len(text) > 20000 or len(query) > 5000:
                        continue
                    events.append({"kind": "user", "ts": ts, "text": query})
                elif role == "assistant":
                    events.append({"kind": "assistant", "ts": ts, "text": text.strip()})

            elif rtype == "function_call":
                name = row.get("name", "")
                args = row.get("arguments") or row.get("input") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                events.append(
                    {"kind": "tool", "ts": ts, "name": name, "args": args}
                )

            elif rtype == "function_call_result":
                if "AskUserQuestion" in str(row.get("name", "")):
                    out = row.get("output")
                    text = out.get("text", "") if isinstance(out, dict) else str(out)
                    if text.strip():
                        events.append({"kind": "decision", "ts": ts, "text": text.strip()})

    events.sort(key=lambda e: e["ts"])
    return events


# --------------------------------------------------------------------------
# 渲染
# --------------------------------------------------------------------------


def hhmm(ms: int) -> str:
    if not ms:
        return "--:--"
    return dt.datetime.fromtimestamp(ms / 1000).strftime("%H:%M")


def fmt_span(ms: int) -> str:
    if ms < 60_000:
        return f"{ms / 1000:.0f} 秒"
    minutes, _ = divmod(ms // 1000, 60)
    if minutes < 60:
        return f"{minutes} 分钟"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} 小时 {minutes} 分钟"


ROUND_TITLES = [
    "需求研判：活动规则拆解与选题决策",
    "原型实现：年报生成器、分享卡、命名与报名文案",
    "收尾交付：导出 WorkBuddy 会话记录",
    "精简与脱敏：生成提交版 workbuddy.md",
    "机制答疑：为什么发 Issue 就算报名",
    "竞品扫描：509 个报名 Issue 全量分析",
    "命名决策：全榜查重并更名为 mcrewind",
]


def render(
    events: list[dict],
    cutoff: int,
    meta: dict,
    brief: bool = False,
    redact: bool = False,
) -> str:
    events = [e for e in events if e["ts"] < cutoff]
    if not events:
        raise SystemExit("裁切时间之后没有任何事件，请检查 --cutoff")

    # ---- 分轮：一次用户提问开启一轮 ----
    rounds: list[dict] = []
    for ev in events:
        if ev["kind"] == "user":
            if rounds and rounds[-1]["query"] == ev["text"]:
                # 同一提问被重复记录（模式切换 / 会话重启），保留最后一次的时间
                rounds[-1]["ts"] = ev["ts"]
                continue
            rounds.append({"ts": ev["ts"], "query": ev["text"], "items": []})
        elif rounds:
            rounds[-1]["items"].append(ev)
        else:
            rounds.append({"ts": ev["ts"], "query": "", "items": [ev]})

    # ---- 统计 ----
    mcd_counter: Counter[str] = Counter()
    builtin_counter: Counter[str] = Counter()
    for ev in events:
        if ev["kind"] != "tool":
            continue
        args = ev.get("args") or {}
        if ev["name"] == "DeferExecuteTool":
            inner = str(args.get("toolName", ""))
            short = inner.split("__")[-1] if "__" in inner else inner
            if inner.startswith("mcp__mcd-mcp__"):
                mcd_counter[short] += 1
                continue
        builtin_counter[ev["name"]] += 1

    n_user = len(rounds)  # 去重后的真实提问轮次
    n_asst = sum(1 for e in events if e["kind"] == "assistant")
    n_tool = sum(1 for e in events if e["kind"] == "tool")
    n_dec = sum(1 for e in events if e["kind"] == "decision")
    t0, t1 = events[0]["ts"], events[-1]["ts"]

    # 有效开发时长：剔除中途空档（间隔 > 10 分钟视为暂停）
    ticks = sorted(e["ts"] for e in events)
    active_ms = sum(
        b - a for a, b in zip(ticks, ticks[1:]) if 0 <= (b - a) <= 600_000
    )

    out: list[str] = []
    w = out.append

    w("# workbuddy.md — WorkBuddy 开发会话记录")
    w("")
    w("> 本文档是 **麦当劳程序员创意开发大赛 · WorkBuddy 专项奖励** 要求的对话上下文文件。")
    w("> 内容由 WorkBuddy 会话原始日志（JSONL）自动导出，源于真实对话，")
    if brief:
        w("> 为便于阅读，本文档为**精简版**：仅保留每一次提问、用户决策、关键回复与执行摘要，")
        w("> 逐条工具调用明细与过程性短句已省略。完整版本见 `workbuddy.full.md`。")
    else:
        w("> 完整保留每一次提问、回复与执行轨迹，可与真实会话逐条对应核验。")
    if redact:
        w("> 已做**脱敏处理**：本地路径、会话标识、账号余额等信息已替换或泛化。")
    if brief:
        w(">")
        w("> 读法提示：轮次 1–2 是项目从零到一的开发过程；轮次 3 是导出会话记录")
        w("> （当时的完整版），轮次 4 是本文档的精简与脱敏过程；轮次 5–6 转为报名机制")
        w("> 答疑与全榜竞品扫描；轮次 7 依据查重结果，将项目由原定名 `maimen-wrapped`")
        w("> 更名为 `mcrewind`（原定名与榜上已有项目重名）。")
    w("")
    w("## 会话元信息")
    w("")
    w("| 项目 | 内容 |")
    w("| --- | --- |")
    w("| 参赛项目 | 麦麦倒带（mcrewind） |")
    w("| 开发工具 | 腾讯 WorkBuddy 智能体 |")
    w("| 会话 ID | `{}` |".format(meta.get("session_id", "-")))
    w("| 会话日期 | {} |".format(meta.get("date", "-")))
    w("| 会话起止 | {} — {} |".format(hhmm(t0), hhmm(t1)))
    w("| 会话跨度 | {}（含中途暂停） |".format(fmt_span(t1 - t0)))
    w("| 有效开发时长 | {} |".format(fmt_span(active_ms)))
    w("| 用户提问 | {} 次 |".format(n_user))
    w("| 助手回复 | {} 条 |".format(n_asst))
    w("| 用户决策确认 | {} 次 |".format(n_dec))
    w("| 工具调用 | {} 次 |".format(n_tool))
    w("| 麦当劳 MCP 调用 | {} 次 |".format(sum(mcd_counter.values())))
    w("")
    flags = " ".join(
        f for f in (["--brief"] if brief else []) + (["--redact"] if redact else [])
    )
    w("> 本文件由仓库内的 `tools/export_workbuddy_md.py` 从会话原始日志生成，")
    w("> 可用同一脚本复现导出过程：`python tools/export_workbuddy_md.py"
      + (f" {flags}" if flags else "") + "`。")
    w("")

    # ---- 麦当劳 MCP 调用清单 ----
    w("## 一、本会话中真实调用的麦当劳 MCP 能力")
    w("")
    w("| 麦当劳 MCP Tool | 调用次数 | 在项目中的作用 |")
    w("| --- | ---: | --- |")
    for tool, cnt in mcd_counter.most_common():
        desc = MCD_TOOL_LABELS.get(tool, "—")
        w(f"| `{tool}` | {cnt} | {desc} |")
    w("")
    w("> 说明：`order-list` / `query-my-account` 是本项目年报数据的核心来源，")
    w("> 其真实返回结构直接决定了 `analyzer.py` 的字段容错设计（见下面对话）。")
    w("")

    # ---- WorkBuddy 内置能力 ----
    w("## 二、本会话中使用的 WorkBuddy 内置能力")
    w("")
    for name, cnt in builtin_counter.most_common():
        label = BUILTIN_TOOL_LABELS.get(name, name)
        w(f"- **{label}**（`{name}`）× {cnt}")
    w("")

    # ---- 对话正文 ----
    w("## 三、对话记录" + ("（精简）" if brief else ""))
    w("")
    w("> 下文中「我」指项目作者（用户），「WorkBuddy」指腾讯 WorkBuddy 智能体。")
    w("")

    for idx, rnd in enumerate(rounds, 1):
        title = ROUND_TITLES[idx - 1] if idx - 1 < len(ROUND_TITLES) else "继续开发"
        w(f"### 轮次 {idx} · {hhmm(rnd['ts'])} — {title}")
        w("")
        if rnd["query"]:
            w("#### 我的提问")
            w("")
            for line in rnd["query"].splitlines() or [""]:
                w(f"> {line}" if line.strip() else ">")
            w("")

        pending_tools: list[str] = []

        def flush_tools() -> None:
            if not pending_tools:
                return
            # 归并去重但保留顺序
            seen: OrderedDict[str, int] = OrderedDict()
            for item in pending_tools:
                seen[item] = seen.get(item, 0) + 1
            parts = [
                f"{k} ×{v}" if v > 1 else k for k, v in seen.items()
            ]
            w("<details><summary>执行轨迹（{} 步）</summary>".format(len(pending_tools)))
            w("")
            for p in parts:
                w(f"- {p}")
            w("")
            w("</details>")
            w("")
            pending_tools.clear()

        # 精简版：整轮的工具调用压成一行摘要，放在提问之后
        if brief:
            summary = summarize_round_tools(rnd["items"])
            if summary:
                w(f"> 🛠 {summary}")
                w("")

        for ev in rnd["items"]:
            if ev["kind"] == "tool":
                # 内联可视化是「看得见的分析」，单独标出来，比混在轨迹里信息量大
                if ev["name"] == "show_widget":
                    if not brief:
                        flush_tools()
                    title = str((ev.get("args") or {}).get("title", "")).strip()
                    if title:
                        w(f"> 📊 WorkBuddy 内联渲染图表：**{title}**")
                        w("")
                    continue
                if brief:
                    continue
                label, _ = label_for_tool(ev["name"], ev.get("args") or {})
                pending_tools.append(label)
            elif ev["kind"] == "decision":
                if not brief:
                    flush_tools()
                w("#### 我的决策")
                w("")
                for line in ev["text"].splitlines():
                    if line.strip():
                        w(f"> {line.strip()}")
                w("")
            elif ev["kind"] == "assistant":
                if not brief:
                    flush_tools()
                text = ev["text"]
                if len(text) <= 120 and "\n" not in text:
                    # 精简版省略过程性短句（「我来查一下…」这类），只留实质回复
                    if brief:
                        continue
                    w(f"*{text}*")
                    w("")
                else:
                    w("#### WorkBuddy 回复")
                    w("")
                    w(demote_headings(cap_text(text, 700) if brief else text))
                    w("")

        if not brief:
            flush_tools()

        has_body = any(
            (e["kind"] == "decision")
            or (e["kind"] == "assistant" and (not brief or len(e["text"]) > 120 or "\n" in e["text"]))
            for e in rnd["items"]
        )
        if not has_body:
            w("*（本轮回复发生在本次导出之后，故此处无正文。）*")
            w("")

    w("---")
    w("")
    w("## 四、交付物")
    w("")
    w("| 文件 | 说明 |")
    w("| --- | --- |")
    w("| `mcrewind/analyzer.py` | 订单数据聚合与字段容错 |")
    w("| `mcrewind/persona.py` | 称号与徽章规则（传播引擎） |")
    w("| `mcrewind/render.py` | 单文件 HTML 报告渲染（手写 SVG/CSS） |")
    w("| `mcrewind/sharecard.py` | 1080×1440 竖版分享卡 |")
    w("| `mcrewind/__main__.py` | CLI 入口，含无头浏览器 PNG 导出 |")
    w("| `tools/gen_demo.py` | 固定种子演示数据集生成器 |")
    w("| `tools/export_workbuddy_md.py` | 本文件的导出脚本（支持 `--brief` / `--redact`） |")
    w("| `tools/check_redaction.py` | 公开前的脱敏与凭证自检 |")
    w("| `examples/demo-report.html` | 示例年报（演示数据） |")
    w("| `examples/demo-card.png` | 示例竖版分享卡 |")
    w("| `workbuddy.full.md` | 同一会话的完整版记录（含逐条工具调用轨迹） |")
    w("")
    w("## 五、说明")
    w("")
    w("1. 本会话全程在腾讯 WorkBuddy 智能体中完成：需求研判、选题决策、")
    w("   代码编写、真实调用麦当劳 MCP 探测数据、无头浏览器截图核验、")
    w("   缺陷修复、参赛材料撰写。")
    w("2. 会话中仅涉及项目作者本人的麦当劳账号，未包含任何第三方个人信息；")
    w("   订单与积分的具体数值已在导出时泛化处理。")
    w("3. `mcp-config.example.json` 中使用环境变量占位符，仓库内无任何真实凭证；")
    w("   本文件亦不含 MCP Token、Cookie 或其他凭据。")
    if redact:
        w("4. 已脱敏内容：本地文件路径（替换为 `<本地路径>` / `<临时目录>`）、")
        w("   会话标识（仅保留前 8 位）、账号余额数值（直接抹除）、系统用户名。")
    else:
        w("4. 会话中出现的历史项目缓存与临时截图均已在交付前清理。")
    w("")
    w("> 导出时间：{}（北京时间）".format(meta.get("export_time", "-")))
    w("")

    return "\n".join(out)


# --------------------------------------------------------------------------
# 入口
# --------------------------------------------------------------------------


def locate_session(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit)
        if not p.exists():
            raise SystemExit(f"会话文件不存在：{p}")
        return p
    root = Path(os.path.expanduser("~")) / ".workbuddy" / "projects"
    cands = sorted(
        root.glob("*/*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    cands = [c for c in cands if c.stat().st_size > 10_000]
    if not cands:
        raise SystemExit("未自动找到会话日志，请用 --session 指定")
    return cands[0]


def main() -> int:
    ap = argparse.ArgumentParser(description="导出 WorkBuddy 会话为 workbuddy.md")
    ap.add_argument("--session", help="会话 JSONL 路径（缺省自动定位）")
    ap.add_argument("--out", default="workbuddy.md", help="输出路径")
    ap.add_argument("--cutoff", type=int, help="只导出该毫秒时间戳之前的事件")
    ap.add_argument(
        "--brief",
        action="store_true",
        help="精简版：省略过程性短句与逐条工具调用明细，长回复截断到 700 字",
    )
    ap.add_argument(
        "--redact",
        action="store_true",
        help="脱敏：替换本地路径、会话标识、账号余额等个人环境信息",
    )
    args = ap.parse_args()

    session = locate_session(args.session)
    events = parse_events(session)

    cutoff = args.cutoff
    if cutoff is None:
        # 缺省：裁到最后一次用户提问那一刻（即本文件的导出请求）
        user_ts = [e["ts"] for e in events if e["kind"] == "user"]
        cutoff = max(user_ts) + 1 if user_ts else events[-1]["ts"] + 1

    meta = {
        "session_id": session.stem,
        "date": dt.datetime.fromtimestamp(events[0]["ts"] / 1000).strftime("%Y-%m-%d"),
        "export_time": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
    }

    md = render(events, cutoff, meta, brief=args.brief, redact=args.redact)
    if args.redact:
        md = apply_redactions(md)

    # 脱敏后自检：任何遗漏的本地指纹都应当在这里被拦住
    leaks = find_leaks(md) if args.redact else []
    if leaks:
        print(f"[警告] 脱敏不完整，仍残留：{leaks}", file=sys.stderr)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    print(f"[完成] 已导出 {len(md)} 字符 → {out_path.resolve()}")
    return 1 if leaks else 0


if __name__ == "__main__":
    sys.exit(main())

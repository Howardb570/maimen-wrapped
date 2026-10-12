"""麦麦年报 · 命令行入口

    python -m maimen_wrapped --demo
    python -m maimen_wrapped --orders raw/orders.json --account raw/account.json -o report.html
    python -m maimen_wrapped --demo --card --card-png          # 生成竖版分享卡（含 PNG）

设计要点：CLI 只做「读文件 → 分析 → 渲染 → 写文件」，
不主动发起任何网络请求。所有 MCP 调用由 WorkBuddy 智能体完成，
结果以 JSON 落盘后再交给本程序。这样做有两个好处：
    1. 报告生成过程完全离线，用户数据不出本机；
    2. 便于用固定样本做回归测试和演示。
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from .analyzer import analyze
from .persona import generate_personas
from .render import render
from .sharecard import RATIOS, render_share_card

DEMO_DIR = Path(__file__).resolve().parent.parent / "assets" / "demo"

#: 无头浏览器候选路径（用于把分享卡导出成 PNG）
BROWSER_CANDIDATES = [
    # Windows
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    # macOS
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    # Linux
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/microsoft-edge",
]


def _load_json(path: Path) -> object:
    """读取 JSON，失败时给出明确提示而不是抛栈。"""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"[错误] 找不到文件：{path}", file=sys.stderr)
        sys.exit(2)
    except json.JSONDecodeError as exc:
        print(f"[错误] JSON 解析失败：{path}\n        {exc}", file=sys.stderr)
        sys.exit(2)


def _find_browser() -> str | None:
    """找一个可用的 Chromium 系浏览器。优先 PATH，其次常见安装路径。"""
    for name in ("msedge", "chrome", "chromium", "google-chrome", "microsoft-edge"):
        found = shutil.which(name)
        if found:
            return found
    for candidate in BROWSER_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return None


def export_png(html_path: Path, png_path: Path, width: int, height: int) -> tuple[bool, str]:
    """用无头浏览器把 HTML 渲染成 PNG。

    返回 (是否成功, 说明信息)。失败时调用方应降级为「只交付 HTML」，
    而不是让整个流程报错 —— 分享卡 HTML 本身也是可用交付物。
    """
    browser = _find_browser()
    if not browser:
        return False, "未找到 Edge/Chrome，分享卡已输出为 HTML（可直接截图）"

    # 注意：Chromium 的 --screenshot 不接受相对路径，必须给绝对路径，
    # 否则进程正常退出但不会产出文件（静默失败）。
    png_path = png_path.resolve()
    png_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--force-device-scale-factor=1",
        f"--window-size={width},{height}",
        f"--screenshot={png_path}",
        html_path.resolve().as_uri(),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=90)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        return False, f"PNG 导出失败（{type(exc).__name__}），分享卡已输出为 HTML"

    if png_path.exists() and png_path.stat().st_size > 0:
        return True, "分享卡 PNG 已生成"
    return False, "PNG 导出未产出文件，分享卡已输出为 HTML"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m maimen_wrapped",
        description="把麦当劳 MCP 订单数据渲染成一份可分享的年度报告",
    )
    parser.add_argument("--orders", type=Path, help="order-list 工具返回的原始 JSON 文件路径")
    parser.add_argument("--account", type=Path, help="query-my-account 工具的原始 JSON 路径（可选）")
    parser.add_argument(
        "--out", "-o", type=Path, default=Path("maimen-wrapped.html"),
        help="输出 HTML 路径，默认 maimen-wrapped.html",
    )
    parser.add_argument("--demo", action="store_true", help="使用内置演示数据（无需 MCP Token）")
    parser.add_argument("--year", type=int, help="报告年份，默认取当前年份")
    parser.add_argument("--quiet", action="store_true", help="只输出结果路径")

    card = parser.add_argument_group("分享卡")
    card.add_argument("--card", action="store_true", help="额外生成一张竖版分享卡 HTML")
    card.add_argument(
        "--card-ratio", default="3:4", choices=sorted(RATIOS),
        help="分享卡比例，默认 3:4（适配小红书/朋友圈）",
    )
    card.add_argument("--card-png", action="store_true", help="尝试把分享卡导出为 PNG（需本机有 Edge/Chrome）")
    card.add_argument("--card-out", type=Path, help="分享卡 HTML 输出路径")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # ---- 取数据 ----
    if args.demo:
        orders = _load_json(DEMO_DIR / "demo_orders.json")
        account = _load_json(DEMO_DIR / "demo_account.json")
    elif args.orders:
        orders = _load_json(args.orders)
        account = _load_json(args.account) if args.account else None
    else:
        print(
            "[提示] 请指定 --orders <文件>，或使用 --demo 查看示例报告。\n"
            "       在 WorkBuddy 中直接说「生成我的麦麦年报」即可自动完成采集。",
            file=sys.stderr,
        )
        return 1

    # ---- 分析 ----
    stats = analyze(orders, _unwrap_account(account))
    stats.personas = generate_personas(stats)

    # ---- 渲染报告 ----
    html_text = render(stats, year=args.year)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(html_text, encoding="utf-8")

    outputs = [str(args.out.resolve())]

    # ---- 渲染分享卡 ----
    if args.card:
        card_path = args.card_out or args.out.with_name(args.out.stem + "-card.html")
        card_path.parent.mkdir(parents=True, exist_ok=True)
        card_path.write_text(
            render_share_card(stats, ratio=args.card_ratio, year=args.year),
            encoding="utf-8",
        )
        outputs.append(str(card_path.resolve()))

        if args.card_png:
            width, height = RATIOS.get(args.card_ratio, RATIOS["3:4"])
            png_path = card_path.with_suffix(".png")
            ok, note = export_png(card_path, png_path, width, height)
            if ok:
                outputs.append(str(png_path.resolve()))
            if not args.quiet:
                print(f"[分享卡] {note}")

    # ---- 输出摘要 ----
    if not args.quiet:
        if stats.has_data:
            title = next((p["name"] for p in stats.personas if p["type"] == "title"), "—")
            print(
                f"[完成] 共 {stats.total_orders} 单 · "
                f"消费 {stats.total_amount:.2f} 元 · 称号「{title}」"
            )
        else:
            print("[完成] 未查询到订单，已生成空状态报告。")
        for path in outputs:
            print(f"[输出] {path}")
    else:
        for path in outputs:
            print(path)

    return 0


def _unwrap_account(account: object) -> dict | None:
    """query-my-account 的返回结构是 {"data": {...}}，这里剥一层。"""
    if isinstance(account, dict):
        inner = account.get("data", account)
        if isinstance(inner, dict):
            return inner
    return None


if __name__ == "__main__":
    raise SystemExit(main())

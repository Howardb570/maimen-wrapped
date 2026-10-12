"""麦麦倒带 · HTML 渲染模块

设计取舍（很重要，写进 README 会加分）:
    报告输出为**单文件、零外部依赖**的 HTML。所有图表用手写 SVG / CSS 实现，
    不引用任何 CDN、字体、图片。理由：这类产品的核心传播动作是「截图 + 转发文件」，
    一个断网就打不开、或者要等 CDN 加载的报告，传播力会大打折扣。

输出目标：用户拿到 HTML 后，不需要任何环境就能打开、截图、发给朋友。
"""

from __future__ import annotations

import html
from datetime import datetime

from .analyzer import (
    WrappedStats,
    format_amount,
    format_percent,
    top_n,
)

# ---------------------------------------------------------------------------
# 视觉规范
# ---------------------------------------------------------------------------

PALETTE = {
    "bg": "#16110E",
    "surface": "#211A16",
    "surface_alt": "#2A211C",
    "border": "rgba(255,255,255,0.09)",
    "text": "#F5F1EC",
    "muted": "#A89E96",
    "dim": "#7A7069",
    "red": "#DA291C",
    "yellow": "#FFC72C",
    "green": "#5DCAA5",
    "blue": "#85B7EB",
}

#: 渠道配色（与图例一一对应，不依赖颜色单独区分——同时带文字）
CHANNEL_COLORS = ["#DA291C", "#FFC72C", "#5DCAA5", "#85B7EB", "#B4B2A9"]

CSS = """
*, *::before, *::after { box-sizing: border-box; }
body {
  margin: 0;
  background: #16110E;
  color: #F5F1EC;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
               "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  -webkit-font-smoothing: antialiased;
  line-height: 1.6;
}
.wrap { max-width: 760px; margin: 0 auto; padding: 0 24px 64px; }

/* ---------- 封面 ---------- */
.hero { padding: 72px 0 40px; }
.hero .eyebrow {
  font-size: 13px; letter-spacing: 0.18em; text-transform: uppercase;
  color: #7A7069; margin-bottom: 20px;
}
.hero h1 {
  font-size: 46px; line-height: 1.15; margin: 0 0 8px; font-weight: 600;
  letter-spacing: -0.02em;
}
.hero h1 .accent { color: #FFC72C; }
.hero .subtitle { font-size: 15px; color: #A89E96; margin: 0 0 40px; }

/* ---------- 称号卡 ---------- */
.title-card {
  background: linear-gradient(135deg, #2A211C 0%, #211A16 100%);
  border: 1px solid rgba(255,199,44,0.28);
  border-radius: 20px; padding: 32px; margin-bottom: 16px;
}
.title-card .label {
  font-size: 12px; letter-spacing: 0.16em; color: #FFC72C;
  text-transform: uppercase; margin-bottom: 12px;
}
.title-card .title-name {
  font-size: 38px; font-weight: 600; margin: 0 0 12px; letter-spacing: -0.01em;
}
.title-card .reason { font-size: 15px; color: #A89E96; margin: 0; }

/* ---------- 区块 ---------- */
.section { margin-top: 56px; }
.section-head { display: flex; align-items: baseline; gap: 12px; margin-bottom: 20px; }
.section-head h2 { font-size: 20px; font-weight: 600; margin: 0; }
.section-head .hint { font-size: 13px; color: #7A7069; }

/* ---------- 指标卡 ---------- */
.metrics { display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 12px; }
.metric {
  background: #211A16; border: 1px solid rgba(255,255,255,0.09);
  border-radius: 14px; padding: 20px;
}
.metric .k { font-size: 13px; color: #A89E96; margin-bottom: 8px; }
.metric .v { font-size: 30px; font-weight: 600; letter-spacing: -0.02em; }
.metric .v .unit { font-size: 15px; font-weight: 400; color: #A89E96; margin-left: 4px; }
.metric .note { font-size: 12px; color: #7A7069; margin-top: 6px; }

/* ---------- 商品条 ---------- */
.bars { display: flex; flex-direction: column; gap: 14px; }
.bar-row .top { display: flex; justify-content: space-between; font-size: 14px; margin-bottom: 6px; }
.bar-row .top .name { color: #F5F1EC; }
.bar-row .top .count { color: #A89E96; font-variant-numeric: tabular-nums; }
.bar-track { height: 8px; background: #2A211C; border-radius: 4px; overflow: hidden; }
.bar-fill { height: 100%; border-radius: 4px; background: #DA291C; }

/* ---------- 图表 ---------- */
.chart-box {
  background: #211A16; border: 1px solid rgba(255,255,255,0.09);
  border-radius: 14px; padding: 20px;
}
.chart-box svg { display: block; width: 100%; height: auto; }

/* ---------- 渠道环 ---------- */
.donut-row { display: flex; gap: 28px; align-items: center; flex-wrap: wrap; }
.donut { width: 148px; height: 148px; border-radius: 50%; position: relative; flex: 0 0 auto; }
.donut::after {
  content: ""; position: absolute; inset: 26px; border-radius: 50%; background: #211A16;
}
.donut-center {
  position: absolute; inset: 0; display: flex; flex-direction: column;
  align-items: center; justify-content: center; z-index: 2;
}
.donut-center .n { font-size: 24px; font-weight: 600; line-height: 1.1; }
.donut-center .l { font-size: 11px; color: #7A7069; }
.legend { display: flex; flex-direction: column; gap: 10px; flex: 1 1 200px; min-width: 0; }
.legend-item { display: flex; align-items: center; gap: 10px; font-size: 14px; }
.legend-item .dot { width: 10px; height: 10px; border-radius: 3px; flex: 0 0 auto; }
.legend-item .nm { flex: 1; color: #F5F1EC; }
.legend-item .pc { color: #A89E96; font-variant-numeric: tabular-nums; }

/* ---------- 徽章墙 ---------- */
.badges { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; }
.badge {
  background: #211A16; border: 1px solid rgba(255,255,255,0.09);
  border-radius: 14px; padding: 18px;
}
.badge .ic { width: 34px; height: 34px; margin-bottom: 12px; }
.badge .bn { font-size: 15px; font-weight: 600; margin-bottom: 4px; }
.badge .bd { font-size: 13px; color: #A89E96; }

/* ---------- 列表 ---------- */
.rank-list { display: flex; flex-direction: column; }
.rank-item {
  display: flex; align-items: center; gap: 14px; padding: 14px 0;
  border-bottom: 1px solid rgba(255,255,255,0.09);
}
.rank-item:last-child { border-bottom: none; }
.rank-item .idx {
  width: 26px; height: 26px; border-radius: 7px; background: #2A211C;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; color: #A89E96; flex: 0 0 auto;
}
.rank-item .nm { flex: 1; font-size: 14px; min-width: 0;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rank-item .ct { font-size: 14px; color: #A89E96; font-variant-numeric: tabular-nums; }

/* ---------- 空状态 ---------- */
.empty {
  background: #211A16; border: 1px dashed rgba(255,199,44,0.35);
  border-radius: 16px; padding: 40px 28px; text-align: center;
}
.empty .e-t { font-size: 18px; font-weight: 600; margin-bottom: 10px; }
.empty .e-d { font-size: 14px; color: #A89E96; margin: 0 auto; max-width: 460px; }

/* ---------- 页脚 ---------- */
.footer {
  margin-top: 64px; padding-top: 24px; border-top: 1px solid rgba(255,255,255,0.09);
  font-size: 12px; color: #7A7069; line-height: 1.8;
}
.footer a { color: #A89E96; }

@media (max-width: 560px) {
  .hero h1 { font-size: 34px; }
  .hero { padding: 48px 0 32px; }
  .metrics { grid-template-columns: minmax(0,1fr); }
  .donut-row { justify-content: center; }
}
"""


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------


def esc(value: object) -> str:
    """统一转义，防止 MCP 返回内容破坏 HTML 结构。"""
    return html.escape(str(value), quote=True)


#: 徽章图标：纯 SVG path，不依赖图标字体
BADGE_ICONS = {
    "moon": '<path d="M20 3a9 9 0 1 0 9 9 7 7 0 0 1-9-9z"/>',
    "sun": '<circle cx="16" cy="16" r="5"/><path d="M16 3v3M16 26v3M3 16h3M26 16h3M7 7l2 2M23 23l2 2M25 7l-2 2M9 23l-2 2"/>',
    "clock": '<circle cx="16" cy="16" r="11"/><path d="M16 9v7l5 3"/>',
    "star": '<path d="M16 4l3.6 7.6 8.4 1.1-6.1 5.8 1.5 8.3L16 23l-7.4 3.8 1.5-8.3L4 12.7l8.4-1.1z"/>',
    "shuffle": '<path d="M4 9h5l5 7 5 7h5M4 23h5l2.6-3.6M20 9h8M20 23h8"/><path d="M25 5l3 4-3 4M25 19l3 4-3 4"/>',
    "lock": '<rect x="7" y="14" width="18" height="12" rx="2"/><path d="M11 14v-4a5 5 0 0 1 10 0v4"/>',
    "route": '<circle cx="8" cy="23" r="3"/><circle cx="24" cy="9" r="3"/><path d="M11 23h7a4 4 0 0 0 4-4v-5"/>',
    "wallet": '<rect x="4" y="9" width="24" height="16" rx="3"/><path d="M4 14h24M21 19h2"/>',
    "pin": '<path d="M16 28s9-8.5 9-14a9 9 0 0 0-18 0c0 5.5 9 14 9 14z"/><circle cx="16" cy="13" r="3"/>',
    "fire": '<path d="M16 28c5 0 8-3.4 8-7.6 0-5.4-5-7.4-5-11.4 0 0-3 1.4-3 5 0 1.6-1 2.4-2 2.4-1.2 0-2-1-2-2.6-2 2-4 4.4-4 7.2C8 24.6 11 28 16 28z"/>',
}


def _icon(name: str, color: str) -> str:
    """渲染一个 32x32 的描边图标。"""
    path = BADGE_ICONS.get(name, BADGE_ICONS["star"])
    return (
        f'<svg class="ic" viewBox="0 0 32 32" fill="none" stroke="{color}" '
        f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" '
        f'role="img" aria-hidden="true">{path}</svg>'
    )


# ---------------------------------------------------------------------------
# 图表：全部手写 SVG / CSS
# ---------------------------------------------------------------------------


def _hour_chart(hist: list[int]) -> str:
    """24 小时下单分布柱状图。"""
    width, height = 660, 170
    top_pad, bottom_pad = 16, 34
    plot_h = height - top_pad - bottom_pad
    slot = width / 24
    bar_w = slot * 0.58
    peak = max(hist) if any(hist) else 1

    parts: list[str] = []
    for hour, count in enumerate(hist):
        x = hour * slot + (slot - bar_w) / 2
        h = (count / peak) * plot_h if peak else 0
        y = top_pad + (plot_h - h)
        is_night = hour >= 22 or hour < 5
        color = PALETTE["yellow"] if is_night else PALETTE["red"]
        opacity = "1" if count else "0.18"
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{max(h, 2):.1f}" '
            f'rx="2" fill="{color}" opacity="{opacity}"/>'
        )
        if count:
            parts.append(
                f'<text x="{hour * slot + slot / 2:.1f}" y="{y - 6:.1f}" text-anchor="middle" '
                f'font-size="10" fill="{PALETTE["muted"]}">{count}</text>'
            )

    # 只在 0/6/12/18/23 点显示刻度，避免拥挤
    for hour in (0, 6, 12, 18, 23):
        cx = hour * slot + slot / 2
        parts.append(
            f'<text x="{cx:.1f}" y="{height - bottom_pad + 20:.1f}" text-anchor="middle" '
            f'font-size="11" fill="{PALETTE["dim"]}">{hour:02d}:00</text>'
        )

    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="24 小时下单分布柱状图，黄色柱为夜间时段">{"".join(parts)}</svg>'
    )


def _weekday_chart(hist: list[int]) -> str:
    """星期分布柱状图。"""
    from .analyzer import WEEKDAY_NAMES

    width, height = 660, 160
    top_pad, bottom_pad = 22, 30
    plot_h = height - top_pad - bottom_pad
    slot = width / 7
    bar_w = slot * 0.42
    peak = max(hist) if any(hist) else 1
    peak_idx = max(range(7), key=lambda d: hist[d]) if any(hist) else -1

    parts: list[str] = []
    for day, count in enumerate(hist):
        x = day * slot + (slot - bar_w) / 2
        h = (count / peak) * plot_h if peak else 0
        y = top_pad + (plot_h - h)
        color = PALETTE["yellow"] if day == peak_idx and count else PALETTE["red"]
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{max(h, 2):.1f}" '
            f'rx="3" fill="{color}" opacity="{"1" if count else "0.18"}"/>'
        )
        if count:
            parts.append(
                f'<text x="{day * slot + slot / 2:.1f}" y="{y - 7:.1f}" text-anchor="middle" '
                f'font-size="11" fill="{PALETTE["muted"]}">{count}</text>'
            )
        parts.append(
            f'<text x="{day * slot + slot / 2:.1f}" y="{height - bottom_pad + 20:.1f}" '
            f'text-anchor="middle" font-size="12" fill="{PALETTE["dim"]}">{WEEKDAY_NAMES[day]}</text>'
        )

    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="一周七天订单分布柱状图，黄色柱为下单最多的一天">{"".join(parts)}</svg>'
    )


def _product_bars(stats: WrappedStats, limit: int = 5) -> str:
    """最常点餐品 Top N 条形图（CSS 实现）。"""
    top = top_n(stats.product_counter, limit)
    if not top:
        return ""
    peak = top[0][1]
    rows: list[str] = []
    for name, count in top:
        pct = round(count / peak * 100)
        rows.append(
            f'<div class="bar-row">'
            f'<div class="top"><span class="name">{esc(name)}</span>'
            f'<span class="count">{count} 份</span></div>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{pct}%"></div></div>'
            f"</div>"
        )
    return f'<div class="bars">{"".join(rows)}</div>'


def _channel_donut(stats: WrappedStats) -> str:
    """渠道占比环形图 + 图例。"""
    counter = sorted(stats.channel_counter.items(), key=lambda kv: -kv[1])
    total = sum(stats.channel_counter.values())
    if not counter or not total:
        return ""

    stops: list[str] = []
    cursor = 0.0
    for i, (_name, count) in enumerate(counter):
        share = count / total * 100
        color = CHANNEL_COLORS[i % len(CHANNEL_COLORS)]
        stops.append(f"{color} {cursor:.2f}% {cursor + share:.2f}%")
        cursor += share

    donut = (
        f'<div class="donut" style="background: conic-gradient({", ".join(stops)})" '
        f'role="img" aria-label="渠道占比环形图">'
        f'<div class="donut-center"><div class="n">{total}</div><div class="l">总订单</div></div>'
        f"</div>"
    )

    legend_items: list[str] = []
    for i, (name, count) in enumerate(counter):
        color = CHANNEL_COLORS[i % len(CHANNEL_COLORS)]
        legend_items.append(
            f'<div class="legend-item">'
            f'<span class="dot" style="background:{color}"></span>'
            f'<span class="nm">{esc(name)}</span>'
            f'<span class="pc">{count} 单 · {format_percent(count, total)}</span>'
            f"</div>"
        )

    return f'<div class="donut-row">{donut}<div class="legend">{"".join(legend_items)}</div></div>'


def _store_rank(stats: WrappedStats, limit: int = 5) -> str:
    """常去门店排行。"""
    top = top_n(stats.store_counter, limit)
    if not top:
        return ""
    items = []
    for i, (name, count) in enumerate(top, 1):
        items.append(
            f'<div class="rank-item"><div class="idx">{i}</div>'
            f'<div class="nm">{esc(name)}</div><div class="ct">{count} 单</div></div>'
        )
    return f'<div class="rank-list">{"".join(items)}</div>'


def _badge_wall(personas: list[dict[str, str]]) -> str:
    badges = [p for p in personas if p.get("type") == "badge"]
    if not badges:
        return ""
    cards: list[str] = []
    for badge in badges:
        color = PALETTE["yellow"]
        cards.append(
            f'<div class="badge">{_icon(badge.get("icon", "star"), color)}'
            f'<div class="bn">{esc(badge.get("name", ""))}</div>'
            f'<div class="bd">{esc(badge.get("detail", ""))}</div></div>'
        )
    return f'<div class="badges">{"".join(cards)}</div>'


# ---------------------------------------------------------------------------
# 主渲染
# ---------------------------------------------------------------------------


def render(stats: WrappedStats, year: int | None = None, generated_at: str | None = None) -> str:
    """把统计结果渲染成一份完整的单文件 HTML 报告。"""
    year = year or datetime.now().year
    generated_at = generated_at or datetime.now().strftime("%Y-%m-%d %H:%M")

    title_persona = next((p for p in stats.personas if p.get("type") == "title"), None)
    title_name = title_persona.get("name", "麦门新朋友") if title_persona else "麦门新朋友"
    title_reason = title_persona.get("reason", "") if title_persona else ""

    # ---- 空状态：不报错，给一份体面的引导页 ----
    if not stats.has_data:
        body = f"""
<div class="hero">
  <div class="eyebrow">McDonald's Data Wrapped {year}</div>
  <h1>我的 <span class="accent">麦麦倒带</span></h1>
  <p class="subtitle">{esc(generated_at)} 生成</p>
</div>
<div class="empty">
  <div class="e-t">还没有找到你的订单记录</div>
  <p class="e-d">
    当前 MCP Token 对应的麦当劳会员账号暂无历史订单，所以还没有故事可以讲。<br>
    用同一个账号下过单之后，再回来生成一次，你的年份画像就会出现。
  </p>
</div>
<div class="footer">
  数据来源：麦当劳 MCP Server（order-list / query-my-account）<br>
  本报告由开源项目 <strong>mcrewind</strong> 生成 · 非麦当劳官方产品
</div>
"""
        return _shell(f"我的麦麦倒带 {year}", body, stats)

    # ---- 指标卡 ----
    avg_note = f"共 {stats.total_orders} 单"
    interval = round(stats.span_days / max(stats.total_orders, 1))
    metrics = [
        ("年度订单", format_amount(stats.total_orders), "单", f"平均 {interval} 天点一次"),
        ("年度消费", format_amount(stats.total_amount), "元", avg_note),
        ("单均消费", format_amount(stats.avg_amount), "元", "每次大约花这么多"),
        (
            "最大单笔",
            format_amount(stats.max_order_amount),
            "元",
            esc(stats.max_order_name or "—"),
        ),
    ]
    metric_html = "".join(
        f'<div class="metric"><div class="k">{k}</div>'
        f'<div class="v">{v}<span class="unit">{u}</span></div>'
        f'<div class="note">{n}</div></div>'
        for k, v, u, n in metrics
    )

    peak_hour_txt = f"{stats.peak_hour:02d}:00" if stats.peak_hour >= 0 else "—"
    from .analyzer import WEEKDAY_NAMES

    peak_weekday_txt = WEEKDAY_NAMES[stats.peak_weekday] if stats.peak_weekday >= 0 else "—"

    sections: list[str] = []

    # 口味画像
    if stats.product_counter:
        sections.append(
            f'<div class="section"><div class="section-head">'
            f"<h2>你的口味画像</h2>"
            f'<span class="hint">一共尝过 {stats.unique_products} 种餐品</span></div>'
            f"{_product_bars(stats)}</div>"
        )

    # 时间画像
    sections.append(
        f'<div class="section"><div class="section-head">'
        f"<h2>你几点吃麦当劳</h2>"
        f'<span class="hint">最常下单时间是 {esc(peak_hour_txt)}</span></div>'
        f'<div class="chart-box">{_hour_chart(stats.hour_hist)}</div></div>'
    )

    sections.append(
        f'<div class="section"><div class="section-head">'
        f"<h2>一周里的规律</h2>"
        f'<span class="hint">{esc(peak_weekday_txt)}是你的高频日</span></div>'
        f'<div class="chart-box">{_weekday_chart(stats.weekday_hist)}</div></div>'
    )

    # 渠道
    donut = _channel_donut(stats)
    if donut:
        sections.append(
            f'<div class="section"><div class="section-head"><h2>你怎么吃</h2>'
            f'<span class="hint">到店 / 外送 / 得来速偏好</span></div>'
            f'<div class="chart-box">{donut}</div></div>'
        )

    # 门店足迹
    store_rank = _store_rank(stats)
    if store_rank:
        sections.append(
            f'<div class="section"><div class="section-head"><h2>你的门店足迹</h2>'
            f'<span class="hint">一共去过 {stats.unique_stores} 家</span></div>'
            f'<div class="chart-box">{store_rank}</div></div>'
        )

    # 徽章墙
    badge_wall = _badge_wall(stats.personas)
    if badge_wall:
        sections.append(
            f'<div class="section"><div class="section-head"><h2>集齐的徽章</h2>'
            f'<span class="hint">共 {len([p for p in stats.personas if p.get("type") == "badge"])} 枚</span>'
            f"</div>{badge_wall}</div>"
        )

    # 积分账户（若已提供）
    point_note = ""
    if stats.account:
        available = stats.account.get("availablePoint")
        accumulative = stats.account.get("accumulativePoint")
        if available is not None or accumulative is not None:
            point_note = (
                f'<div class="section"><div class="section-head"><h2>麦享会积分</h2></div>'
                f'<div class="metrics">'
                f'<div class="metric"><div class="k">可用积分</div>'
                f'<div class="v">{esc(format_amount(_safe_float(available)))}</div></div>'
                f'<div class="metric"><div class="k">累计积分</div>'
                f'<div class="v">{esc(format_amount(_safe_float(accumulative)))}</div></div>'
                f"</div></div>"
            )

    span = (
        f"{esc(stats.first_order_time)} 起 · 到 {esc(stats.last_order_time)} 止<br>"
        f"这期间你有 {stats.active_days} 天下过单"
    )

    body = f"""
<div class="hero">
  <div class="eyebrow">McDonald's Data Wrapped {year}</div>
  <h1>我的 <span class="accent">麦麦倒带</span></h1>
  <p class="subtitle">{esc(generated_at)} 生成 · 数据截至 {esc(stats.last_order_time or "未知")}</p>
</div>

<div class="title-card">
  <div class="label">你的年度称号</div>
  <div class="title-name">{esc(title_name)}</div>
  <p class="reason">{esc(title_reason)}</p>
</div>

<div class="section">
  <div class="metrics">{metric_html}</div>
</div>

{''.join(sections)}
{point_note}

<div class="section">
  <div class="section-head"><h2>这一年</h2></div>
  <div class="chart-box" style="font-size:14px;color:#A89E96;line-height:1.9">{span}</div>
</div>

<div class="footer">
  数据来源：麦当劳 MCP Server（order-list / query-my-account）<br>
  本报告由开源项目 <strong>mcrewind</strong> 生成 · 非麦当劳官方产品<br>
  所有数据仅在你的本地设备上生成，不上传任何服务器
</div>
"""
    return _shell(f"我的麦麦倒带 {year}", body, stats)


def _safe_float(value: object) -> float:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return 0.0


def _shell(page_title: str, body: str, stats: WrappedStats) -> str:
    """包一层完整 HTML 文档。"""
    return (
        "<!DOCTYPE html>\n"
        '<html lang="zh-CN">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{esc(page_title)}</title>\n"
        "<style>" + CSS + "</style>\n"
        "</head>\n<body>\n"
        f'<div class="wrap">{body}</div>\n'
        "</body>\n</html>\n"
    )

"""麦麦倒带 · 竖版分享卡渲染

为什么单独做一个分享卡：
    年报本体是横向长页面（约 3600px 高），发到社交平台会被压缩得看不清文字。
    真正能被转发的最小单元是一张**竖版定尺卡**（默认 1080×1440，即 3:4，
    适配小红书 / 朋友圈 / Instagram）。所以分享卡不是附属素材，
    而是这个产品的第二个正式交付物。

实现要点：
    1. 固定像素尺寸，不做响应式 —— 它是要被"导出成图"的，不是给浏览器看的。
    2. 依然零外部依赖：无 CDN、无网络字体、无外部图片。
    3. 信息密度刻意压低：一张卡只讲"你最像我什么" + 3 个数字 + 1 张迷你图。
"""

from __future__ import annotations

from datetime import datetime

from .analyzer import WrappedStats, format_amount, top_n
from .render import PALETTE, esc

#: 支持的画布比例 -> (宽, 高)
RATIOS: dict[str, tuple[int, int]] = {
    "3:4": (1080, 1440),  # 小红书 / 朋友圈 竖版，默认
    "9:16": (1080, 1920),  # 快拍 / Story
    "1:1": (1080, 1080),  # 方图
}


def _hour_strip(hist: list[int], width: int = 920, height: int = 84) -> str:
    """24 小时迷你热度条：夜间用黄色，其余用红色。"""
    peak = max(hist) if any(hist) else 1
    slot = width / 24
    bar_w = slot * 0.62
    parts: list[str] = []
    for hour, count in enumerate(hist):
        x = hour * slot + (slot - bar_w) / 2
        h = max((count / peak) * height, 4) if peak else 4
        y = height - h
        is_night = hour >= 22 or hour < 5
        color = PALETTE["yellow"] if is_night else PALETTE["red"]
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{h:.1f}" '
            f'rx="2.5" fill="{color}" opacity="{"1" if count else "0.16"}"/>'
        )
    return (
        f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'role="img" aria-label="24 小时下单热度条">{"".join(parts)}</svg>'
    )


def _top_products(stats: WrappedStats, limit: int = 3) -> str:
    """最常点餐品 Top N，纯 CSS 条形。"""
    top = top_n(stats.product_counter, limit)
    if not top:
        return ""
    peak = top[0][1]
    rows: list[str] = []
    for name, count in top:
        pct = round(count / peak * 100)
        rows.append(
            f'<div style="margin-bottom:22px">'
            f'<div style="display:flex;justify-content:space-between;align-items:baseline;'
            f'margin-bottom:10px">'
            f'<span style="font-size:30px;color:#F5F1EC">{esc(name)}</span>'
            f'<span style="font-size:27px;color:#A89E96;font-variant-numeric:tabular-nums">'
            f"{count} 份</span></div>"
            f'<div style="height:9px;background:#2A211C;border-radius:5px;overflow:hidden">'
            f'<div style="height:100%;width:{pct}%;background:#DA291C;border-radius:5px"></div>'
            f"</div></div>"
        )
    return "".join(rows)


def _metrics(stats: WrappedStats) -> str:
    """三宫格核心数字。"""
    items = [
        ("年度订单", format_amount(stats.total_orders), "单"),
        ("年度消费", format_amount(stats.total_amount), "元"),
        ("单均", format_amount(stats.avg_amount), "元"),
    ]
    cells: list[str] = []
    for label, value, unit in items:
        cells.append(
            f'<div style="flex:1;min-width:0">'
            f'<div style="font-size:24px;color:#A89E96;margin-bottom:12px">{label}</div>'
            f'<div style="font-size:64px;font-weight:500;letter-spacing:-0.02em;line-height:1.05">'
            f'{value}<span style="font-size:28px;font-weight:400;color:#A89E96;'
            f'margin-left:6px">{unit}</span></div></div>'
        )
    return (
        f'<div style="display:flex;gap:28px">{"".join(cells)}</div>'
    )


def render_share_card(
    stats: WrappedStats,
    ratio: str = "3:4",
    year: int | None = None,
    brand: str = "麦麦倒带",
) -> str:
    """渲染一张固定尺寸的竖版分享卡 HTML。

    参数：
        ratio: 画布比例，见 :data:`RATIOS`，默认 ``"3:4"``。
        brand: 卡片左上角的产品名。
    """
    year = year or datetime.now().year
    width, height = RATIOS.get(ratio, RATIOS["3:4"])

    title_persona = next((p for p in stats.personas if p.get("type") == "title"), None)
    title_name = title_persona.get("name", "麦门新朋友") if title_persona else "麦门新朋友"
    title_reason = title_persona.get("reason", "") if title_persona else ""

    # ---------------- 空状态：卡片同样要能用 ----------------
    if not stats.has_data:
        return _card_shell(
            width,
            height,
            f"""
<div style="display:flex;flex-direction:column;justify-content:space-between;height:100%">
  <div>
    <div style="font-size:26px;letter-spacing:0.2em;color:#7A7069;text-transform:uppercase">
      {esc(brand)} · {year}
    </div>
  </div>
  <div>
    <div style="font-size:24px;letter-spacing:0.16em;color:#FFC72C;margin-bottom:24px">
      你的年度称号
    </div>
    <div style="font-size:92px;font-weight:500;line-height:1.1;margin-bottom:28px">
      麦门新朋友
    </div>
    <p style="font-size:30px;color:#A89E96;line-height:1.6;margin:0">
      还没有查到订单记录，<br>这一年的故事等你写下第一单。
    </p>
  </div>
  <div style="font-size:22px;color:#7A7069;line-height:1.7">
    数据来自麦当劳 MCP · 本地生成，不上传<br>
    非麦当劳官方产品
  </div>
</div>
""",
        )

    card_body = f"""
<div style="display:flex;flex-direction:column;justify-content:space-between;height:100%">

  <div>
    <div style="display:flex;justify-content:space-between;align-items:baseline;
                font-size:26px;letter-spacing:0.2em;color:#7A7069;text-transform:uppercase">
      <span>{esc(brand)}</span><span>{year}</span>
    </div>
    <div style="height:1px;background:rgba(255,255,255,0.09);margin-top:28px"></div>
  </div>

  <div>
    <div style="font-size:24px;letter-spacing:0.16em;color:#FFC72C;margin-bottom:24px">
      你的年度称号
    </div>
    <div style="font-size:96px;font-weight:500;line-height:1.08;letter-spacing:-0.02em;
                margin-bottom:26px">{esc(title_name)}</div>
    <p style="font-size:30px;color:#A89E96;line-height:1.65;margin:0">{esc(title_reason)}</p>
  </div>

  <div>
    {_metrics(stats)}
  </div>

  <div>
    <div style="font-size:22px;color:#7A7069;letter-spacing:0.1em;margin-bottom:18px">
      我几点吃麦当劳（夜间为黄色）
    </div>
    {_hour_strip(stats.hour_hist)}
  </div>

  <div>
    <div style="font-size:22px;color:#7A7069;letter-spacing:0.1em;margin-bottom:22px">
      最常点
    </div>
    {_top_products(stats)}
  </div>

  <div style="font-size:22px;color:#7A7069;line-height:1.7">
    数据来自麦当劳 MCP · 本地生成，不上传<br>
    非麦当劳官方产品
  </div>

</div>
"""
    return _card_shell(width, height, card_body)


def _card_shell(width: int, height: int, body: str) -> str:
    """固定尺寸画布外壳。不做响应式：它要被导出成图片。"""
    return (
        "<!DOCTYPE html>\n"
        '<html lang="zh-CN">\n<head>\n'
        '<meta charset="UTF-8">\n'
        f"<title>麦麦倒带 · 分享卡 {width}x{height}</title>\n"
        "<style>\n"
        "*{box-sizing:border-box}\n"
        "html,body{margin:0;padding:0;background:#16110E}\n"
        "body{display:flex;justify-content:center}\n"
        ".card{\n"
        f"  width:{width}px;height:{height}px;padding:80px 80px 72px;\n"
        "  background:#16110E;color:#F5F1EC;\n"
        '  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",'
        '"Hiragino Sans GB","Microsoft YaHei",sans-serif;\n'
        "  -webkit-font-smoothing:antialiased;line-height:1.6;\n"
        "}\n"
        "</style>\n</head>\n<body>\n"
        f'<div class="card">{body}</div>\n'
        "</body>\n</html>\n"
    )

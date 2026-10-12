"""麦麦年报 · 趣味标签生成器

这是整个产品的传播引擎。用户愿意把年报截图发出去，靠的不是数据本身，
而是这些「精准戳中自己」的标签。

设计原则：
    1. 标签必须**有依据**（data-driven），不能是随机夸奖，否则用户会觉得假。
    2. 每条标签都要带一个具体数字，数字是可信度的来源。
    3. 语气要「懂梗但不油腻」——用麦当劳社群的语感（麦门、麦门信徒）。
    4. 标签分档：称号（最高级，只给一个）+ 徽章（可多个）。
    5. 数据稀薄时降级为新手上路类标签，绝不输出空数组。
"""

from __future__ import annotations

from .analyzer import WrappedStats, format_amount, format_percent

# ---------------------------------------------------------------------------
# 称号规则（互斥，取优先级最高的一个）
# ---------------------------------------------------------------------------

#: (优先级, 判定函数, 称号, 一句话理由模板)
TITLE_RULES: list[tuple[int, str]] = []


def _title_rules() -> list[tuple[int, object, str, str]]:
    """构建称号规则表。优先级数字越大越优先。"""

    def night_beast(s: WrappedStats) -> bool:
        return s.night_orders >= 5 and s.night_orders / max(s.total_orders, 1) >= 0.2

    def breakfast_keeper(s: WrappedStats) -> bool:
        return s.breakfast_orders >= 8

    def power_user(s: WrappedStats) -> bool:
        return s.total_orders >= 60

    def bundle_hunter(s: WrappedStats) -> bool:
        # 单均低于 25 元说明很会凑单
        return s.total_orders >= 10 and s.avg_amount <= 25

    def big_spender(s: WrappedStats) -> bool:
        return s.total_orders >= 10 and s.avg_amount >= 55

    def store_pilgrim(s: WrappedStats) -> bool:
        return s.unique_stores >= 8

    def loyalist(s: WrappedStats) -> bool:
        return s.total_orders >= 30

    def regular(s: WrappedStats) -> bool:
        return s.total_orders >= 10

    return [
        (100, night_beast, "深夜麦门信徒", "有 {night} 单下在了 22 点之后，占全部订单的 {p}。"),
        (95, power_user, "麦门重度用户", "一年 {n} 单，平均 {d} 天就点一次。"),
        (90, store_pilgrim, "麦麦巡礼者", "足迹遍布 {stores} 家门店，最常去的是「{store}」。"),
        (85, breakfast_keeper, "早餐守门员", "早上 10 点前下单 {breakfast} 次，早餐是你的主场。"),
        (80, big_spender, "麦门豪客", "单均 {a} 元，{n} 单下来一共花了 {total} 元。"),
        (75, bundle_hunter, "精算型麦门", "单均只要 {a} 元，{n} 单总共才花 {total} 元。"),
        (70, loyalist, "麦门常驻民", "一年 {n} 单，你已经是这里的熟客了。"),
        (60, regular, "麦门忠实用户", "一年 {n} 单，稳定的快乐来源。"),
    ]


def _render_reason(template: str, s: WrappedStats) -> str:
    """把理由模板里的占位符替换成真实数字。

    可用占位符：
        {n}         总订单数
        {d}         平均下单间隔（天）
        {a}         单均消费
        {total}     年度总消费
        {p}         夜间订单占比
        {store}     最常去门店
        {night}     夜间订单数（22 点后）
        {breakfast} 早餐时段订单数
        {stores}    去过的门店数
    """
    top_store = s.top_stores[0][0] if s.top_stores else "未知门店"
    avg_interval = round(s.span_days / max(s.total_orders, 1))
    return template.format(
        n=s.total_orders,
        d=avg_interval,
        a=format_amount(s.avg_amount),
        total=format_amount(s.total_amount),
        p=format_percent(s.night_orders, s.total_orders),
        store=top_store,
        night=s.night_orders,
        breakfast=s.breakfast_orders,
        stores=s.unique_stores,
    )


# ---------------------------------------------------------------------------
# 徽章规则（可叠加，最多展示 6 个）
# ---------------------------------------------------------------------------


def _build_badges(s: WrappedStats) -> list[dict[str, str]]:
    badges: list[dict[str, str]] = []

    def add(icon: str, name: str, detail: str) -> None:
        badges.append({"icon": icon, "name": name, "detail": detail})

    # --- 时间维度 ---
    if s.night_orders >= 3:
        add("moon", "夜宵战神", f"22 点后下单 {s.night_orders} 次")
    if s.breakfast_orders >= 5:
        add("sun", "早起鸟", f"早餐时段 {s.breakfast_orders} 单")
    if s.peak_hour >= 0:
        add("clock", f"{s.peak_hour:02d}:00 党", f"最常在这个点下单，共 {s.hour_hist[s.peak_hour]} 单")

    # --- 口味维度 ---
    if s.top_products:
        top_name, top_count = s.top_products[0]
        if top_count >= 5:
            add("star", f"{top_name}死忠粉", f"一年点了 {top_count} 份")
    if s.unique_products >= 25:
        add("shuffle", "菜单探索家", f"尝试过 {s.unique_products} 种不同餐品")
    elif s.unique_products and s.unique_products <= 5:
        add("lock", "专一党", f"一年只点 {s.unique_products} 种，认准了就不换")

    # --- 渠道维度 ---
    for channel, count, share in _channel_shares(s):
        if share >= 0.5 and count >= 5:
            label = {
                "麦乐送": "宅家麦门",
                "到店自取": "线下打卡派",
                "得来速": "车轮上的麦门",
                "企业团餐": "团餐组织者",
            }.get(channel)
            if label:
                add("route", label, f"{channel} 占 {round(share * 100)}%")
            break

    # --- 消费维度 ---
    if s.max_order_amount >= 80:
        add("wallet", "豪横时刻", f"最大一笔 {format_amount(s.max_order_amount)} 元")
    if s.unique_stores >= 5:
        add("pin", "门店收集者", f"去过 {s.unique_stores} 家门店")

    # --- 频率维度 ---
    if s.active_days >= 20:
        add("fire", "高频用户", f"一年有 {s.active_days} 天下过单")

    return badges[:6]


def _channel_shares(s: WrappedStats) -> list[tuple[str, int, float]]:
    total = sum(s.channel_counter.values())
    return [
        (name, count, count / total if total else 0.0)
        for name, count in sorted(s.channel_counter.items(), key=lambda kv: -kv[1])
    ]


# ---------------------------------------------------------------------------
# 对外入口
# ---------------------------------------------------------------------------


def generate_personas(stats: WrappedStats) -> list[dict[str, str]]:
    """生成称号 + 徽章。永远返回非空列表。"""
    personas: list[dict[str, str]] = []

    if not stats.has_data:
        personas.append(
            {
                "type": "title",
                "name": "麦门新朋友",
                "reason": "还没有查到历史订单，这一年的故事等你写下第一单。",
            }
        )
        return personas

    # 1) 称号：按优先级取第一个命中的规则
    matched_title = None
    for priority, predicate, name, reason_tpl in sorted(_title_rules(), key=lambda r: -r[0]):
        if predicate(stats):
            matched_title = {
                "type": "title",
                "name": name,
                "reason": _render_reason(reason_tpl, stats),
                "priority": str(priority),
            }
            break

    if matched_title is None:
        matched_title = {
            "type": "title",
            "name": "麦门路人甲",
            "reason": f"一年 {stats.total_orders} 单，不多不少，刚刚好。",
            "priority": "0",
        }
    personas.append(matched_title)

    # 2) 徽章
    personas.extend({"type": "badge", **badge} for badge in _build_badges(stats))

    return personas

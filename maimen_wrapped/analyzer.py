"""麦麦年报 · 数据聚合分析模块

把麦当劳 MCP `order-list` 返回的原始订单数据，聚合成年报所需的全部统计指标。

数据契约（来自 MCP `order-list` 真实返回结构）::

    {
      "success": true,
      "data": {
        "list": [
          {
            "orderId": "1030108270000795607354880945",
            "orderType": "1",
            "createTime": "2026-03-14 08:12:33",
            "beType": "1",
            "beCode": "",
            "storeCode": "1001234",
            "storeName": "麦当劳(中关村店)",
            "orderStatus": "5",
            "orderProductList": [
              {"productCode": "1001", "productName": "巨无霸", "quantity": 1, "comboItemList": []}
            ],
            "realTotalAmount": "35.50"
          }
        ]
      }
    }

设计原则：
    1. 绝不因为数据缺失而抛异常 —— 任何字段缺失都降级为空值。
    2. 所有金额统一按「元」处理（浮点数，两位小数）。
    3. 只统计已完成订单，避免把取消单算进消费额。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# 常量映射
# ---------------------------------------------------------------------------

#: beType -> 渠道中文名
CHANNEL_NAMES: dict[str, str] = {
    "1": "到店自取",
    "2": "麦乐送",
    "5": "得来速",
    "6": "企业团餐",
}

#: 订单状态码 -> 是否计入统计（只统计已完成的单）
COMPLETED_STATUS: frozenset[str] = frozenset({"4", "5", "6", "7", "8"})

WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
HOUR_BUCKETS = list(range(24))


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def parse_time(value: Any) -> datetime | None:
    """尽最大努力把 createTime 解析成 datetime，失败返回 None。"""
    if not value or not isinstance(value, str):
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    return None


def parse_amount(value: Any) -> float:
    """把 realTotalAmount 解析成「元」。无法解析时返回 0.0。"""
    if value is None:
        return 0.0
    try:
        amount = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0
    return round(amount, 2)


def unwrap_orders(payload: Any) -> list[dict[str, Any]]:
    """从 MCP 返回的多种可能外壳里，稳健地取出订单列表。

    兼容以下形态：
        - {"data": {"list": [...]}}      # order-list 正常返回
        - {"data": [...]}                # 直接是数组
        - [...]                          # 裸数组
        - {"data": {}}                   # 空账号，返回空列表
    """
    if payload is None:
        return []
    node: Any = payload
    if isinstance(node, dict):
        node = node.get("data", node)
    if isinstance(node, dict):
        node = node.get("list", [])
    if not isinstance(node, list):
        return []
    return [item for item in node if isinstance(item, dict)]


# ---------------------------------------------------------------------------
# 统计结果
# ---------------------------------------------------------------------------


@dataclass
class WrappedStats:
    """一份年报所需的全部聚合指标。"""

    # 总量
    total_orders: int = 0
    total_amount: float = 0.0
    avg_amount: float = 0.0
    max_order_amount: float = 0.0
    max_order_name: str = ""
    max_order_time: str = ""

    # 时间跨度
    first_order_time: str = ""
    last_order_time: str = ""
    active_days: int = 0
    span_days: int = 0

    # 分布
    hour_hist: list[int] = field(default_factory=lambda: [0] * 24)
    weekday_hist: list[int] = field(default_factory=lambda: [0] * 7)
    month_hist: list[int] = field(default_factory=lambda: [0] * 12)

    # 口味 / 渠道 / 门店
    product_counter: dict[str, int] = field(default_factory=dict)
    channel_counter: dict[str, int] = field(default_factory=dict)
    store_counter: dict[str, int] = field(default_factory=dict)

    # 衍生指标
    night_orders: int = 0
    breakfast_orders: int = 0
    lunch_orders: int = 0
    dinner_orders: int = 0

    # 积分账户（来自 query-my-account）
    account: dict[str, Any] = field(default_factory=dict)

    # 标签
    personas: list[dict[str, str]] = field(default_factory=list)

    # 元信息
    has_data: bool = False
    data_quality_note: str = ""

    # -- 便捷属性 ---------------------------------------------------------

    @property
    def peak_hour(self) -> int:
        if not any(self.hour_hist):
            return -1
        return max(range(24), key=lambda h: self.hour_hist[h])

    @property
    def peak_weekday(self) -> int:
        if not any(self.weekday_hist):
            return -1
        return max(range(7), key=lambda d: self.weekday_hist[d])

    @property
    def top_products(self) -> list[tuple[str, int]]:
        return sorted(self.product_counter.items(), key=lambda kv: -kv[1])

    @property
    def top_channels(self) -> list[tuple[str, int]]:
        return sorted(self.channel_counter.items(), key=lambda kv: -kv[1])

    @property
    def top_stores(self) -> list[tuple[str, int]]:
        return sorted(self.store_counter.items(), key=lambda kv: -kv[1])

    @property
    def unique_products(self) -> int:
        return len(self.product_counter)

    @property
    def unique_stores(self) -> int:
        return len(self.store_counter)


# ---------------------------------------------------------------------------
# 主分析入口
# ---------------------------------------------------------------------------


def analyze(payload: Any, account: dict[str, Any] | None = None) -> WrappedStats:
    """把原始订单 JSON 聚合为 :class:`WrappedStats`。"""
    stats = WrappedStats()
    stats.account = account or {}

    orders = unwrap_orders(payload)
    if not orders:
        stats.has_data = False
        stats.data_quality_note = (
            "未查询到任何历史订单。年报将进入「空状态」展示，"
            "请确认 MCP Token 对应的麦当劳会员账号是否已完成过下单。"
        )
        return stats

    times: list[datetime] = []

    for order in orders:
        status = str(order.get("orderStatus", "")).strip()
        # 若状态字段存在且明确不属于已完成集合，则跳过（避免把取消单算入）
        if status and status not in COMPLETED_STATUS:
            # 状态字段语义未文档化，过于激进地过滤会丢数据，
            # 因此只在状态明确表示「已取消/已退款」时跳过。
            if status in {"0", "1", "2", "-1"}:
                continue

        amount = parse_amount(order.get("realTotalAmount"))
        stats.total_amount += amount
        stats.total_orders += 1

        # 最大单笔
        if amount > stats.max_order_amount:
            stats.max_order_amount = amount
            products = order.get("orderProductList") or []
            names: list[str] = []
            for p in products:
                if not isinstance(p, dict) or not p.get("productName"):
                    continue
                try:
                    qty = int(p.get("quantity") or 1)
                except (TypeError, ValueError):
                    qty = 1
                label = str(p["productName"]).strip()
                # 带上数量，否则「早餐全餐×2 + 咖啡」会被误读成两样共 1 份
                names.append(f"{label}×{qty}" if qty > 1 else label)
            stats.max_order_name = " + ".join(names[:3]) if names else "未知订单"
            stats.max_order_time = str(order.get("createTime", ""))

        # 时间维度
        moment = parse_time(order.get("createTime"))
        if moment:
            times.append(moment)
            stats.hour_hist[moment.hour] += 1
            stats.weekday_hist[moment.weekday()] += 1
            stats.month_hist[moment.month - 1] += 1

            hour = moment.hour
            if hour >= 22 or hour < 5:
                stats.night_orders += 1
            elif 5 <= hour < 10:
                stats.breakfast_orders += 1
            elif 11 <= hour < 14:
                stats.lunch_orders += 1
            elif 17 <= hour < 21:
                stats.dinner_orders += 1

        # 渠道
        be_type = str(order.get("beType", "")).strip()
        channel = CHANNEL_NAMES.get(be_type, "其他渠道")
        stats.channel_counter[channel] = stats.channel_counter.get(channel, 0) + 1

        # 门店
        store = str(order.get("storeName", "")).strip()
        if store:
            stats.store_counter[store] = stats.store_counter.get(store, 0) + 1

        # 商品：把套餐子项也计入
        for product in order.get("orderProductList") or []:
            if not isinstance(product, dict):
                continue
            name = str(product.get("productName", "")).strip()
            qty = product.get("quantity") or 1
            try:
                qty = int(qty)
            except (TypeError, ValueError):
                qty = 1
            if name:
                stats.product_counter[name] = stats.product_counter.get(name, 0) + max(qty, 1)

    # 衍生指标
    stats.has_data = stats.total_orders > 0
    if stats.total_orders:
        stats.avg_amount = round(stats.total_amount / stats.total_orders, 2)

    if times:
        times.sort()
        stats.first_order_time = times[0].strftime("%Y-%m-%d %H:%M")
        stats.last_order_time = times[-1].strftime("%Y-%m-%d %H:%M")
        stats.active_days = len({t.date() for t in times})
        stats.span_days = max((times[-1].date() - times[0].date()).days, 1)

    if not stats.has_data:
        stats.data_quality_note = "订单列表为空，已降级为空状态报告。"

    return stats


def format_amount(value: float) -> str:
    """金额格式化：整数不带小数，否则保留两位。"""
    if abs(value - round(value)) < 0.005:
        return f"{int(round(value))}"
    return f"{value:.2f}"


def format_percent(part: int, whole: int) -> str:
    """安全百分比，分母为 0 时返回 0%。"""
    if not whole:
        return "0%"
    return f"{round(part / whole * 100)}%"


def top_n(counter: dict[str, int], n: int) -> list[tuple[str, int]]:
    return sorted(counter.items(), key=lambda kv: -kv[1])[:n]


def iter_channel_shares(counter: dict[str, int]) -> Iterable[tuple[str, int, float]]:
    """产出 (渠道名, 单数, 占比 0~1)。"""
    total = sum(counter.values())
    for name, count in sorted(counter.items(), key=lambda kv: -kv[1]):
        yield name, count, (count / total if total else 0.0)

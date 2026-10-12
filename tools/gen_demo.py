"""生成演示数据集（固定随机种子，结果可复现）。

为什么要专门做一个 demo 数据集，而不是让用户跑自己的真实订单：
    1. README 的截图 / GIF 需要一份**好看但不涉隐私**的数据；
    2. 大多数评审者不会配置 MCP Token，demo 让他们无需任何凭证就能看到成果；
    3. 固定种子 + 稳定编码 → 每次生成的报告完全一致，可用于回归测试。

运行：python tools/gen_demo.py
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

random.seed(1024)

OUT_DIR = Path(__file__).resolve().parent.parent / "assets" / "demo"

# (商品名, 单价, 所属品类)
MENU: list[tuple[str, float, str]] = [
    ("巨无霸", 22.0, "主食"),
    ("麦辣鸡腿堡", 21.0, "主食"),
    ("板烧鸡腿堡", 21.0, "主食"),
    ("双层吉士汉堡", 18.0, "主食"),
    ("麦香鱼", 15.0, "主食"),
    ("猪柳蛋麦满分", 16.5, "早餐"),
    ("早餐全餐", 24.0, "早餐"),
    ("热香饼", 14.0, "早餐"),
    ("麦辣鸡翅", 13.5, "小食"),
    ("麦乐鸡(5块)", 12.5, "小食"),
    ("中薯条", 11.5, "小食"),
    ("大薯条", 13.5, "小食"),
    ("玉米杯", 9.5, "小食"),
    ("苹果派", 8.5, "小食"),
    ("香芋派", 8.5, "小食"),
    ("可乐(中)", 9.5, "饮料"),
    ("可乐(大)", 11.0, "饮料"),
    ("雪碧(中)", 9.5, "饮料"),
    ("橙汁", 12.0, "饮料"),
    ("拿铁", 17.5, "饮料"),
    ("美式咖啡", 13.0, "饮料"),
    ("麦旋风", 13.5, "甜品"),
    ("原味甜筒", 6.0, "甜品"),
    ("新地", 9.5, "甜品"),
]

#: 商品名 -> 稳定的 productCode（不使用内置 hash()，它在不同进程间是随机化的）
MENU_CODE: dict[str, str] = {
    name: f"P{1001 + idx * 7:04d}" for idx, (name, _price, _cat) in enumerate(MENU)
}
MENU_PRICE: dict[str, float] = {name: price for name, price, _cat in MENU}

STORES = [
    "麦当劳(中关村大街店)",
    "麦当劳(五道口购物中心店)",
    "麦当劳(知春路店)",
    "麦当劳(西直门凯德店)",
    "麦当劳(清华科技园店)",
    "麦当劳(北京南站店)",
    "麦当劳(三里屯太古里店)",
    "麦当劳(望京SOHO店)",
    "麦当劳(首都机场T3店)",
]

# 下单时段权重：早高峰 + 午间 + 深夜三个峰
HOUR_WEIGHTS = {
    0: 2, 1: 1, 2: 1, 3: 0, 4: 0,
    5: 1, 6: 3, 7: 7, 8: 9, 9: 5,
    10: 3, 11: 6, 12: 9, 13: 7, 14: 4,
    15: 3, 16: 3, 17: 5, 18: 7, 19: 6,
    20: 5, 21: 5, 22: 6, 23: 4,
}

# 星期权重：周末略高
WEEKDAY_WEIGHTS = [5, 5, 5, 6, 8, 9, 7]

TOTAL_DAYS = (datetime(2026, 10, 10) - datetime(2026, 1, 6)).days


def pick_hour() -> int:
    return random.choices(list(HOUR_WEIGHTS.keys()), weights=list(HOUR_WEIGHTS.values()), k=1)[0]


def make_item(name: str, quantity: int = 1) -> dict:
    return {
        "productCode": MENU_CODE[name],
        "productName": name,
        "quantity": quantity,
        "comboItemList": [],
    }


def build_order(order_no: int, moment: datetime) -> dict:
    hour = moment.hour
    is_breakfast = 5 <= hour < 10

    # 早餐时段点早餐，其他时段点正餐
    pool = [m for m in MENU if m[2] == "早餐"] if is_breakfast else [m for m in MENU if m[2] == "主食"]
    main_name = random.choice(pool)[0]
    items = [make_item(main_name)]

    # 约 70% 的订单会加小食或饮料
    if random.random() < 0.7:
        extra_pool = [m for m in MENU if m[2] in ("小食", "饮料")]
        items.append(make_item(random.choice(extra_pool)[0]))

    # 偶发「一次点两人份」
    if random.random() < 0.08:
        items[0]["quantity"] = 2

    # 深夜单偶尔加点甜品
    if hour >= 22 and random.random() < 0.4:
        items.append(make_item(random.choice([m for m in MENU if m[2] == "甜品"])[0]))

    # 实际支付金额：偶尔用券，比标价略低
    gross = sum(MENU_PRICE[it["productName"]] * it["quantity"] for it in items)
    amount = round(gross * random.uniform(0.90, 1.0), 2)

    # 渠道：深夜更多用麦乐送，白天以到店为主
    weights = [4, 5, 1] if (hour >= 21 or hour < 6) else [12, 4, 2]
    be_type = random.choices(["1", "2", "5"], weights=weights, k=1)[0]

    store = random.choice(STORES[:6] if be_type == "2" else STORES)

    return {
        "orderId": f"103010827000079560735488{order_no:04d}",
        "orderType": "2" if be_type in ("2", "6") else "1",
        "createTime": moment.strftime("%Y-%m-%d %H:%M:%S"),
        "beType": be_type,
        "beCode": f"BE{1000 + order_no}" if be_type == "5" else "",
        "storeCode": f"{1001000 + order_no % 60}",
        "storeName": store,
        "orderStatus": "5",
        "orderProductList": items,
        "realTotalAmount": f"{amount:.2f}",
    }


def build_orders() -> list[dict]:
    orders: list[dict] = []
    start = datetime(2026, 1, 6, 8, 0, 0)
    end = datetime(2026, 10, 10, 23, 0, 0)

    # 先随机挑一批「想下单的日子」，再按星期权重二次筛选，
    # 让分布呈现真实用户的「周末略多、工作日早餐稳定」的形态
    candidate_days = sorted(random.sample(range(TOTAL_DAYS), 150))
    order_no = 1

    for day_offset in candidate_days:
        day = start + timedelta(days=day_offset, hours=pick_hour(), minutes=random.randint(0, 59))
        if random.random() > WEEKDAY_WEIGHTS[day.weekday()] / 10:
            continue

        orders.append(build_order(order_no, day))
        order_no += 1

        # 约 1/4 的下单日会点第二单
        if random.random() < 0.25:
            second = day + timedelta(hours=random.randint(3, 8), minutes=random.randint(0, 59))
            if second <= end:
                orders.append(build_order(order_no, second))
                order_no += 1

    orders.sort(key=lambda o: o["createTime"])
    return orders


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    orders = build_orders()

    payload = {
        "success": True,
        "code": 200,
        "message": "请求成功（演示数据）",
        "data": {"list": orders},
    }
    account = {
        "success": True,
        "code": 200,
        "message": "请求成功（演示数据）",
        "data": {
            "accountId": "DEMO000000000000000000000000",
            "availablePoint": "386.5",
            "accumulativePoint": "2418",
            "currency": "麦享会积分",
            "currentMouthExpirePoint": "42.0",
            "expiredPoint": "86.0",
            "frozenPoint": "0",
            "lastMouthExpirePoint": "0",
            "nextMouthExpirePoint": "58.0",
            "usedPoint": "1240",
        },
    }

    (OUT_DIR / "demo_orders.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT_DIR / "demo_account.json").write_text(
        json.dumps(account, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    total = sum(float(o["realTotalAmount"]) for o in orders)
    print(f"已生成 {len(orders)} 条演示订单，合计 {total:.2f} 元 → {OUT_DIR}")


if __name__ == "__main__":
    main()

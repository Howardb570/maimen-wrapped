# MCP 集成说明（MCP_INTEGRATION.md）

本文档说明麦麦倒带（mcrewind）实际使用的麦当劳 MCP Server、Tool、
完整调用流程，以及这些能力带来的业务价值。

---

## 1. 使用的 MCP Server

| 项目 | 值 |
|---|---|
| Server 名称 | `mcd-mcp` |
| 端点 | `https://mcp.mcd.cn` |
| 协议 | Streamable HTTP |
| 鉴权方式 | `Authorization: Bearer <MCP_TOKEN>`（通过 HTTP Header 传递） |
| Token 获取 | 麦当劳 MCP 控制台申请（见[官方指南](https://github.com/M-China/mcd-mcp-server)） |

脱敏后的配置示例见 [mcp-config.example.json](mcp-config.example.json)，
其中 Token 一律使用环境变量占位符 `${MCD_MCP_TOKEN}`。

---

## 2. 使用的 Tool 清单

### 2.1 核心必需

#### `order-list`

- **入参**：无
- **作用**：读取当前会员账号的历史订单列表
- **返回关键字段**：

| 字段 | 含义 | 在年报中的用途 |
|---|---|---|
| `data.list[].createTime` | 下单时间 | 24 小时分布、星期分布、活跃天数 |
| `data.list[].realTotalAmount` | 实付金额 | 年度消费、单均消费、最大单笔 |
| `data.list[].orderProductList[].productName` | 商品名 | 口味画像 Top 5 |
| `data.list[].orderProductList[].quantity` | 数量 | 商品份数聚合、最大单笔明细 |
| `data.list[].beType` | 渠道类型 | 到店 / 麦乐送 / 得来速 占比 |
| `data.list[].storeName` | 门店名称 | 门店足迹排行 |
| `data.list[].orderStatus` | 订单状态 | 剔除已取消/已退款订单 |

**这是整个产品的唯一核心数据源**，没有它就没有年报。

### 2.2 建议使用

#### `query-my-account`

- **入参**：无
- **作用**：读取麦享会积分账户
- **使用字段**：`availablePoint`（可用积分）、`accumulativePoint`（累计积分）
- **用途**：年报末尾的"麦享会积分"板块

### 2.3 可选使用

| Tool | 用途 | 说明 |
|---|---|---|
| `query-my-prizes` | 抽奖奖品记录 | 预留字段，当前版本未在报告中展示 |
| `mall-order-list` | 麦麦商城订单 | 预留字段，当前版本未在报告中展示 |

### 2.4 明确不使用

| Tool | 不用的原因 |
|---|---|
| `query-my-coupons` | 该工具返回的是**渲染后的文本**而非结构化 JSON，无法可靠统计，强行解析会产生脏数据 |
| `create-order` / `calculate-price` 等交易类工具 | 本 Skill 是只读的回顾型产品，**不涉及任何下单行为**，避免误触发交易 |

---

## 3. 调用流程

```text
用户："生成我的麦麦倒带"
        │
        ▼
┌─────────────────────────────────────────┐
│ 阶段一：采集（WorkBuddy 智能体执行）        │
│                                         │
│  mcp__mcd-mcp__order-list      ─┐        │
│  mcp__mcd-mcp__query-my-account ─┤ 原始   │
│  mcp__mcd-mcp__query-my-prizes  ─┘ JSON  │
│        │                                 │
│        ▼ 落盘到 .mcrewind-raw/         │
└─────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────┐
│ 阶段二：分析（本地 Python，完全离线）       │
│                                         │
│  python -m mcrewind                   │
│   --orders  .mcrewind-raw/orders.json │
│   --account .mcrewind-raw/account.json│
│   --out     我的麦麦倒带.html             │
│                                         │
│  analyzer.py  → 聚合统计 + 字段容错       │
│  persona.py   → 称号与徽章规则匹配        │
│  render.py    → 单文件 HTML 渲染         │
└─────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────┐
│ 阶段三：展示                              │
│  present_files 打开 HTML，用户直接预览/截图 │
└─────────────────────────────────────────┘
```

### 关键设计：为什么 MCP 调用和数据分析要分离

1. **隐私**：阶段二完全离线。分析脚本只读本地文件，不发任何网络请求，
   用户数据不出本机。
2. **可测试**：固定输入可以复现固定输出。仓库内置的 `assets/demo/`
   演示数据让任何人不配 Token 也能看到完整成果。
3. **可降级**：账号无订单时 `order-list` 返回空的 `data: {}`，
   分析脚本会生成体面的空状态引导页，而不是抛异常。

---

## 4. 数据容错策略

MCP 返回结构未在官方文档中完整描述，因此分析层做了大量防御性处理：

| 场景 | 处理方式 |
|---|---|
| `data` 为 `{}` 或 `null` | 视为无订单，走空状态降级 |
| `createTime` 格式变体 | 依次尝试 4 种常见格式，全部失败则该订单不计入时间维度 |
| `realTotalAmount` 含逗号或非数字 | 清洗后解析，失败按 0 元计，不让单条脏数据炸掉整份报告 |
| `quantity` 缺失或非法 | 按 1 处理 |
| 商品 `productName` 为空 | 跳过，不计入口味画像 |
| 套餐子项 `comboItemList` | 子项同样计入口味画像 |
| 未知 `beType` | 归入"其他渠道"，不丢弃订单 |

---

## 5. 业务价值

### 对用户

- **自我认知**：第一次能回答"我一年在麦当劳花了多少钱、几点吃最凶"这个问题
- **社交货币**：年度称号是可截图、可转发的结论，不是一串冷冰冰的数字
- **零门槛**：不需要看懂任何数据，打开 HTML 就能看懂

### 对麦当劳 MCP 生态

- **展示了只读类 Skill 的完整范式**：采集 → 落盘 → 离线分析 → 可视化，
  全程不触发交易，适合作为其他"回顾型 / 报表型"Skill 的参考实现
- **验证了非交易场景的价值**：MCP 能力不只能用来点餐，
  用户已有的历史数据同样能产出情感价值
- **零依赖的交付形态**：单文件 HTML 可以脱离 WorkBuddy 环境传播，
  让 Skill 的成果能被"圈外用户"看到——这是普通对话型 Skill 做不到的

### 明确的边界

- 本 Skill **只读**，不调用任何下单、支付、取消类交易工具
- 本 Skill **不构成营养或健康建议**，餐品信息以麦当劳官方渠道为准

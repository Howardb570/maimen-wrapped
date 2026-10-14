"""麦麦倒带 · mcrewind

把麦当劳 MCP Server 返回的个人订单数据，变成一份可截图、可转发、
零外部依赖的单文件 HTML 年报。

用法::

    python -m mcrewind --demo
    python -m mcrewind --orders orders.json --account account.json --out my-rewind.html
"""

__version__ = "1.0.0"
__all__ = ["analyzer", "persona", "render"]

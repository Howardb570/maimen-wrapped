"""麦麦年报 · maimen-wrapped

把麦当劳 MCP Server 返回的个人订单数据，变成一份可截图、可转发、
零外部依赖的单文件 HTML 年报。

用法::

    python -m maimen_wrapped --demo
    python -m maimen_wrapped --orders orders.json --account account.json --out my-wrapped.html
"""

__version__ = "1.0.0"
__all__ = ["analyzer", "persona", "render"]

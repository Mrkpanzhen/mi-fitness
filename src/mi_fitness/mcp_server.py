"""MCP server：把健康数据查询暴露为 MCP 工具。

通过 stdio 传输运行，供支持 MCP 的 agent 直接调用：

    mi-fitness-mcp

工具列表：
    list_relatives         列出亲友
    get_latest_data        查询亲友最新数据快照
    get_history            查询按日历史数据
    get_daily_summary      查询每日综合摘要
    get_shared_data_types  查询亲友共享的数据类型
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date
from typing import Any, TypeVar

from mi_fitness.client import MiHealthClient
from mi_fitness.exceptions import MiSDKError
from mi_fitness.query import HISTORY_KEYS, resolve_relative_uid, resolve_token_path
from mi_fitness.query import get_history as query_history
from mi_fitness.query import get_latest as query_latest
from mi_fitness.query import get_summary as query_summary
from mi_fitness.query import list_relatives as query_relatives

try:
    from mcp.server.mcpserver import MCPServer
    from mcp.server.mcpserver.exceptions import ToolError
except ModuleNotFoundError as e:  # pragma: no cover - 依赖未安装时的提示
    raise SystemExit("MCP server 需要安装 mcp：pip install 'mi-fitness[mcp]'") from e

_T = TypeVar("_T")

mcp = MCPServer(
    name="mi-fitness",
    instructions=(
        "小米运动健康亲友数据。首次使用需先用 `mi-fitness qr-login` 扫码登录生成 token.json；"
        "token 路径可用环境变量 MI_FITNESS_TOKEN 覆盖。所有时间按中国标准时间（UTC+8）。"
    ),
)


async def _with_client(call: Callable[[MiHealthClient], Awaitable[_T]]) -> _T:
    """创建客户端并执行查询。

    预期内的失败（token 缺失/过期、未共享数据等）转换为 ``ToolError``，
    MCP 会把消息原样回传给调用方，便于 agent 判断下一步。
    """
    try:
        async with MiHealthClient.from_token(resolve_token_path()) as client:
            return await call(client)
    except MiSDKError as e:
        raise ToolError(f"{type(e).__name__}: {e}") from e


async def _resolve_uid(
    client: MiHealthClient,
    relative_uid: int | None,
    relative: str,
) -> int:
    """确定目标亲友 UID。"""
    if relative_uid is not None:
        return relative_uid
    if not relative:
        raise ToolError("请提供 relative_uid 或 relative（备注名）")
    try:
        return resolve_relative_uid(await query_relatives(client), relative)
    except LookupError as e:
        raise ToolError(str(e)) from e


def _parse_date(value: str) -> date | None:
    """把可选的 YYYY-MM-DD 字符串解析为日期。"""
    return date.fromisoformat(value) if value else None


@mcp.tool()
async def list_relatives() -> list[dict[str, Any]]:
    """列出所有已绑定的亲友及其 UID、备注名和最近同步时间。"""
    return await _with_client(query_relatives)


@mcp.tool()
async def get_latest_data(
    relative_uid: int | None = None,
    relative: str = "",
) -> dict[str, Any]:
    """查询亲友的最新健康数据快照。

    Args:
        relative_uid: 亲友 UID，优先使用。
        relative: 亲友备注名（支持子串匹配），relative_uid 为空时使用。
    """

    async def call(client: MiHealthClient) -> dict[str, Any]:
        uid = await _resolve_uid(client, relative_uid, relative)
        return await query_latest(client, uid)

    return await _with_client(call)


@mcp.tool()
async def get_history(
    key: str,
    relative_uid: int | None = None,
    relative: str = "",
    query_date: str = "",
    days: int = 1,
) -> list[dict[str, Any]]:
    """查询亲友按日聚合的历史数据。

    Args:
        key: 数据类型，可选 heart_rate / sleep / steps / blood_pressure /
            calories / valid_stand / intensity / weight / spo2。
        relative_uid: 亲友 UID，优先使用。
        relative: 亲友备注名，relative_uid 为空时使用。
        query_date: 窗口结束日，格式 YYYY-MM-DD，默认今天。
        days: 窗口天数，1..365。
    """
    if key not in HISTORY_KEYS:
        raise ToolError(f"不支持的 key: {key}（可选: {', '.join(HISTORY_KEYS)}）")
    parsed_date = _parse_date(query_date)

    async def call(client: MiHealthClient) -> list[dict[str, Any]]:
        uid = await _resolve_uid(client, relative_uid, relative)
        return await query_history(client, uid, key, query_date=parsed_date, days=days)

    return await _with_client(call)


@mcp.tool()
async def get_daily_summary(
    relative_uid: int | None = None,
    relative: str = "",
    query_date: str = "",
    latest: bool = False,
) -> dict[str, Any]:
    """查询亲友每日综合摘要（心率 + 睡眠 + 步数）。

    Args:
        relative_uid: 亲友 UID，优先使用。
        relative: 亲友备注名，relative_uid 为空时使用。
        query_date: 查询日期，格式 YYYY-MM-DD，默认今天。
        latest: 为 True 时使用最近一次同步日（优先于 query_date）。
    """
    parsed_date = _parse_date(query_date)

    async def call(client: MiHealthClient) -> dict[str, Any]:
        uid = await _resolve_uid(client, relative_uid, relative)
        return await query_summary(client, uid, query_date=parsed_date, latest=latest)

    return await _with_client(call)


@mcp.tool()
async def get_shared_data_types(
    relative_uid: int | None = None,
    relative: str = "",
) -> list[str]:
    """查询亲友对当前账号共享了哪些数据类型。"""

    async def call(client: MiHealthClient) -> list[str]:
        uid = await _resolve_uid(client, relative_uid, relative)
        return await client.get_shared_data_types(uid)

    return await _with_client(call)


def main() -> None:
    """以 stdio 传输启动 MCP server。"""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

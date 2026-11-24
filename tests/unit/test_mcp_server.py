"""测试 MCP server 的工具注册与调用逻辑。"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Self

import pytest
from mcp.server.mcpserver.exceptions import ToolError

import mi_fitness.mcp_server as mcp_server
from mi_fitness.exceptions import TokenExpiredError
from mi_fitness.models import DailySummary, FamilyMember, LatestDataSnapshot, StepData


class _FakeClient:
    def __init__(self, *args: object, **kwargs: object) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    @classmethod
    def from_token(cls, path: Path | str) -> Self:
        return cls()

    async def get_relatives(self) -> list[FamilyMember]:
        self.calls.append(("relatives", ()))
        return [FamilyMember(relative_uid=1, relative_note="妈妈")]

    async def get_latest_data(self, uid: int) -> LatestDataSnapshot:
        self.calls.append(("latest", (uid,)))
        return LatestDataSnapshot(steps=StepData(steps=7))

    async def get_steps(
        self, uid: int, query_date: date | None, *, days: int = 1
    ) -> list[StepData]:
        self.calls.append(("steps", (uid, query_date, days)))
        return [StepData(steps=7)]

    async def get_daily_summary(self, uid: int, query_date: date | None = None) -> DailySummary:
        self.calls.append(("summary", (uid, query_date)))
        return DailySummary(date="2024-06-04", relative_uid=uid)

    async def get_latest_daily_summary(self, uid: int) -> DailySummary:
        self.calls.append(("latest_summary", (uid,)))
        return DailySummary(date="2024-06-05", relative_uid=uid)

    async def get_shared_data_types(self, uid: int) -> list[str]:
        self.calls.append(("shared", (uid,)))
        return ["steps", "heart_rate"]


@pytest.fixture(autouse=True)
def _patch_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_server, "MiHealthClient", _FakeClient)


# region 工具注册
def test_tools_are_registered() -> None:
    names = {name for name in dir(mcp_server) if not name.startswith("_")}
    for expected in (
        "list_relatives",
        "get_latest_data",
        "get_history",
        "get_daily_summary",
        "get_shared_data_types",
    ):
        assert expected in names


def test_mcp_server_has_name() -> None:
    assert mcp_server.mcp.name == "mi-fitness"


# endregion


# region 工具调用
@pytest.mark.asyncio
async def test_list_relatives_tool() -> None:
    result = await mcp_server.list_relatives()

    assert result[0]["relative_uid"] == 1
    assert result[0]["relative_note"] == "妈妈"


@pytest.mark.asyncio
async def test_get_latest_data_with_uid() -> None:
    result = await mcp_server.get_latest_data(relative_uid=1)

    assert result["steps"]["steps"] == 7


@pytest.mark.asyncio
async def test_get_latest_data_resolves_relative_name() -> None:
    result = await mcp_server.get_latest_data(relative="妈")

    assert result["steps"]["steps"] == 7


@pytest.mark.asyncio
async def test_get_latest_data_requires_target() -> None:
    with pytest.raises(ToolError, match="relative_uid 或 relative"):
        await mcp_server.get_latest_data()


@pytest.mark.asyncio
async def test_get_history_tool_passes_date_and_days() -> None:
    result = await mcp_server.get_history(
        key="steps",
        relative_uid=1,
        query_date="2024-06-04",
        days=7,
    )

    assert result[0]["steps"] == 7


@pytest.mark.asyncio
async def test_get_history_rejects_unknown_key() -> None:
    with pytest.raises(ToolError, match="不支持的 key"):
        await mcp_server.get_history(key="goal", relative_uid=1)


@pytest.mark.asyncio
async def test_get_history_rejects_bad_date() -> None:
    with pytest.raises(ValueError, match="Invalid isoformat"):
        await mcp_server.get_history(key="steps", relative_uid=1, query_date="bad")


@pytest.mark.asyncio
async def test_get_daily_summary_latest() -> None:
    result = await mcp_server.get_daily_summary(relative_uid=1, latest=True)

    assert result["date"] == "2024-06-05"


@pytest.mark.asyncio
async def test_get_daily_summary_by_date() -> None:
    result = await mcp_server.get_daily_summary(relative_uid=1, query_date="2024-06-04")

    assert result["date"] == "2024-06-04"


@pytest.mark.asyncio
async def test_get_shared_data_types_tool() -> None:
    result = await mcp_server.get_shared_data_types(relative_uid=1)

    assert result == ["steps", "heart_rate"]


# endregion


# region 错误转换
@pytest.mark.asyncio
async def test_sdk_error_becomes_tool_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FailingClient(_FakeClient):
        @classmethod
        def from_token(cls, path: Path | str) -> Any:
            raise TokenExpiredError("token 已过期")

    monkeypatch.setattr(mcp_server, "MiHealthClient", _FailingClient)

    with pytest.raises(ToolError, match="TokenExpiredError"):
        await mcp_server.list_relatives()


# endregion

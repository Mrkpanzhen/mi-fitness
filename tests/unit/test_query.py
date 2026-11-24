"""测试查询层 (query.py)：序列化、token 路径解析与查询分发。"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from mi_fitness.models import (
    DailySummary,
    FamilyMember,
    HeartRateData,
    LatestDataSnapshot,
    LatestHeartRate,
    StepData,
)
from mi_fitness.query import (
    DEFAULT_TOKEN_FILE,
    HISTORY_KEYS,
    TOKEN_ENV_VAR,
    family_member_to_dict,
    get_history,
    get_latest,
    get_summary,
    list_relatives,
    resolve_relative_uid,
    resolve_token_path,
    snapshot_to_dict,
    summary_to_dict,
    to_jsonable,
)


# region token 路径解析
def test_resolve_token_path_explicit(tmp_path: Path) -> None:
    target = tmp_path / "custom.json"
    assert resolve_token_path(target) == target


def test_resolve_token_path_uses_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TOKEN_ENV_VAR, "/tmp/from-env.json")
    assert resolve_token_path() == Path("/tmp/from-env.json")


def test_resolve_token_path_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(TOKEN_ENV_VAR, raising=False)
    assert resolve_token_path() == DEFAULT_TOKEN_FILE


def test_explicit_path_wins_over_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TOKEN_ENV_VAR, "/tmp/from-env.json")
    assert resolve_token_path("explicit.json") == Path("explicit.json")


# endregion


# region 序列化
def test_to_jsonable_handles_nested_models() -> None:
    payload = {"items": [StepData(steps=10)], "count": 1, "none": None}
    result = to_jsonable(payload)

    assert result["items"][0]["steps"] == 10
    assert result["count"] == 1
    assert result["none"] is None


def test_to_jsonable_output_is_serializable() -> None:
    snapshot = LatestDataSnapshot(
        updated_time=1717488000,
        heart_rate=LatestHeartRate(bpm=80, time=1717488000),
    )
    result = to_jsonable(snapshot)

    assert json.loads(json.dumps(result, ensure_ascii=False))["heart_rate"]["bpm"] == 80


def test_family_member_to_dict_has_stable_fields() -> None:
    member = FamilyMember(
        relative_uid=123,
        relative_note="妈妈",
        latest_data_time=1717488000,
        source_tag=1,
    )
    assert family_member_to_dict(member) == {
        "relative_uid": 123,
        "relative_note": "妈妈",
        "latest_data_time": 1717488000,
        "source_tag": 1,
    }


def test_snapshot_to_dict_excludes_none() -> None:
    snapshot = LatestDataSnapshot(steps=StepData(steps=100))
    result = snapshot_to_dict(snapshot)

    assert result["steps"]["steps"] == 100
    assert "sleep" not in result


def test_summary_to_dict_serializes_date_and_metrics() -> None:
    summary = DailySummary(
        date="2024-06-04",
        relative_uid=123,
        heart_rate=HeartRateData(avg_hr=70),
    )
    result = summary_to_dict(summary)

    assert result["date"] == "2024-06-04"
    assert result["heart_rate"]["avg_hr"] == 70
    assert "sleep" not in result


# endregion


# region 查询
@pytest.fixture
def client() -> Any:
    mock = AsyncMock()
    mock.get_relatives = AsyncMock(
        return_value=[
            FamilyMember(relative_uid=1, relative_note="妈妈", latest_data_time=1717488000),
            FamilyMember(relative_uid=2, relative_note="爸爸"),
        ]
    )
    mock.get_latest_data = AsyncMock(return_value=LatestDataSnapshot(steps=StepData(steps=5)))
    mock.get_steps = AsyncMock(return_value=[StepData(steps=5)])
    return mock


async def test_list_relatives_returns_dicts(client: Any) -> None:
    result = await list_relatives(client)

    assert [row["relative_uid"] for row in result] == [1, 2]


async def test_get_latest_returns_snapshot_dict(client: Any) -> None:
    result = await get_latest(client, 1)

    assert result["steps"]["steps"] == 5
    client.get_latest_data.assert_awaited_once_with(1)


async def test_get_history_dispatches_to_client_method(client: Any) -> None:
    result = await get_history(client, 1, "steps", query_date=date(2024, 6, 4), days=7)

    assert result[0]["steps"] == 5
    client.get_steps.assert_awaited_once_with(1, date(2024, 6, 4), days=7)


async def test_get_history_rejects_unknown_key(client: Any) -> None:
    with pytest.raises(ValueError, match="不支持的历史数据类型"):
        await get_history(client, 1, "goal")


def test_history_keys_exclude_goal() -> None:
    assert "goal" not in HISTORY_KEYS
    assert "heart_rate" in HISTORY_KEYS


async def test_get_summary_uses_latest(client: Any) -> None:
    client.get_latest_daily_summary = AsyncMock(
        return_value=DailySummary(date="2024-06-04", relative_uid=1)
    )

    result = await get_summary(client, 1, latest=True)

    assert result["date"] == "2024-06-04"
    client.get_latest_daily_summary.assert_awaited_once_with(1)


async def test_get_summary_uses_specific_date(client: Any) -> None:
    client.get_daily_summary = AsyncMock(
        return_value=DailySummary(date="2024-06-01", relative_uid=1)
    )

    result = await get_summary(client, 1, query_date=date(2024, 6, 1))

    assert result["date"] == "2024-06-01"
    client.get_daily_summary.assert_awaited_once_with(1, date(2024, 6, 1))


# endregion


# region UID 解析
def test_resolve_relative_uid_by_uid() -> None:
    members = [{"relative_uid": 1, "relative_note": "妈妈"}]
    assert resolve_relative_uid(members, "1") == 1


def test_resolve_relative_uid_by_note() -> None:
    members = [
        {"relative_uid": 1, "relative_note": "妈妈"},
        {"relative_uid": 2, "relative_note": "爸爸"},
    ]
    assert resolve_relative_uid(members, "爸") == 2


def test_resolve_relative_uid_missing_raises() -> None:
    with pytest.raises(LookupError, match="未找到亲友"):
        resolve_relative_uid([{"relative_uid": 1, "relative_note": "妈妈"}], "奶奶")


def test_resolve_relative_uid_ambiguous_raises() -> None:
    members = [
        {"relative_uid": 1, "relative_note": "妈妈"},
        {"relative_uid": 2, "relative_note": "妈妈2"},
    ]
    with pytest.raises(LookupError, match="匹配不唯一"):
        resolve_relative_uid(members, "妈妈")


# endregion

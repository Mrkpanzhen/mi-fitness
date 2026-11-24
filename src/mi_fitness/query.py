"""共享查询逻辑与序列化，供 CLI 与 MCP server 复用。"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from mi_fitness.client.api import MiHealthClient
from mi_fitness.const import DATA_KEYS
from mi_fitness.models import DailySummary, FamilyMember, LatestDataSnapshot

#: 支持历史查询的数据类型（``goal`` 只有最新值，没有历史序列）。
HISTORY_KEYS: tuple[str, ...] = tuple(key for key in DATA_KEYS if key != "goal")

#: 历史数据类型 -> MiHealthClient 方法名。
_HISTORY_METHODS: dict[str, str] = {
    "heart_rate": "get_heart_rate",
    "sleep": "get_sleep",
    "steps": "get_steps",
    "blood_pressure": "get_blood_pressure_history",
    "calories": "get_calories_history",
    "valid_stand": "get_valid_stand_history",
    "intensity": "get_intensity_history",
    "weight": "get_weight_history",
    "spo2": "get_spo2_history",
}

DEFAULT_TOKEN_FILE = Path("token.json")
TOKEN_ENV_VAR = "MI_FITNESS_TOKEN"


def resolve_token_path(explicit: Path | str | None = None) -> Path:
    """解析 token 路径：显式参数 > 环境变量 > 默认 ``token.json``。"""
    if explicit is not None:
        return Path(explicit)
    env_value = os.environ.get(TOKEN_ENV_VAR, "").strip()
    if env_value:
        return Path(env_value)
    return DEFAULT_TOKEN_FILE


def to_jsonable(value: Any) -> Any:
    """把 Pydantic 模型/容器转换为可 JSON 序列化的结构。"""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", exclude_none=True)
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    return value


def family_member_to_dict(member: FamilyMember) -> dict[str, Any]:
    """亲友信息转为稳定字段名，便于脚本消费。"""
    return {
        "relative_uid": member.relative_uid,
        "relative_note": member.relative_note,
        "latest_data_time": member.latest_data_time,
        "source_tag": member.source_tag,
    }


def snapshot_to_dict(snapshot: LatestDataSnapshot) -> dict[str, Any]:
    """最新快照转为 {key: value} 结构，保留未知数据类型。"""
    return to_jsonable(snapshot)


def summary_to_dict(summary: DailySummary) -> dict[str, Any]:
    """每日摘要转为可序列化结构。"""
    return to_jsonable(summary)


async def list_relatives(client: MiHealthClient) -> list[dict[str, Any]]:
    """查询亲友列表。"""
    members = await client.get_relatives()
    return [family_member_to_dict(m) for m in members]


async def get_latest(client: MiHealthClient, relative_uid: int) -> dict[str, Any]:
    """查询亲友的最新数据快照。"""
    return snapshot_to_dict(await client.get_latest_data(relative_uid))


async def get_history(
    client: MiHealthClient,
    relative_uid: int,
    key: str,
    *,
    query_date: date | None = None,
    days: int = 1,
) -> list[dict[str, Any]]:
    """查询指定数据类型的按日历史。

    Args:
        client: 健康数据客户端。
        relative_uid: 亲友 UID。
        key: 数据类型，取值见 :data:`HISTORY_KEYS`。
        query_date: 窗口结束日，默认今天（中国标准时间）。
        days: 窗口天数（1..365）。

    Raises:
        ValueError: ``key`` 不支持或 ``days`` 越界。
    """
    method_name = _HISTORY_METHODS.get(key)
    if method_name is None:
        supported = ", ".join(HISTORY_KEYS)
        raise ValueError(f"不支持的历史数据类型: {key}（可选: {supported}）")

    method = getattr(client, method_name)
    items = await method(relative_uid, query_date, days=days)
    return [to_jsonable(item) for item in items]


async def get_summary(
    client: MiHealthClient,
    relative_uid: int,
    *,
    query_date: date | None = None,
    latest: bool = False,
) -> dict[str, Any]:
    """查询每日综合摘要。

    Args:
        client: 健康数据客户端。
        relative_uid: 亲友 UID。
        query_date: 指定日期；与 ``latest`` 互斥（``latest`` 优先）。
        latest: 为 True 时使用最近一次同步日。
    """
    if latest:
        summary = await client.get_latest_daily_summary(relative_uid)
    else:
        summary = await client.get_daily_summary(relative_uid, query_date)
    return summary_to_dict(summary)


def resolve_relative_uid(members: list[dict[str, Any]], keyword: str | int) -> int:
    """在亲友列表中按 UID 或备注名找到唯一 UID。

    Raises:
        LookupError: 未找到或匹配到多个亲友。
    """
    text = str(keyword).strip()
    matches = [
        m
        for m in members
        if text == str(m["relative_uid"]) or text.lower() in str(m["relative_note"]).lower()
    ]
    if not matches:
        raise LookupError(f"未找到亲友: {keyword}")
    if len(matches) > 1:
        names = ", ".join(f"{m['relative_note']}({m['relative_uid']})" for m in matches)
        raise LookupError(f"亲友匹配不唯一: {keyword} -> {names}")
    return int(matches[0]["relative_uid"])

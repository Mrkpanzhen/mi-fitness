"""测试常量 (const.py)。"""

from __future__ import annotations

from datetime import timedelta

from mi_fitness.const import (
    ALL_SHARED_DATA_TYPES,
    CN_TZ,
    DATA_KEYS,
    HEALTH_API_BASE,
    RELATIVES_AGGREGATED_DATA_PATH,
    RELATIVES_DELETE_PATH,
    RELATIVES_FITNESS_DATA_PATH,
    RELATIVES_GET_APPLIED_SHARED_TYPES_PATH,
    RELATIVES_GET_FAMILY_MEMBER_PATH,
    RELATIVES_GET_INVITE_ID_PATH,
    RELATIVES_GET_SHARED_TYPES_PATH,
    RELATIVES_GET_TOPIC_SUBS_PATH,
    RELATIVES_LATEST_DATA_PATH,
    RELATIVES_LIST_PATH,
    RELATIVES_SEND_INVITE_PATH,
    RELATIVES_VERIFY_USER_PATH,
    VERIFY_TYPE_XIAOMI_ID,
)


class TestAPIEndpoints:
    """API 端点常量测试。"""

    def test_base_url_is_https(self) -> None:
        assert HEALTH_API_BASE.startswith("https://")

    def test_all_paths_start_with_slash(self) -> None:
        paths = [
            RELATIVES_LIST_PATH,
            RELATIVES_LATEST_DATA_PATH,
            RELATIVES_AGGREGATED_DATA_PATH,
            RELATIVES_FITNESS_DATA_PATH,
            RELATIVES_VERIFY_USER_PATH,
            RELATIVES_SEND_INVITE_PATH,
            RELATIVES_DELETE_PATH,
            RELATIVES_GET_SHARED_TYPES_PATH,
            RELATIVES_GET_APPLIED_SHARED_TYPES_PATH,
            RELATIVES_GET_FAMILY_MEMBER_PATH,
            RELATIVES_GET_INVITE_ID_PATH,
            RELATIVES_GET_TOPIC_SUBS_PATH,
        ]
        for path in paths:
            assert path.startswith("/app/v1/relatives/"), f"{path} 不以 /app/v1/relatives/ 开头"


class TestSharedDataTypes:
    """共享数据类型常量测试。"""

    def test_has_10_types(self) -> None:
        assert len(ALL_SHARED_DATA_TYPES) == 10

    def test_contains_core_types(self) -> None:
        for key in ["heart_rate", "sleep", "steps", "weight", "spo2"]:
            assert key in ALL_SHARED_DATA_TYPES, f"缺少 {key}"

    def test_no_duplicates(self) -> None:
        assert len(ALL_SHARED_DATA_TYPES) == len(set(ALL_SHARED_DATA_TYPES))

    def test_shared_types_match_data_keys(self) -> None:
        assert ALL_SHARED_DATA_TYPES == DATA_KEYS


class TestTimezone:
    """时区常量测试。"""

    def test_china_timezone_is_utc_plus_8(self) -> None:
        assert CN_TZ.utcoffset(None) == timedelta(hours=8)


class TestVerifyTypes:
    """验证类型常量测试。"""

    def test_values(self) -> None:
        assert VERIFY_TYPE_XIAOMI_ID == 1

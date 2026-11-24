"""测试 CLI 子命令的参数解析、输出格式与查询分发。"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar, Self
from unittest.mock import AsyncMock

import pytest

import mi_fitness.cli as cli


# region 参数解析
def test_parser_defaults_to_login() -> None:
    args = cli._build_parser().parse_args([])
    assert args.command is None


@pytest.mark.parametrize("command", ["relatives", "latest", "history", "summary", "qr-login"])
def test_parser_accepts_known_commands(command: str) -> None:
    argv = [command]
    if command == "history":
        argv += ["--key", "steps"]
    args = cli._build_parser().parse_args(argv)
    assert args.command == command


def test_parser_rejects_unknown_command() -> None:
    with pytest.raises(SystemExit):
        cli._build_parser().parse_args(["nope"])


def test_parser_rejects_unknown_history_key() -> None:
    with pytest.raises(SystemExit):
        cli._build_parser().parse_args(["history", "--key", "goal"])


def test_parser_parses_date_and_days() -> None:
    args = cli._build_parser().parse_args(
        ["history", "--key", "steps", "--date", "2024-06-04", "--days", "7", "--uid", "123"]
    )
    assert args.date == date(2024, 6, 4)
    assert args.days == 7
    assert args.uid == 123


def test_parser_rejects_bad_date_format() -> None:
    with pytest.raises(SystemExit):
        cli._build_parser().parse_args(["history", "--key", "steps", "--date", "06/04/2024"])


def test_format_defaults_to_json() -> None:
    args = cli._build_parser().parse_args(["relatives"])
    assert args.format == "json"


# endregion


# region 输出格式
def test_emit_json(capsys: pytest.CaptureFixture[str]) -> None:
    cli._emit([{"relative_uid": 1, "relative_note": "妈妈"}], "json")

    payload = json.loads(capsys.readouterr().out)
    assert payload == [{"relative_uid": 1, "relative_note": "妈妈"}]


def test_emit_table(capsys: pytest.CaptureFixture[str]) -> None:
    cli._emit([{"uid": 1, "note": "妈妈"}, {"uid": 2, "note": "爸爸"}], "table")

    out = capsys.readouterr().out
    assert "uid" in out
    assert "note" in out
    assert "妈妈" in out
    assert "爸爸" in out


def test_emit_table_empty(capsys: pytest.CaptureFixture[str]) -> None:
    cli._emit([], "table")

    assert "(无数据)" in capsys.readouterr().out


def test_emit_table_nested_values(capsys: pytest.CaptureFixture[str]) -> None:
    cli._emit([{"steps": {"count": 10}}], "table")

    assert '{"count": 10}' in capsys.readouterr().out


# endregion


# region 查询分发
class _FakeClient:
    instances: ClassVar[list["_FakeClient"]] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.relatives = [
            {"relative_uid": 1, "relative_note": "妈妈", "latest_data_time": 0, "source_tag": 0}
        ]
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        _FakeClient.instances.append(self)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    @classmethod
    def from_token(cls, path: Path | str) -> Self:
        return cls()

    async def get_relatives(self) -> list[Any]:
        from mi_fitness.models import FamilyMember

        return [FamilyMember(**row) for row in self.relatives]

    async def get_latest_data(self, uid: int) -> Any:
        from mi_fitness.models import LatestDataSnapshot, StepData

        self.calls.append(("latest", (uid,), {}))
        return LatestDataSnapshot(steps=StepData(steps=9))

    async def get_steps(self, uid: int, query_date: date | None, *, days: int = 1) -> list[Any]:
        from mi_fitness.models import StepData

        self.calls.append(("steps", (uid, query_date), {"days": days}))
        return [StepData(steps=9)]

    async def get_daily_summary(self, uid: int, query_date: date | None = None) -> Any:
        from mi_fitness.models import DailySummary

        self.calls.append(("summary", (uid, query_date), {}))
        return DailySummary(date="2024-06-04", relative_uid=uid)

    async def get_latest_daily_summary(self, uid: int) -> Any:
        from mi_fitness.models import DailySummary

        self.calls.append(("latest_summary", (uid,), {}))
        return DailySummary(date="2024-06-05", relative_uid=uid)


@pytest.fixture(autouse=True)
def _patch_client(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeClient.instances.clear()
    monkeypatch.setattr(cli, "MiHealthClient", _FakeClient)


def _args(**overrides: Any) -> Any:
    defaults: dict[str, Any] = {
        "command": "relatives",
        "token": None,
        "format": "json",
        "uid": None,
        "relative": None,
        "key": "steps",
        "date": None,
        "days": 1,
        "latest": False,
    }
    defaults.update(overrides)
    return type("Args", (), defaults)()


@pytest.mark.asyncio
async def test_run_query_relatives() -> None:
    result = await cli._run_query(_args(command="relatives"))
    assert result[0]["relative_uid"] == 1


@pytest.mark.asyncio
async def test_run_query_latest_by_uid() -> None:
    result = await cli._run_query(_args(command="latest", uid=1))
    assert result["steps"]["steps"] == 9


@pytest.mark.asyncio
async def test_run_query_resolves_relative_by_name() -> None:
    result = await cli._run_query(_args(command="latest", relative="妈"))
    assert result["steps"]["steps"] == 9
    assert _FakeClient.instances[-1].calls == [("latest", (1,), {})]


@pytest.mark.asyncio
async def test_run_query_history_passes_window() -> None:
    result = await cli._run_query(_args(command="history", uid=1, date=date(2024, 6, 4), days=7))
    assert result[0]["steps"] == 9
    assert _FakeClient.instances[-1].calls == [("steps", (1, date(2024, 6, 4)), {"days": 7})]


@pytest.mark.asyncio
async def test_run_query_summary_latest() -> None:
    result = await cli._run_query(_args(command="summary", uid=1, latest=True))
    assert result["date"] == "2024-06-05"


@pytest.mark.asyncio
async def test_run_query_summary_by_date() -> None:
    result = await cli._run_query(_args(command="summary", uid=1, date=date(2024, 6, 4)))
    assert result["date"] == "2024-06-04"


@pytest.mark.asyncio
async def test_run_query_requires_relative_target() -> None:
    with pytest.raises(SystemExit):
        await cli._run_query(_args(command="latest"))


def test_main_prints_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "_run_query", AsyncMock(return_value=[{"uid": 1}]))
    cli.main(["relatives"])

    assert json.loads(capsys.readouterr().out) == [{"uid": 1}]


def test_main_converts_sdk_error_to_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    from mi_fitness.exceptions import AuthError

    monkeypatch.setattr(cli, "_run_query", AsyncMock(side_effect=AuthError("token 过期")))

    with pytest.raises(SystemExit, match="token 过期"):
        cli.main(["relatives"])


def test_main_table_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "_run_query", AsyncMock(return_value=[{"uid": 1, "note": "妈妈"}]))
    cli.main(["relatives", "--format", "table"])

    assert "妈妈" in capsys.readouterr().out


# endregion


# region 登录（保留原有行为）
def test_main_runs_qr_login_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    async def fake_qr_login(token_path: Path | str | None = None) -> None:
        nonlocal called
        called = True
        assert token_path is None

    monkeypatch.setattr(cli, "_qr_login", fake_qr_login)
    cli.main([])
    assert called


def test_main_accepts_custom_token_path(monkeypatch: pytest.MonkeyPatch) -> None:
    received: list[Path | str | None] = []

    async def fake_qr_login(token_path: Path | str | None = None) -> None:
        received.append(token_path)

    monkeypatch.setattr(cli, "_qr_login", fake_qr_login)
    cli.main(["qr-login", "--token", "custom.json"])

    assert received == [Path("custom.json")]


class _FakeAuth:
    instances: ClassVar[list["_FakeAuth"]] = []

    def __init__(self, *args: object) -> None:
        self.token = SimpleNamespace(user_id="42")
        self.saved_path: Path | None = None
        self.login_calls: list[str] = []
        _FakeAuth.instances.append(self)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def login_qr(self, qr_callback: Any = None) -> None:
        self.login_calls.append("qr")
        if qr_callback is not None:
            await qr_callback("https://example.com/qr.png", "https://example.com/login")

    def save_token(self, path: Path | str) -> None:
        self.saved_path = Path(path)


@pytest.mark.asyncio
async def test_qr_login_saves_token(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _FakeAuth.instances.clear()
    monkeypatch.setattr(cli, "XiaomiAuth", _FakeAuth)
    rendered: list[str] = []
    monkeypatch.setattr(cli, "_print_qr_to_terminal", rendered.append)

    await cli._qr_login("custom-token.json")

    auth = _FakeAuth.instances[-1]
    assert auth.login_calls == ["qr"]
    assert auth.saved_path == Path("custom-token.json")
    out = capsys.readouterr().out
    assert rendered == ["https://example.com/login"]
    assert "user_id = 42" in out


@pytest.mark.asyncio
async def test_qr_login_prints_error_and_reraises(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from mi_fitness.exceptions import AuthError

    class _FailingAuth(_FakeAuth):
        async def login_qr(self, qr_callback: Any = None) -> None:
            raise AuthError("二维码过期")

    monkeypatch.setattr(cli, "XiaomiAuth", _FailingAuth)

    with pytest.raises(AuthError, match="二维码过期"):
        await cli._qr_login()

    assert "扫码登录失败" in capsys.readouterr().out


def test_print_qr_to_terminal_renders(capsys: pytest.CaptureFixture[str]) -> None:
    cli._print_qr_to_terminal("https://example.com/login")

    out = capsys.readouterr().out
    assert "\u2588" in out or "\u2580" in out or "\u2584" in out
    assert len(out.splitlines()) > 5


# endregion

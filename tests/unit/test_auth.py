"""测试认证模块的内部编排逻辑。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from mi_fitness.auth import XiaomiAuth
from mi_fitness.auth import manager as auth_manager
from mi_fitness.auth import passtoken as passtoken_module
from mi_fitness.auth import password as password_module
from mi_fitness.auth import qr as qr_module
from mi_fitness.exceptions import (
    AuthError,
    CaptchaRequiredError,
    DeviceUntrustedError,
    TokenExpiredError,
)
from mi_fitness.models import AuthToken

pytestmark = pytest.mark.asyncio


class _DummyResponse:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self) -> None:
        """测试响应默认视为成功。"""


def _http_response(text: str, status_code: int = 200) -> httpx.Response:
    request = httpx.Request("GET", "https://example.com/test")
    return httpx.Response(status_code=status_code, text=text, request=request)


def _make_auth() -> XiaomiAuth:
    auth = XiaomiAuth("13800138000", "secret")
    auth._http = MagicMock()
    auth._http.cookies = MagicMock()
    return auth


async def test_send_verification_code_retries_captcha_once(monkeypatch: pytest.MonkeyPatch) -> None:
    auth = _make_auth()

    ensure_ready = AsyncMock()
    send_ticket = AsyncMock(
        side_effect=[
            CaptchaRequiredError("需要图形验证码", captcha_url="https://example.com/captcha.png"),
            None,
        ]
    )
    get_phone_info = AsyncMock(return_value=("191******54", "ticket-token"))
    fetch_captcha = AsyncMock(return_value=b"captcha-image")
    captcha_handler = AsyncMock(return_value="ABCD")

    monkeypatch.setattr(auth_manager._pwd, "ensure_ticket_login_ready", ensure_ready)
    monkeypatch.setattr(auth_manager._pwd, "send_ticket", send_ticket)
    monkeypatch.setattr(auth_manager._pwd, "get_phone_info", get_phone_info)
    monkeypatch.setattr(auth_manager._pwd, "fetch_captcha_image", fetch_captcha)

    phone = await auth.send_verification_code(captcha_handler=captcha_handler)

    assert phone == "191******54"
    assert auth._ticket_token == "ticket-token"
    ensure_ready.assert_awaited_once_with(auth._http)
    assert [call.kwargs["captcha_code"] for call in send_ticket.await_args_list] == ["", "ABCD"]
    get_phone_info.assert_awaited_once_with(auth._http, auth.username, captcha_code="")
    fetch_captcha.assert_awaited_once_with(auth._http, "https://example.com/captcha.png")
    captcha_handler.assert_awaited_once_with(b"captcha-image")


async def test_send_verification_code_stops_after_max_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth = _make_auth()

    captcha_error = CaptchaRequiredError(
        "需要图形验证码",
        captcha_url="https://example.com/captcha.png",
    )
    send_ticket = AsyncMock(side_effect=[captcha_error] * auth_manager._MAX_CAPTCHA_RETRIES)
    get_phone_info = AsyncMock()
    fetch_captcha = AsyncMock(return_value=b"captcha-image")
    captcha_handler = AsyncMock(return_value="ABCD")

    monkeypatch.setattr(auth_manager._pwd, "ensure_ticket_login_ready", AsyncMock())
    monkeypatch.setattr(auth_manager._pwd, "send_ticket", send_ticket)
    monkeypatch.setattr(auth_manager._pwd, "get_phone_info", get_phone_info)
    monkeypatch.setattr(auth_manager._pwd, "fetch_captcha_image", fetch_captcha)

    with pytest.raises(AuthError, match="已连续重试 3 次"):
        await auth.send_verification_code(captcha_handler=captcha_handler)

    assert send_ticket.await_count == auth_manager._MAX_CAPTCHA_RETRIES
    assert fetch_captcha.await_count == auth_manager._MAX_CAPTCHA_RETRIES
    assert captcha_handler.await_count == auth_manager._MAX_CAPTCHA_RETRIES
    get_phone_info.assert_not_awaited()


async def test_login_passtoken_uses_shared_service_token_extractor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http = MagicMock()
    http.cookies = MagicMock()
    http.get = AsyncMock(
        return_value=_DummyResponse(
            '&&&START&&&{"ssecurity":"sec","location":"https://example.com/cb?foo=1","nonce":"nonce","cUserId":"cid"}'
        )
    )
    extract_service_token = AsyncMock(return_value="service-token")
    monkeypatch.setattr(passtoken_module, "extract_service_token", extract_service_token)

    token = AuthToken()
    await passtoken_module.login_passtoken(
        http,
        token,
        pass_token="pass-token",
        user_id="user-id",
        device_id="an_device",
    )

    assert token.ssecurity == "sec"
    assert token.c_user_id == "cid"
    assert token.service_token == "service-token"
    extract_service_token.assert_awaited_once()
    await_args = extract_service_token.await_args
    assert await_args is not None
    redirect_url = await_args.args[1]
    assert redirect_url.startswith("https://example.com/cb?foo=1&clientSign=")


async def test_refresh_reuses_existing_token_and_persists(monkeypatch: pytest.MonkeyPatch) -> None:
    auth = _make_auth()
    auth.token = AuthToken(
        user_id="user-id",
        pass_token="pass-token",
        device_id="an_device",
        service_token="old-token",
        ssecurity="old-sec",
    )
    auth._token_path = Path("token.json")
    save_token = MagicMock()
    auth.save_token = save_token  # type: ignore[method-assign]

    async def fake_login_passtoken(*args, **kwargs) -> None:
        auth.token.service_token = "new-token"
        auth.token.ssecurity = "new-sec"

    login_passtoken = AsyncMock(side_effect=fake_login_passtoken)
    monkeypatch.setattr(auth_manager, "_pt", MagicMock(login_passtoken=login_passtoken))
    monkeypatch.setattr(auth_manager, "_sts", MagicMock(sts_exchange=AsyncMock()))

    token = await auth.refresh()

    assert token.service_token == "new-token"
    assert token.ssecurity == "new-sec"
    login_passtoken.assert_awaited_once_with(
        auth._http,
        auth.token,
        pass_token="pass-token",
        user_id="user-id",
        device_id="an_device",
    )
    save_token.assert_called_once_with(Path("token.json"))


async def test_refresh_requires_pass_token() -> None:
    auth = _make_auth()
    auth.token = AuthToken(user_id="user-id", pass_token="")

    with pytest.raises(TokenExpiredError, match="无法自动刷新"):
        await auth.refresh()


async def test_password_login_wrong_password_raises_auth_error() -> None:
    http = MagicMock()
    http.post = AsyncMock(
        return_value=_http_response('&&&START&&&{"code":70002,"desc":"invalid credential"}')
    )

    with pytest.raises(AuthError, match="登录失败"):
        await password_module._raw_submit_login(http, "13800138000", "bad", "sign", "callback")


async def test_submit_login_requires_device_verification() -> None:
    http = MagicMock()
    token = AuthToken()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            password_module,
            "_raw_submit_login",
            AsyncMock(return_value={"code": 70016}),
        )

        with pytest.raises(DeviceUntrustedError, match="二次验证"):
            await password_module.submit_login(
                http, token, "13800138000", "secret", "sign", "callback"
            )


async def test_submit_login_requires_trusted_device_when_security_status_non_zero() -> None:
    http = MagicMock()
    token = AuthToken()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            password_module,
            "_raw_submit_login",
            AsyncMock(return_value={"code": 0, "securityStatus": 8}),
        )

        with pytest.raises(DeviceUntrustedError, match="设备未受信任"):
            await password_module.submit_login(
                http, token, "13800138000", "secret", "sign", "callback"
            )


async def test_qr_login_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    http = MagicMock()
    http.get = AsyncMock(
        return_value=_http_response(
            '&&&START&&&{"qr":"https://example.com/qr.png","lp":"https://example.com/poll","timeout":0}'
        )
    )
    http.request_without_retry = AsyncMock(return_value=_http_response("", status_code=500))
    monkeypatch.setattr(qr_module, "async_sleep", AsyncMock())
    time_values = iter([0.0, 0.0, 1.0])
    monkeypatch.setattr(qr_module.time, "time", lambda: next(time_values))

    with pytest.raises(AuthError, match="二维码扫码超时"):
        await qr_module.login_qr(http, AuthToken(), max_wait=0)


async def test_qr_login_extracts_credentials_after_success() -> None:
    http = MagicMock()
    http.get = AsyncMock(
        return_value=_http_response(
            '&&&START&&&{"qr":"https://example.com/qr.png","lp":"https://example.com/poll","timeout":60}'
        )
    )
    http.request_without_retry = AsyncMock(
        return_value=_http_response(
            '&&&START&&&{"ssecurity":"sec","userId":"42","passToken":"pass","cUserId":"cid"}'
        )
    )
    token = AuthToken()

    await qr_module.login_qr(http, token)

    assert token.ssecurity == "sec"
    assert token.user_id == "42"
    assert token.pass_token == "pass"
    assert token.c_user_id == "cid"


async def test_qr_login_raises_auth_error_for_business_failure() -> None:
    http = MagicMock()
    http.get = AsyncMock(
        return_value=_http_response(
            '&&&START&&&{"qr":"https://example.com/qr.png","lp":"https://example.com/poll","timeout":60}'
        )
    )
    http.request_without_retry = AsyncMock(
        return_value=_http_response('&&&START&&&{"code":70001,"desc":"二维码已过期"}')
    )

    with pytest.raises(AuthError, match="二维码登录失败"):
        await qr_module.login_qr(http, AuthToken())


async def test_qr_login_raises_auth_error_when_ssecurity_missing() -> None:
    http = MagicMock()
    http.get = AsyncMock(
        return_value=_http_response(
            '&&&START&&&{"qr":"https://example.com/qr.png","lp":"https://example.com/poll","timeout":60}'
        )
    )
    http.request_without_retry = AsyncMock(
        return_value=_http_response('&&&START&&&{"userId":"42","desc":"登录未完成"}')
    )

    with pytest.raises(AuthError, match="登录凭证提取失败"):
        await qr_module.login_qr(http, AuthToken())


async def test_qr_login_invokes_callback() -> None:
    http = MagicMock()
    http.get = AsyncMock(
        return_value=_http_response(
            '&&&START&&&{"qr":"https://example.com/qr.png",'
            '"loginUrl":"https://example.com/login",'
            '"lp":"https://example.com/poll","timeout":60}'
        )
    )
    http.request_without_retry = AsyncMock(
        return_value=_http_response(
            '&&&START&&&{"ssecurity":"sec","userId":"42","passToken":"pass","cUserId":"cid"}'
        )
    )
    callback = AsyncMock()

    await qr_module.login_qr(http, AuthToken(), qr_callback=callback)

    callback.assert_awaited_once_with("https://example.com/qr.png", "https://example.com/login")


async def test_qr_login_retries_after_non_200_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http = MagicMock()
    http.get = AsyncMock(
        return_value=_http_response(
            '&&&START&&&{"qr":"https://example.com/qr.png","lp":"https://example.com/poll","timeout":60}'
        )
    )
    http.request_without_retry = AsyncMock(
        side_effect=[
            _http_response("", status_code=503),
            _http_response(
                '&&&START&&&{"ssecurity":"sec","userId":"42","passToken":"pass","cUserId":"cid"}'
            ),
        ]
    )
    monkeypatch.setattr(qr_module, "async_sleep", AsyncMock())
    token = AuthToken()

    await qr_module.login_qr(http, token)

    assert token.ssecurity == "sec"
    assert http.request_without_retry.await_count == 2


async def test_qr_login_retries_after_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http = MagicMock()
    http.get = AsyncMock(
        return_value=_http_response(
            '&&&START&&&{"qr":"https://example.com/qr.png","lp":"https://example.com/poll","timeout":60}'
        )
    )
    http.request_without_retry = AsyncMock(
        side_effect=[
            httpx.ReadTimeout("poll timeout"),
            _http_response(
                '&&&START&&&{"ssecurity":"sec","userId":"42","passToken":"pass","cUserId":"cid"}'
            ),
        ]
    )
    token = AuthToken()

    await qr_module.login_qr(http, token)

    assert token.ssecurity == "sec"


async def test_qr_login_retries_after_request_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http = MagicMock()
    http.get = AsyncMock(
        return_value=_http_response(
            '&&&START&&&{"qr":"https://example.com/qr.png","lp":"https://example.com/poll","timeout":60}'
        )
    )
    http.request_without_retry = AsyncMock(
        side_effect=[
            httpx.ConnectError("network down"),
            _http_response(
                '&&&START&&&{"ssecurity":"sec","userId":"42","passToken":"pass","cUserId":"cid"}'
            ),
        ]
    )
    monkeypatch.setattr(qr_module, "async_sleep", AsyncMock())
    token = AuthToken()

    await qr_module.login_qr(http, token)

    assert token.ssecurity == "sec"


async def test_login_password_success_clears_password(monkeypatch: pytest.MonkeyPatch) -> None:
    auth = _make_auth()
    get_login_page = AsyncMock(return_value=("sign", "callback"))
    submit_login = AsyncMock()
    sts_exchange = AsyncMock()
    monkeypatch.setattr(auth_manager._pwd, "get_login_page", get_login_page)
    monkeypatch.setattr(auth_manager._pwd, "submit_login", submit_login)
    monkeypatch.setattr(auth_manager._sts, "sts_exchange", sts_exchange)

    token = await auth.login()

    assert token is auth.token
    get_login_page.assert_awaited_once_with(auth._http)
    submit_login.assert_awaited_once()
    sts_exchange.assert_awaited_once_with(auth._http, auth.token)
    assert auth._password == ""


async def test_login_missing_credentials_raises() -> None:
    with pytest.raises(AuthError, match="用户名和密码不能为空"):
        await XiaomiAuth().login()


async def test_login_device_untrusted_uses_verification_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth = _make_auth()
    monkeypatch.setattr(auth_manager._pwd, "get_login_page", AsyncMock(return_value=("s", "c")))
    monkeypatch.setattr(
        auth_manager._pwd,
        "submit_login",
        AsyncMock(side_effect=DeviceUntrustedError("需要短信验证")),
    )
    auth.send_verification_code = AsyncMock(return_value="191******54")  # type: ignore[method-assign]
    auth.login_with_verification_code = AsyncMock()  # type: ignore[method-assign]
    handler = AsyncMock(return_value="123456")

    token = await auth.login(verification_code_handler=handler)

    assert token is auth.token
    handler.assert_awaited_once_with("191******54")
    auth.login_with_verification_code.assert_awaited_once_with("123456")


async def test_login_qr_success_calls_sts(monkeypatch: pytest.MonkeyPatch) -> None:
    auth = _make_auth()
    login_qr = AsyncMock()
    sts_exchange = AsyncMock()
    monkeypatch.setattr(auth_manager._qr, "login_qr", login_qr)
    monkeypatch.setattr(auth_manager._sts, "sts_exchange", sts_exchange)

    token = await auth.login_qr()

    assert token is auth.token
    login_qr.assert_awaited_once()
    sts_exchange.assert_awaited_once_with(auth._http, auth.token)


async def test_login_with_verification_code_requires_ticket_token() -> None:
    auth = _make_auth()

    with pytest.raises(AuthError, match="请先调用 send_verification_code"):
        await auth.login_with_verification_code("123456")


async def test_login_with_verification_code_success(monkeypatch: pytest.MonkeyPatch) -> None:
    auth = _make_auth()
    auth._ticket_token = "ticket-token"
    monkeypatch.setattr(auth_manager._pwd, "get_login_page", AsyncMock(return_value=("s", "c")))
    submit_ticket = AsyncMock()
    sts_exchange = AsyncMock()
    monkeypatch.setattr(auth_manager._pwd, "submit_ticket_auth", submit_ticket)
    monkeypatch.setattr(auth_manager._sts, "sts_exchange", sts_exchange)

    token = await auth.login_with_verification_code("123456")

    assert token is auth.token
    submit_ticket.assert_awaited_once()
    sts_exchange.assert_awaited_once_with(auth._http, auth.token)
    assert auth._ticket_token == ""
    assert auth._password == ""


async def test_save_and_load_token_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _make_auth()
    auth.token = AuthToken(
        user_id="42",
        c_user_id="cid",
        service_token="service",
        ssecurity="sec",
        pass_token="pass",
        device_id="an_device",
    )
    chmod = MagicMock()
    monkeypatch.setattr(auth_manager.os, "chmod", chmod)
    path = tmp_path / "token.json"

    auth.save_token(path)

    chmod.assert_called_once_with(path, 0o600)
    loaded = XiaomiAuth.from_token(path)
    assert loaded.token == auth.token
    assert loaded._token_path == path


async def test_save_token_ignores_chmod_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _make_auth()
    monkeypatch.setattr(auth_manager.os, "chmod", MagicMock(side_effect=OSError("denied")))
    path = tmp_path / "token.json"

    auth.save_token(path)

    assert path.exists()


async def test_load_token_missing_or_invalid_raises(tmp_path: Path) -> None:
    auth = XiaomiAuth()

    with pytest.raises(AuthError, match="Token 文件不存在"):
        auth.load_token(tmp_path / "missing.json")

    invalid = tmp_path / "invalid.json"
    invalid.write_text("{not-json", encoding="utf-8")
    with pytest.raises(AuthError, match="Token 文件解析失败"):
        auth.load_token(invalid)


async def test_authenticated_and_refreshable_properties() -> None:
    auth = XiaomiAuth()
    assert auth.is_authenticated is False
    assert auth.can_refresh is False

    auth.token = AuthToken(
        user_id="42",
        pass_token="pass",
        service_token="service",
        ssecurity="sec",
    )
    assert auth.is_authenticated is True
    assert auth.can_refresh is True


async def test_login_passtoken_requires_non_empty_inputs() -> None:
    http = MagicMock()
    http.cookies = MagicMock()
    token = AuthToken()

    with pytest.raises(AuthError, match="passToken 不能为空"):
        await passtoken_module.login_passtoken(http, token, pass_token="", user_id="uid")

    with pytest.raises(AuthError, match="userId 不能为空"):
        await passtoken_module.login_passtoken(http, token, pass_token="pt", user_id="")

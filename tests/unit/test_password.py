"""测试密码登录与短信验证码流程 (auth/password.py)。"""

from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from mi_fitness.auth import password as password_module
from mi_fitness.exceptions import AuthError, CaptchaRequiredError
from mi_fitness.models import AuthToken

pytestmark = pytest.mark.asyncio


def _response(
    text: str = "",
    *,
    status_code: int = 200,
    content: bytes = b"",
) -> httpx.Response:
    request = httpx.Request("GET", "https://example.com/test")
    body = content if content else text.encode("utf-8")
    return httpx.Response(status_code, content=body, request=request)


# region 登录页
async def test_get_login_page_parses_json() -> None:
    http = MagicMock()
    http.get = AsyncMock(
        return_value=_response('&&&START&&&{"_sign":"sign-value","callback":"callback-url"}')
    )

    sign, callback = await password_module.get_login_page(http)

    assert sign == "sign-value"
    assert callback == "callback-url"
    http.get.assert_awaited_once()


async def test_get_login_page_falls_back_to_regex() -> None:
    http = MagicMock()
    http.get = AsyncMock(
        return_value=_response('not-json "_sign":"fallback-sign" "callback":"fallback-callback"')
    )

    sign, callback = await password_module.get_login_page(http, login_sign="ticket")

    assert sign == "fallback-sign"
    assert callback == "fallback-callback"
    assert http.get.await_args.kwargs["params"]["_loginSign"] == "ticket"


# endregion


# region 密码提交
async def test_raw_submit_login_sends_uppercase_md5_hash() -> None:
    http = MagicMock()
    http.post = AsyncMock(return_value=_response('&&&START&&&{"code":0,"ssecurity":"sec"}'))

    data = await password_module._raw_submit_login(
        http, "13800138000", "secret", "sign", "callback"
    )

    assert data["ssecurity"] == "sec"
    form = http.post.await_args.kwargs["data"]
    assert form["hash"] == hashlib.md5(b"secret").hexdigest().upper()
    assert form["_sign"] == "sign"
    assert form["callback"] == "callback"
    assert form["user"] == "13800138000"


async def test_submit_login_extracts_credentials_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http = MagicMock()
    token = AuthToken()
    extract_credentials = AsyncMock()
    monkeypatch.setattr(
        password_module, "_raw_submit_login", AsyncMock(return_value={"ssecurity": "sec"})
    )
    monkeypatch.setattr(password_module, "extract_credentials", extract_credentials)

    await password_module.submit_login(http, token, "13800138000", "secret", "sign", "callback")

    extract_credentials.assert_awaited_once_with(http, {"ssecurity": "sec"}, token)


async def test_submit_login_raises_when_no_credentials_returned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http = MagicMock()
    monkeypatch.setattr(
        password_module,
        "_raw_submit_login",
        AsyncMock(return_value={"code": 0, "securityStatus": 0}),
    )

    with pytest.raises(AuthError, match="登录异常"):
        await password_module.submit_login(
            http, AuthToken(), "13800138000", "secret", "sign", "callback"
        )


# endregion


# region 短信验证码
async def test_ensure_ticket_login_ready_accepts_success() -> None:
    http = MagicMock()
    http.get = AsyncMock(return_value=_response('&&&START&&&{"code":0}'))

    await password_module.ensure_ticket_login_ready(http)

    http.get.assert_awaited_once()


async def test_ensure_ticket_login_ready_rejects_failure() -> None:
    http = MagicMock()
    http.get = AsyncMock(
        return_value=_response('&&&START&&&{"code":1,"description":"preference failed"}')
    )

    with pytest.raises(AuthError, match="登录偏好初始化失败"):
        await password_module.ensure_ticket_login_ready(http)


async def test_post_ticket_request_raises_captcha_error() -> None:
    http = MagicMock()
    http.post = AsyncMock(
        return_value=_response(
            '&&&START&&&{"code":87001,"description":"captcha","captchaUrl":"/pass/getCode?x=1"}'
        )
    )

    with pytest.raises(CaptchaRequiredError) as exc_info:
        await password_module._post_ticket_request(
            http,
            "https://example.com/send",
            "13800138000",
            error_prefix="验证码发送失败",
        )

    assert exc_info.value.captcha_url == "https://account.xiaomi.com/pass/getCode?x=1"


async def test_post_ticket_request_raises_auth_error_without_captcha() -> None:
    http = MagicMock()
    http.post = AsyncMock(return_value=_response('&&&START&&&{"code":1,"description":"boom"}'))

    with pytest.raises(AuthError, match="验证码发送失败: boom"):
        await password_module._post_ticket_request(
            http,
            "https://example.com/send",
            "13800138000",
            error_prefix="验证码发送失败",
        )


async def test_get_phone_info_returns_masked_phone_and_ticket() -> None:
    http = MagicMock()
    http.post = AsyncMock(
        return_value=_response(
            '&&&START&&&{"code":0,"data":{"phone":"191******54","ticketToken":"ticket"}}'
        )
    )

    phone, ticket = await password_module.get_phone_info(http, "13800138000")

    assert phone == "191******54"
    assert ticket == "ticket"


async def test_get_phone_info_requires_ticket_token() -> None:
    http = MagicMock()
    http.post = AsyncMock(
        return_value=_response('&&&START&&&{"code":0,"data":{"phone":"191******54"}}')
    )

    with pytest.raises(AuthError, match="未返回 ticketToken"):
        await password_module.get_phone_info(http, "13800138000")


async def test_fetch_captcha_image_returns_bytes() -> None:
    http = MagicMock()
    http.get = AsyncMock(return_value=_response(content=b"captcha-image"))

    image = await password_module.fetch_captcha_image(http, "https://example.com/captcha.png")

    assert image == b"captcha-image"


async def test_submit_ticket_auth_extracts_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http = MagicMock()
    http.post = AsyncMock(return_value=_response('&&&START&&&{"code":0,"ssecurity":"sec"}'))
    extract_credentials = AsyncMock()
    monkeypatch.setattr(password_module, "extract_credentials", extract_credentials)
    token = AuthToken()

    await password_module.submit_ticket_auth(http, token, "123456", "sign", "callback")

    extract_credentials.assert_awaited_once_with(http, {"code": 0, "ssecurity": "sec"}, token)


async def test_submit_ticket_auth_rejects_invalid_code() -> None:
    http = MagicMock()
    http.post = AsyncMock(
        return_value=_response('&&&START&&&{"code":70002,"desc":"invalid ticket"}')
    )

    with pytest.raises(AuthError, match="验证码验证失败"):
        await password_module.submit_ticket_auth(http, AuthToken(), "123456", "sign", "callback")


async def test_submit_ticket_auth_requires_ssecurity() -> None:
    http = MagicMock()
    http.post = AsyncMock(return_value=_response('&&&START&&&{"code":0}'))

    with pytest.raises(AuthError, match="未返回凭证"):
        await password_module.submit_ticket_auth(http, AuthToken(), "123456", "sign", "callback")


# endregion

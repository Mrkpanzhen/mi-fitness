"""STS 安全令牌交换。"""

from __future__ import annotations

import logging
import time

from mi_fitness.const import STS_HEALTH_URL
from mi_fitness.http import RetryAsyncClient
from mi_fitness.models import AuthToken

logger = logging.getLogger(__name__)


async def sts_exchange(http: RetryAsyncClient, token: AuthToken) -> None:
    """STS 安全令牌交换。

    使用 deviceId 完成 STS 验证。此步骤非致命，失败仅打印警告。

    Args:
        http: HTTP 客户端。
        token: 已有 device_id 的 AuthToken。
    """
    params = {
        "d": token.device_id,
        "ticket": "0",
        "pwd": "0",
        "p_ts": str(int(time.time() * 1000)),
        "fid": "0",
        "p_lm": "2",
        "p_ur": "CN",
    }

    try:
        resp = await http.get(STS_HEALTH_URL, params=params)
        if resp.text.strip() == "ok":
            logger.debug("STS 交换成功")
        else:
            logger.warning("STS 交换响应: %s", resp.text[:100])
    except Exception as e:
        logger.warning("STS 交换失败（非致命）: %s", e)

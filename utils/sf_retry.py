"""
SiliconFlow API 重试工具

提供带指数退避的请求重试函数，统一处理 429（速率限制）和超时错误。
通过环境变量配置默认行为：
  SF_REQUEST_DELAY_SECONDS  每次请求前基础延迟（秒），默认 1.0
  SF_MAX_RETRIES            最大重试次数，默认 3
  SF_API_TIMEOUT            请求超时时间（秒），默认 30
"""

from __future__ import annotations

import logging
import os
import time
from typing import Callable, Optional

import httpx

logger = logging.getLogger(__name__)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (ValueError, TypeError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (ValueError, TypeError):
        return default


def get_sf_timeout() -> int:
    """从环境变量读取 SiliconFlow API 超时秒数（SF_API_TIMEOUT，默认 30）。"""
    return _env_int("SF_API_TIMEOUT", 30)


def call_with_retry(
    fn: Callable[[], httpx.Response],
    *,
    max_retries: Optional[int] = None,
    delay: Optional[float] = None,
) -> httpx.Response:
    """
    执行 HTTP 调用并在遇到 429 或超时时自动指数退避重试。

    请求流程：
      1. 首次调用前睡眠 ``delay`` 秒（速率限制）。
      2. 若遇到 HTTP 429 或 :class:`httpx.TimeoutException`，
         按 ``delay × 2^attempt`` 指数退避后重试，最多 ``max_retries`` 次。
      3. 其他 HTTP 错误立即抛出，不重试。

    Args:
        fn: 无参数可调用对象，执行后返回 :class:`httpx.Response`。
        max_retries: 最大重试次数；``None`` 时读取环境变量
                     ``SF_MAX_RETRIES``（默认 3）。
        delay: 基础延迟秒数；``None`` 时读取环境变量
               ``SF_REQUEST_DELAY_SECONDS``（默认 1.0）。

    Returns:
        成功的 :class:`httpx.Response` 对象。

    Raises:
        httpx.HTTPStatusError: 非 429 HTTP 错误，或达到最大重试次数后仍为 429。
        httpx.TimeoutException: 达到最大重试次数后仍超时。
    """
    _max_retries = max_retries if max_retries is not None else _env_int("SF_MAX_RETRIES", 3)
    _delay = delay if delay is not None else _env_float("SF_REQUEST_DELAY_SECONDS", 1.0)

    last_exc: Optional[Exception] = None

    for attempt in range(_max_retries + 1):
        if attempt > 0:
            wait = _delay * (2 ** attempt)
            logger.debug("SiliconFlow API: 等待 %.2f 秒后重试（attempt=%d）", wait, attempt)
            time.sleep(wait)

        try:
            response = fn()
            if response.status_code == 429:
                logger.warning(
                    "SiliconFlow API 速率限制（429）, attempt=%d/%d", attempt, _max_retries
                )
                last_exc = httpx.HTTPStatusError(
                    f"429 Too Many Requests (attempt {attempt})",
                    request=response.request,
                    response=response,
                )
                if attempt < _max_retries:
                    continue
                raise last_exc
            response.raise_for_status()
            return response
        except httpx.TimeoutException as exc:
            logger.warning(
                "SiliconFlow API 请求超时, attempt=%d/%d: %s", attempt, _max_retries, exc
            )
            last_exc = exc
            if attempt < _max_retries:
                continue
            raise

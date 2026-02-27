"""
utils.sf_retry 单元测试

完全离线：使用 unittest.mock 模拟 httpx 调用，不发出真实 HTTP 请求。
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import httpx
import pytest

from utils.sf_retry import call_with_retry, get_sf_timeout


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _make_response(status_code: int = 200) -> MagicMock:
    """构造一个模拟的 httpx.Response 对象。"""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.request = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"{status_code}", request=resp.request, response=resp
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


# ---------------------------------------------------------------------------
# get_sf_timeout
# ---------------------------------------------------------------------------


class TestGetSfTimeout:
    def test_default_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SF_API_TIMEOUT", raising=False)
        assert get_sf_timeout() == 30

    def test_reads_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SF_API_TIMEOUT", "45")
        assert get_sf_timeout() == 45

    def test_invalid_env_falls_back_to_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SF_API_TIMEOUT", "not_a_number")
        assert get_sf_timeout() == 30


# ---------------------------------------------------------------------------
# call_with_retry — 成功路径
# ---------------------------------------------------------------------------


class TestCallWithRetrySuccess:
    def test_returns_response_on_first_attempt(self) -> None:
        resp = _make_response(200)
        fn = MagicMock(return_value=resp)
        with patch("utils.sf_retry.time.sleep"):
            result = call_with_retry(fn, max_retries=3, delay=0.0)
        assert result is resp
        fn.assert_called_once()

    def test_no_sleep_before_first_attempt(self) -> None:
        resp = _make_response(200)
        fn = MagicMock(return_value=resp)
        with patch("utils.sf_retry.time.sleep") as mock_sleep:
            call_with_retry(fn, max_retries=0, delay=1.5)
        mock_sleep.assert_not_called()


# ---------------------------------------------------------------------------
# call_with_retry — 429 重试
# ---------------------------------------------------------------------------


class TestCallWithRetry429:
    def test_retries_on_429_and_succeeds(self) -> None:
        resp_429 = _make_response(429)
        resp_200 = _make_response(200)
        fn = MagicMock(side_effect=[resp_429, resp_200])
        with patch("utils.sf_retry.time.sleep"):
            result = call_with_retry(fn, max_retries=3, delay=0.0)
        assert result is resp_200
        assert fn.call_count == 2

    def test_raises_after_max_retries_exhausted(self) -> None:
        resp_429 = _make_response(429)
        fn = MagicMock(return_value=resp_429)
        with patch("utils.sf_retry.time.sleep"):
            with pytest.raises(httpx.HTTPStatusError):
                call_with_retry(fn, max_retries=2, delay=0.0)
        assert fn.call_count == 3  # initial + 2 retries

    def test_exponential_backoff_delays(self) -> None:
        resp_429 = _make_response(429)
        resp_200 = _make_response(200)
        fn = MagicMock(side_effect=[resp_429, resp_429, resp_200])
        with patch("utils.sf_retry.time.sleep") as mock_sleep:
            call_with_retry(fn, max_retries=3, delay=1.0)
        # attempt 0: no sleep, attempt 1: sleep(2.0), attempt 2: sleep(4.0)
        calls = [c.args[0] for c in mock_sleep.call_args_list]
        assert calls == [2.0, 4.0]
        assert fn.call_count == 3


# ---------------------------------------------------------------------------
# call_with_retry — 超时重试
# ---------------------------------------------------------------------------


class TestCallWithRetryTimeout:
    def test_retries_on_timeout_and_succeeds(self) -> None:
        resp_200 = _make_response(200)
        fn = MagicMock(
            side_effect=[httpx.ReadTimeout("timeout", request=MagicMock()), resp_200]
        )
        with patch("utils.sf_retry.time.sleep"):
            result = call_with_retry(fn, max_retries=3, delay=0.0)
        assert result is resp_200
        assert fn.call_count == 2

    def test_raises_timeout_after_max_retries(self) -> None:
        fn = MagicMock(
            side_effect=httpx.ReadTimeout("timeout", request=MagicMock())
        )
        with patch("utils.sf_retry.time.sleep"):
            with pytest.raises(httpx.TimeoutException):
                call_with_retry(fn, max_retries=2, delay=0.0)
        assert fn.call_count == 3


# ---------------------------------------------------------------------------
# call_with_retry — 非重试错误
# ---------------------------------------------------------------------------


class TestCallWithRetryNonRetryableErrors:
    def test_raises_immediately_on_500(self) -> None:
        resp_500 = _make_response(500)
        fn = MagicMock(return_value=resp_500)
        with patch("utils.sf_retry.time.sleep"):
            with pytest.raises(httpx.HTTPStatusError):
                call_with_retry(fn, max_retries=3, delay=0.0)
        fn.assert_called_once()


# ---------------------------------------------------------------------------
# call_with_retry — 从环境变量读取默认值
# ---------------------------------------------------------------------------


class TestCallWithRetryEnvDefaults:
    def test_reads_max_retries_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SF_MAX_RETRIES", "1")
        monkeypatch.setenv("SF_REQUEST_DELAY_SECONDS", "0.0")
        resp_429 = _make_response(429)
        fn = MagicMock(return_value=resp_429)
        with patch("utils.sf_retry.time.sleep"):
            with pytest.raises(httpx.HTTPStatusError):
                call_with_retry(fn)
        assert fn.call_count == 2  # initial + 1 retry

    def test_reads_delay_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SF_REQUEST_DELAY_SECONDS", "2.5")
        monkeypatch.setenv("SF_MAX_RETRIES", "1")
        resp_429 = _make_response(429)
        resp_200 = _make_response(200)
        fn = MagicMock(side_effect=[resp_429, resp_200])
        with patch("utils.sf_retry.time.sleep") as mock_sleep:
            call_with_retry(fn)
        # attempt 0: no sleep; attempt 1: sleep(2.5 * 2^1 = 5.0)
        mock_sleep.assert_called_once_with(5.0)

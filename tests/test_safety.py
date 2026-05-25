from __future__ import annotations

import pytest

from rpa_helper.core.safety import SafetyManager


def test_initial_state_not_stopped() -> None:
    s = SafetyManager()
    assert s.is_stop_requested() is False
    s.raise_if_stopped()  # should not raise


def test_request_stop_sets_flag() -> None:
    s = SafetyManager()
    s.request_stop()
    assert s.is_stop_requested() is True


def test_raise_if_stopped_raises_after_request() -> None:
    s = SafetyManager()
    s.request_stop()
    with pytest.raises(InterruptedError, match="停止"):
        s.raise_if_stopped()


def test_reset_clears_flag() -> None:
    s = SafetyManager()
    s.request_stop()
    s.reset()
    assert s.is_stop_requested() is False
    s.raise_if_stopped()


def test_multiple_request_stop_idempotent() -> None:
    s = SafetyManager()
    s.request_stop()
    s.request_stop()
    s.request_stop()
    assert s.is_stop_requested() is True

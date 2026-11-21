"""``HAPPYCLAW_*`` variables win; ``OCTOP_*`` still work, with a deprecation warning."""

from __future__ import annotations

import warnings

import pytest

from happyclaw_harness import env_compat


@pytest.fixture(autouse=True)
def _fresh_deprecation_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(env_compat, "_deprecated_names", set())


def test_new_name_wins_over_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAPPYCLAW_CHECKPOINT_KEEP_LAST", "5")
    monkeypatch.setenv("OCTOP_CHECKPOINT_KEEP_LAST", "9")
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        assert env_compat.get_env("HAPPYCLAW_CHECKPOINT_KEEP_LAST") == "5"


def test_legacy_name_falls_back_with_one_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HAPPYCLAW_CHECKPOINT_KEEP_LAST", raising=False)
    monkeypatch.setenv("OCTOP_CHECKPOINT_KEEP_LAST", "9")
    with pytest.warns(DeprecationWarning, match="OCTOP_CHECKPOINT_KEEP_LAST is deprecated"):
        assert env_compat.get_env("HAPPYCLAW_CHECKPOINT_KEEP_LAST") == "9"
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        assert env_compat.get_env("HAPPYCLAW_CHECKPOINT_KEEP_LAST") == "9"


def test_unset_returns_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HAPPYCLAW_CHECKPOINT_VACUUM", raising=False)
    monkeypatch.delenv("OCTOP_CHECKPOINT_VACUUM", raising=False)
    assert env_compat.get_env("HAPPYCLAW_CHECKPOINT_VACUUM") is None
    assert env_compat.get_env("HAPPYCLAW_CHECKPOINT_VACUUM", "fallback") == "fallback"


def test_is_set_sees_both_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HAPPYCLAW_CHECKPOINT_VACUUM", raising=False)
    assert not env_compat.is_set("HAPPYCLAW_CHECKPOINT_VACUUM")
    monkeypatch.setenv("OCTOP_CHECKPOINT_VACUUM", "1")
    assert env_compat.is_set("HAPPYCLAW_CHECKPOINT_VACUUM")
    monkeypatch.setenv("HAPPYCLAW_CHECKPOINT_VACUUM", "1")
    monkeypatch.delenv("OCTOP_CHECKPOINT_VACUUM")
    assert env_compat.is_set("HAPPYCLAW_CHECKPOINT_VACUUM")


def test_legacy_checkpoint_retention_still_applies(monkeypatch: pytest.MonkeyPatch) -> None:
    from happyclaw_harness.middleware.memory import checkpoint_retention_policy

    for suffix in ("RETENTION", "KEEP_LAST", "KEEP_DAYS", "VACUUM", "BACKUP_BEFORE_PRUNE", "BACKUP_KEEP_DAYS"):
        monkeypatch.delenv(f"HAPPYCLAW_CHECKPOINT_{suffix}", raising=False)
    monkeypatch.setenv("OCTOP_CHECKPOINT_KEEP_LAST", "7")
    with pytest.warns(DeprecationWarning, match="OCTOP_CHECKPOINT_KEEP_LAST is deprecated"):
        policy = checkpoint_retention_policy()
    assert policy["keep_last"] == 7


def test_durability_new_name_wins_over_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAPPYCLAW_CHECKPOINT_DURABILITY", "async")
    monkeypatch.setenv("OCTOP_CHECKPOINT_DURABILITY", "sync")
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        raw = env_compat.get_env("HAPPYCLAW_CHECKPOINT_DURABILITY") or ""
    assert raw.strip().lower() == "async"

"""Fail-closed boundary. No provider adapter exists in this milestone."""

from collections.abc import Callable
from typing import Never


class ExternalIntegrationDisabled(RuntimeError):
    pass


def invoke_external(mode: str, integration: Callable, *args, **kwargs) -> Never:
    # Check BEFORE resolving credentials, constructing clients, or invoking callbacks.
    # Unknown modes also fail closed. Live execution is deliberately unavailable.
    if mode == "dry_run":
        raise ExternalIntegrationDisabled("External integrations are forbidden in dry-run mode.")
    raise ExternalIntegrationDisabled("External execution is unavailable in this milestone.")

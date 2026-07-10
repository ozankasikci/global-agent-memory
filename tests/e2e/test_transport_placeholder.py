from __future__ import annotations

import pytest


@pytest.mark.e2e
@pytest.mark.skip(reason="Enabled in Phase 10 when daemon and stdio transports exist")
def test_daemon_through_stdio_proxy() -> None:
    """Reserve the mandatory E2E gate without claiming transport coverage early."""

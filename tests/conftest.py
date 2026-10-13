from pathlib import Path

import pytest

from escalate_anything.registry import Registry

FIXTURES = Path(__file__).parent / "fixtures" / "registry"


@pytest.fixture
def fixture_registry() -> Registry:
    return Registry.load(FIXTURES)

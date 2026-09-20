import gzip
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    with gzip.open(FIXTURES / name, "rt", encoding="utf-8", errors="replace") as fh:
        return fh.read()


@pytest.fixture(scope="session")
def avdx_html() -> str:
    """AvidXchange FY2024 10-K. Clean: ICFR effective, no material weakness."""
    return _load("avdx_10k_fy2024.htm.gz")


@pytest.fixture(scope="session")
def bglc_html() -> str:
    """BioNexus Gene Lab FY2022 10-K/A. Retracts a previously disclosed weakness."""
    return _load("bglc_10ka_fy2022.htm.gz")


@pytest.fixture(scope="session")
def ceridian_html() -> str:
    """Ceridian FY2022 10-K/A. Explanatory Note references Item 9A before it."""
    return _load("ceridian_10ka_fy2022.htm.gz")

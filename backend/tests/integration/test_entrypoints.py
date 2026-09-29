"""Standalone entry points must register every model, or foreign keys cannot resolve."""

import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("module", ["app.worker", "app.cli"])
def test_entrypoint_registers_all_models(module: str) -> None:
    code = (
        f"import {module}\n"
        "from sqlalchemy.orm import configure_mappers\n"
        "from app.core.database import Base\n"
        "configure_mappers()\n"
        "tables = set(Base.metadata.tables)\n"
        "for fk in (fk for t in Base.metadata.tables.values() for fk in t.foreign_keys):\n"
        "    assert fk.column is not None\n"
        "assert {'organisations', 'crawl_pages', 'crawl_links'} <= tables, tables\n"
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr

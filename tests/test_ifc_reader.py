import sys
import types
from pathlib import Path

import pytest

from bim.ifc_reader import read_ifc_elements


class UploadedIfc:
    name = "example.ifc"

    def getvalue(self) -> bytes:
        return b"ISO-10303-21;\nEND-ISO-10303-21;\n"


class EmptyIfcModel:
    def by_type(self, _ifc_type: str) -> list:
        return []


def test_temporary_ifc_is_removed_after_open(monkeypatch: pytest.MonkeyPatch) -> None:
    opened_path: list[str] = []

    def fake_open(path: str) -> EmptyIfcModel:
        opened_path.append(path)
        assert Path(path).exists()
        return EmptyIfcModel()

    monkeypatch.setitem(sys.modules, "ifcopenshell", types.SimpleNamespace(open=fake_open))

    result = read_ifc_elements(UploadedIfc())

    assert result.empty
    assert len(opened_path) == 1
    assert not Path(opened_path[0]).exists()


def test_temporary_ifc_is_removed_when_open_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    opened_path: list[str] = []

    def failing_open(path: str) -> None:
        opened_path.append(path)
        assert Path(path).exists()
        raise ValueError("invalid IFC")

    monkeypatch.setitem(sys.modules, "ifcopenshell", types.SimpleNamespace(open=failing_open))

    with pytest.raises(ValueError, match="invalid IFC"):
        read_ifc_elements(UploadedIfc())

    assert len(opened_path) == 1
    assert not Path(opened_path[0]).exists()

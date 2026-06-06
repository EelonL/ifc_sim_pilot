from __future__ import annotations

import tempfile
from pathlib import Path
import pandas as pd

SUPPORTED_TYPES = ["IfcColumn", "IfcBeam", "IfcSlab", "IfcWall", "IfcMember"]


def read_ifc_elements(uploaded_file) -> pd.DataFrame:
    """Read a small set of structural elements from an uploaded IFC file.

    Returns a normalized dataframe used by the simulation. The function is
    intentionally conservative: if storey/zone/task cannot be inferred, it
    fills them with simple defaults that the user can later edit in the UI.
    """
    try:
        import ifcopenshell
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "IfcOpenShell is not installed or could not be imported. "
            "Use the sample CSV mode or install ifcopenshell."
        ) from exc

    suffix = Path(uploaded_file.name).suffix or ".ifc"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.getvalue())
        tmp_path = tmp.name

    model = ifcopenshell.open(tmp_path)
    rows = []

    for ifc_type in SUPPORTED_TYPES:
        for obj in model.by_type(ifc_type):
            guid = getattr(obj, "GlobalId", None)
            name = getattr(obj, "Name", None) or ifc_type
            storey = _safe_storey(obj)
            zone = _infer_zone(name)
            task = _default_task(ifc_type)
            rows.append(
                {
                    "guid": guid,
                    "name": name,
                    "ifc_type": ifc_type,
                    "storey": storey,
                    "zone": zone,
                    "task": task,
                    "quantity": 1,
                }
            )

    if not rows:
        return pd.DataFrame(columns=["guid", "name", "ifc_type", "storey", "zone", "task", "quantity"])

    df = pd.DataFrame(rows)
    df["storey"] = pd.to_numeric(df["storey"], errors="coerce").fillna(1).astype(int)
    df["zone"] = df["zone"].fillna("A")
    return df


def _safe_storey(obj) -> int:
    """Try to find the containing building storey from IFC decomposition."""
    try:
        for rel in getattr(obj, "ContainedInStructure", []) or []:
            structure = getattr(rel, "RelatingStructure", None)
            if structure and structure.is_a("IfcBuildingStorey"):
                name = getattr(structure, "Name", "") or ""
                digits = "".join(ch for ch in name if ch.isdigit())
                return int(digits) if digits else 1
    except Exception:
        pass
    return 1


def _infer_zone(name: str) -> str:
    upper = (name or "").upper()
    for candidate in ["A", "B", "C", "D"]:
        if f"ZONE {candidate}" in upper or f"LOHKO {candidate}" in upper or f" {candidate}" in upper:
            return candidate
    return "A"


def _default_task(ifc_type: str) -> str:
    return {
        "IfcColumn": "Install columns",
        "IfcBeam": "Install beams",
        "IfcSlab": "Install slabs",
        "IfcWall": "Install walls",
        "IfcMember": "Install members",
    }.get(ifc_type, "Install elements")

from __future__ import annotations

import re
import tempfile
from pathlib import Path
import pandas as pd

# Broader list than v1. Real IFC exports often use proxy, assembly, wallstandardcase, plate, etc.
SUPPORTED_TYPES = [
    "IfcColumn",
    "IfcBeam",
    "IfcSlab",
    "IfcWall",
    "IfcWallStandardCase",
    "IfcMember",
    "IfcPlate",
    "IfcElementAssembly",
    "IfcBuildingElementProxy",
    "IfcFooting",
    "IfcPile",
    "IfcStair",
]

REQUIRED_COLUMNS = ["guid", "name", "ifc_type", "storey", "zone", "task", "quantity"]


def read_ifc_elements(uploaded_file) -> pd.DataFrame:
    """Read structural-ish elements from an uploaded IFC file.

    This pilot intentionally returns a simple tabular representation. It does
    not yet read detailed geometry. The key field is the IFC GlobalId, which
    lets later versions link simulation status back to the 3D object.
    """
    try:
        import ifcopenshell
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "IfcOpenShell is not installed or could not be imported. "
            "Use the sample CSV mode or install ifcopenshell."
        ) from exc

    suffix = Path(getattr(uploaded_file, "name", "model.ifc")).suffix or ".ifc"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.getvalue())
        tmp_path = tmp.name

    model = ifcopenshell.open(tmp_path)
    rows: list[dict] = []

    for ifc_type in SUPPORTED_TYPES:
        try:
            objects = model.by_type(ifc_type)
        except RuntimeError:
            # Some IFC schemas do not contain all entity names.
            continue

        for obj in objects:
            guid = getattr(obj, "GlobalId", None)
            name = getattr(obj, "Name", None) or getattr(obj, "ObjectType", None) or ifc_type
            storey = _safe_storey(obj)
            zone = _infer_zone(name)
            task = _default_task(ifc_type, name)
            rows.append(
                {
                    "guid": guid,
                    "name": str(name),
                    "ifc_type": ifc_type,
                    "storey": storey,
                    "zone": zone,
                    "task": task,
                    "quantity": 1,
                }
            )

    if not rows:
        return pd.DataFrame(columns=REQUIRED_COLUMNS)

    df = pd.DataFrame(rows)
    df["storey"] = pd.to_numeric(df["storey"], errors="coerce").fillna(1).astype(int)
    df["zone"] = df["zone"].fillna("A")
    # Remove rare duplicates if an element is returned through overlapping categories.
    df = df.drop_duplicates(subset=["guid"], keep="first")
    return df[REQUIRED_COLUMNS]


def _safe_storey(obj) -> int:
    """Try to find the containing building storey from IFC spatial relations."""
    # Common direct containment: element -> IfcRelContainedInSpatialStructure -> storey
    try:
        for rel in getattr(obj, "ContainedInStructure", []) or []:
            structure = getattr(rel, "RelatingStructure", None)
            if structure and structure.is_a("IfcBuildingStorey"):
                return _storey_number_from_name(getattr(structure, "Name", ""))
    except Exception:
        pass

    # Some exports nest through assemblies or decomposition. Walk one step upward.
    try:
        for rel in getattr(obj, "Decomposes", []) or []:
            parent = getattr(rel, "RelatingObject", None)
            if parent:
                return _safe_storey(parent)
    except Exception:
        pass

    return 1


def _storey_number_from_name(name: str) -> int:
    text = str(name or "")
    nums = re.findall(r"-?\d+", text)
    if not nums:
        return 1
    # Avoid returning 0 because the pilot sorting/status view is simpler with 1-based floors.
    value = int(nums[0])
    return value if value > 0 else 1


def _infer_zone(name: str) -> str:
    upper = (name or "").upper()
    patterns = [
        r"\bZONE\s*([A-Z])\b",
        r"\bLOHKO\s*([A-Z])\b",
        r"\bBLOCK\s*([A-Z])\b",
    ]
    for pat in patterns:
        m = re.search(pat, upper)
        if m:
            return m.group(1)
    return "A"


def _default_task(ifc_type: str, name: str | None = None) -> str:
    text = f"{ifc_type} {name or ''}".lower()
    if "column" in text or "pilari" in text:
        return "Install columns"
    if "beam" in text or "palk" in text:
        return "Install beams"
    if "slab" in text or "laatta" in text or "floor" in text:
        return "Install slabs"
    if "wall" in text or "seinä" in text:
        return "Install walls"
    if "member" in text or "assembly" in text or "proxy" in text or "plate" in text:
        return "Install members"
    if "footing" in text or "pile" in text:
        return "Install elements"
    return "Install elements"

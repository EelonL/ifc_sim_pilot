from __future__ import annotations

import re
import tempfile
from collections import Counter
from pathlib import Path
from typing import BinaryIO

import pandas as pd

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


def uploaded_bytes(uploaded_file) -> bytes:
    if hasattr(uploaded_file, "getvalue"):
        return uploaded_file.getvalue()
    return uploaded_file.read()


def diagnose_ifc(uploaded_file) -> pd.DataFrame:
    """Fast text-level IFC entity count. Does not require IfcOpenShell."""
    raw = uploaded_bytes(uploaded_file)
    text = raw.decode("utf-8", errors="ignore")
    entity_re = re.compile(r"=\s*([A-Z0-9_]+)\s*\(")
    counts = Counter(entity_re.findall(text))
    rows = [{"ifc_entity": k, "count": v} for k, v in counts.items()]
    if not rows:
        return pd.DataFrame(columns=["ifc_entity", "count", "used_by_pilot"])
    df = pd.DataFrame(rows).sort_values("count", ascending=False).reset_index(drop=True)
    supported_upper = {x.upper() for x in SUPPORTED_TYPES}
    df["used_by_pilot"] = df["ifc_entity"].isin(supported_upper)
    return df


def read_ifc_elements(uploaded_file, max_objects: int | None = None) -> pd.DataFrame:
    """Read structural-ish elements from an uploaded IFC file.

    Returns one row per IFC object. Large models should usually be aggregated
    in the app before simulation.
    """
    try:
        import ifcopenshell
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "IfcOpenShell is not installed or could not be imported. "
            "Use the sample CSV mode or install ifcopenshell."
        ) from exc

    raw = uploaded_bytes(uploaded_file)
    suffix = Path(getattr(uploaded_file, "name", "model.ifc")).suffix or ".ifc"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(raw)
        tmp_path = tmp.name

    model = ifcopenshell.open(tmp_path)
    rows: list[dict] = []

    for ifc_type in SUPPORTED_TYPES:
        try:
            objects = model.by_type(ifc_type)
        except Exception:
            continue

        for obj in objects:
            guid = getattr(obj, "GlobalId", None)
            name = getattr(obj, "Name", None) or getattr(obj, "ObjectType", None) or ifc_type
            storey = _safe_storey(obj)
            zone = _infer_zone(name)
            task = _default_task(ifc_type, name)
            rows.append(
                {
                    "guid": guid or f"NO-GUID-{ifc_type}-{len(rows)}",
                    "name": str(name),
                    "ifc_type": ifc_type,
                    "storey": storey,
                    "zone": zone,
                    "task": task,
                    "quantity": 1,
                }
            )
            if max_objects is not None and len(rows) >= max_objects:
                break
        if max_objects is not None and len(rows) >= max_objects:
            break

    if not rows:
        return pd.DataFrame(columns=REQUIRED_COLUMNS)

    df = pd.DataFrame(rows)
    df["storey"] = pd.to_numeric(df["storey"], errors="coerce").fillna(1).astype(int)
    df["zone"] = df["zone"].fillna("A")
    df = df.drop_duplicates(subset=["guid"], keep="first")
    return df[REQUIRED_COLUMNS]


def _safe_storey(obj) -> int:
    try:
        for rel in getattr(obj, "ContainedInStructure", []) or []:
            structure = getattr(rel, "RelatingStructure", None)
            if structure and structure.is_a("IfcBuildingStorey"):
                return _storey_number_from_name(getattr(structure, "Name", ""))
    except Exception:
        pass

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

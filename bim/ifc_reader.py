from __future__ import annotations

import re
import tempfile
from collections import Counter
from pathlib import Path

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

REQUIRED_COLUMNS = [
    "guid", "name", "ifc_type", "storey", "zone", "task", "quantity",
    "material", "material_category", "parent_assembly_guid", "parent_assembly_name",
    "x", "y", "z",
]


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


def diagnose_materials(uploaded_file) -> pd.DataFrame:
    """Text-level material association count by assigned IFC object ids."""
    raw = uploaded_bytes(uploaded_file)
    text = raw.decode("utf-8", errors="ignore")
    material_map = _parse_material_associations(text)
    counts = Counter(material_map.values())
    rows = []
    for material, count in counts.items():
        rows.append({
            "material": material,
            "material_category": _material_category(material),
            "assigned_object_count": count,
        })
    if not rows:
        return pd.DataFrame(columns=["material", "material_category", "assigned_object_count"])
    return pd.DataFrame(rows).sort_values(["assigned_object_count", "material"], ascending=[False, True]).reset_index(drop=True)


def read_ifc_elements(uploaded_file, max_objects: int | None = None) -> pd.DataFrame:
    """Read structural-ish elements from an uploaded IFC file.

    Returns one row per IFC object, enriched with material, parent assembly and
    approximate placement coordinates (x, y, z) when available. The coordinate
    extraction uses IFC ObjectPlacement, not full geometry, so it is lightweight
    enough for Streamlit Cloud but approximate.
    """
    try:
        import ifcopenshell
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "IfcOpenShell is not installed or could not be imported. "
            "Use the sample CSV mode or install ifcopenshell."
        ) from exc

    raw = uploaded_bytes(uploaded_file)
    text = raw.decode("utf-8", errors="ignore")
    material_by_step_id = _parse_material_associations(text)

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
            material = material_by_step_id.get(int(obj.id()), "Unknown")
            parent_guid, parent_name = _parent_assembly(obj)
            x, y, z = _object_placement_xyz(obj)
            rows.append(
                {
                    "guid": guid or f"NO-GUID-{ifc_type}-{len(rows)}",
                    "name": str(name),
                    "ifc_type": ifc_type,
                    "storey": storey,
                    "zone": zone,
                    "task": task,
                    "quantity": 1,
                    "material": material,
                    "material_category": _material_category(material),
                    "parent_assembly_guid": parent_guid or "",
                    "parent_assembly_name": parent_name or "",
                    "x": x,
                    "y": y,
                    "z": z,
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
    for col in ["x", "y", "z"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.drop_duplicates(subset=["guid"], keep="first")
    return df[REQUIRED_COLUMNS]


def _parse_material_associations(text: str) -> dict[int, str]:
    """Parse simple IfcMaterial and IfcRelAssociatesMaterial relationships."""
    material_names: dict[int, str] = {}
    material_re = re.compile(r"#(\d+)\s*=\s*IFCMATERIAL\s*\(\s*'((?:[^']|'')*)'", re.IGNORECASE)
    for m in material_re.finditer(text):
        material_names[int(m.group(1))] = m.group(2).replace("''", "'")

    obj_to_material: dict[int, str] = {}
    rel_re = re.compile(
        r"#\d+\s*=\s*IFCRELASSOCIATESMATERIAL\s*\([^;]*?\((#[\d#,\s]+)\)\s*,\s*#(\d+)\s*\)\s*;",
        re.IGNORECASE | re.DOTALL,
    )
    for rel in rel_re.finditer(text):
        object_refs = [int(x) for x in re.findall(r"#(\d+)", rel.group(1))]
        mat_id = int(rel.group(2))
        mat_name = material_names.get(mat_id, f"Material #{mat_id}")
        for oid in object_refs:
            obj_to_material[oid] = mat_name
    return obj_to_material


def _material_category(material: str | None) -> str:
    text = str(material or "").upper()
    if "STEEL" in text or "S355" in text or "AISI" in text or "TERÄS" in text:
        return "Steel"
    if "CONCRETE" in text or "BETON" in text or re.search(r"\bC\d{2}/\d{2}\b", text):
        return "Concrete"
    if "WOOD" in text or "TIMBER" in text or "PUU" in text:
        return "Timber"
    if "EPS" in text or "FINNFOAM" in text or "THERMISOL" in text or "PAROC" in text or "KIVIVILLA" in text:
        return "Insulation"
    if "UNDEFINED" in text or not text or text == "UNKNOWN":
        return "Unknown"
    return "Other"


def _parent_assembly(obj) -> tuple[str, str]:
    try:
        for rel in getattr(obj, "Decomposes", []) or []:
            parent = getattr(rel, "RelatingObject", None)
            if parent is not None and parent.is_a("IfcElementAssembly"):
                return str(getattr(parent, "GlobalId", "") or ""), str(getattr(parent, "Name", "") or "IfcElementAssembly")
    except Exception:
        pass
    return "", ""


def _object_placement_xyz(obj) -> tuple[float | None, float | None, float | None]:
    """Return approximate absolute placement coordinates.

    This recursively sums IfcLocalPlacement.Location coordinates. It ignores
    local axis rotation, so it is intended for an approximate 3D status view,
    not for measurement or clash geometry.
    """
    try:
        placement = getattr(obj, "ObjectPlacement", None)
        return _placement_xyz(placement)
    except Exception:
        return None, None, None


def _placement_xyz(placement, depth: int = 0) -> tuple[float | None, float | None, float | None]:
    if placement is None or depth > 20:
        return 0.0, 0.0, 0.0

    px, py, pz = 0.0, 0.0, 0.0
    try:
        parent = getattr(placement, "PlacementRelTo", None)
        if parent is not None:
            p = _placement_xyz(parent, depth + 1)
            px, py, pz = [float(v or 0.0) for v in p]
    except Exception:
        pass

    try:
        rel = getattr(placement, "RelativePlacement", None)
        loc = getattr(rel, "Location", None)
        coords = list(getattr(loc, "Coordinates", []) or [])
        x = float(coords[0]) if len(coords) > 0 else 0.0
        y = float(coords[1]) if len(coords) > 1 else 0.0
        z = float(coords[2]) if len(coords) > 2 else 0.0
        return px + x, py + y, pz + z
    except Exception:
        return px, py, pz


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
    if "assembly" in text or "ristikko" in text or "truss" in text:
        return "Install assemblies"
    if "member" in text or "plate" in text:
        return "Install members"
    return "Install elements"

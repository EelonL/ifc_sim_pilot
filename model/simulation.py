from __future__ import annotations

import numpy as np
import pandas as pd

TASK_ORDER = {
    "Install columns": 1,
    "Install walls": 2,
    "Install members": 2,
    "Install beams": 3,
    "Install assemblies": 3,
    "Install slabs": 4,
    "Install elements": 5,
}

BASE_COLUMNS = ["guid", "name", "ifc_type", "storey", "zone", "task", "quantity"]
OPTIONAL_COLUMNS = ["material", "material_category", "parent_assembly_guid", "parent_assembly_name"]
REQUIRED_COLUMNS = BASE_COLUMNS


def normalize_elements(df: pd.DataFrame) -> pd.DataFrame:
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    out = df.copy()
    for col in OPTIONAL_COLUMNS:
        if col not in out.columns:
            out[col] = "Unknown" if "material" in col else ""
    out = out[BASE_COLUMNS + OPTIONAL_COLUMNS].copy()
    out["guid"] = out["guid"].astype(str)
    out["name"] = out["name"].astype(str)
    out["ifc_type"] = out["ifc_type"].astype(str)
    out["storey"] = pd.to_numeric(out["storey"], errors="coerce").fillna(1).astype(int)
    out["zone"] = out["zone"].fillna("A").astype(str)
    out["task"] = out["task"].fillna("Install elements").astype(str)
    out["quantity"] = pd.to_numeric(out["quantity"], errors="coerce").fillna(1).clip(lower=1)
    out["material"] = out["material"].fillna("Unknown").astype(str)
    out["material_category"] = out["material_category"].fillna("Unknown").astype(str)
    out["parent_assembly_guid"] = out["parent_assembly_guid"].fillna("").astype(str)
    out["parent_assembly_name"] = out["parent_assembly_name"].fillna("").astype(str)
    out["task_order"] = out["task"].map(TASK_ORDER).fillna(99).astype(int)
    return out.sort_values(["storey", "zone", "task_order", "material_category", "ifc_type", "name"]).reset_index(drop=True)


def filter_elements(
    df: pd.DataFrame,
    material_categories: list[str] | None = None,
    materials: list[str] | None = None,
    prefer_assemblies: bool = True,
) -> pd.DataFrame:
    """Apply user-facing filters before aggregation and simulation."""
    out = normalize_elements(df)
    if material_categories:
        out = out[out["material_category"].isin(material_categories)]
    if materials:
        out = out[out["material"].isin(materials)]
    if prefer_assemblies:
        # If a child part is decomposed under an IfcElementAssembly AND that parent
        # assembly is still present after the user's filters, keep the assembly row
        # and do not count the child part as a separate install.
        #
        # Important: this must be done after material filtering. If the user selects
        # Concrete and the parent assembly itself is Steel/Unknown, concrete child
        # elements should not disappear merely because they have a parent assembly.
        parent_guids = set(out.loc[out["ifc_type"].eq("IfcElementAssembly"), "guid"].astype(str))
        child_counted_by_parent = (
            out["parent_assembly_guid"].astype(str).isin(parent_guids)
            & out["ifc_type"].ne("IfcElementAssembly")
        )
        out = out.loc[~child_counted_by_parent].copy()
    return out.reset_index(drop=True)


def aggregate_elements(df: pd.DataFrame, include_material: bool = True) -> pd.DataFrame:
    """Aggregate many IFC objects into installable work packages.

    Compatible with both pandas 2.x and 3.x. Handles empty filtered data safely.
    """
    norm = normalize_elements(df)

    empty_cols = BASE_COLUMNS + OPTIONAL_COLUMNS
    if norm.empty:
        return pd.DataFrame(columns=empty_cols)

    group_cols = ["storey", "zone", "task", "ifc_type"]
    if include_material:
        group_cols += ["material_category", "material"]

    grouped = (
        norm.groupby(group_cols, dropna=False, as_index=False)
        .agg(quantity=("quantity", "sum"), element_count=("guid", "count"))
        .sort_values(group_cols)
        .reset_index(drop=True)
    )

    if grouped.empty:
        return pd.DataFrame(columns=empty_cols)

    # Avoid DataFrame.apply(axis=1) here: in pandas 3.x, assigning the result of
    # apply on an empty or edge-case frame can raise "Cannot set a DataFrame with
    # multiple columns to the single column ...". Vectorised string construction is
    # safer and faster.
    material_part = ""
    if "material_category" in grouped.columns:
        material_part = grouped["material_category"].fillna("").astype(str)
    else:
        material_part = pd.Series([""] * len(grouped), index=grouped.index)

    grouped["guid"] = (
        "GROUP-S" + grouped["storey"].astype(str)
        + "-Z" + grouped["zone"].astype(str)
        + "-" + grouped["task"].astype(str)
        + "-" + grouped["ifc_type"].astype(str)
        + "-" + material_part.astype(str)
    )

    grouped["name"] = (
        grouped["task"].astype(str)
        + " | " + grouped["ifc_type"].astype(str)
        + " | " + material_part.astype(str)
        + " | S" + grouped["storey"].astype(str)
        + " | Zone " + grouped["zone"].astype(str)
        + " (" + grouped["element_count"].astype(int).astype(str) + " objs)"
    )

    for col in OPTIONAL_COLUMNS:
        if col not in grouped.columns:
            grouped[col] = "" if "parent" in col else "Unknown"
        else:
            grouped[col] = grouped[col].fillna("" if "parent" in col else "Unknown").astype(str)

    return grouped[BASE_COLUMNS + OPTIONAL_COLUMNS].reset_index(drop=True)


def run_simulation(
    elements: pd.DataFrame,
    scenario_name: str,
    crew_count: int,
    crane_count: int,
    elements_per_crew_per_day: int,
    delivery_reliability: float,
    rework_probability: float,
    seed: int = 42,
) -> pd.DataFrame:
    """Run a simple discrete-day frame installation simulation.

    The unit of simulation may be a single IFC object or an aggregated work package.
    Quantity controls how much capacity the row consumes.
    """
    rng = np.random.default_rng(seed)
    df = normalize_elements(elements)

    crane_capacity_per_day = max(1, crane_count) * elements_per_crew_per_day
    crew_capacity_per_day = max(1, crew_count) * elements_per_crew_per_day
    daily_capacity = max(1, min(crane_capacity_per_day, crew_capacity_per_day))

    scheduled = []
    current_day = 1
    capacity_left = daily_capacity

    for _, row in df.iterrows():
        qty = int(max(1, round(float(row["quantity"]))))
        work_days = int(np.ceil(qty / daily_capacity))

        if capacity_left < min(qty, daily_capacity):
            current_day += 1
            capacity_left = daily_capacity

        delivery_wait = 0 if rng.random() <= delivery_reliability else int(rng.integers(1, 4))
        rework_wait = int(rng.integers(1, 3)) if rng.random() <= rework_probability else 0
        start_day = current_day + delivery_wait
        finish_day = start_day + max(1, work_days) - 1 + rework_wait

        delay_reason = []
        if delivery_wait:
            delay_reason.append("delivery")
        if rework_wait:
            delay_reason.append("rework")

        scheduled.append(
            {
                **row.to_dict(),
                "scenario": scenario_name,
                "start_day": int(start_day),
                "finish_day": int(finish_day),
                "work_days": int(work_days),
                "delay_days": int(delivery_wait + rework_wait),
                "delay_reason": ", ".join(delay_reason) if delay_reason else "",
                "daily_capacity": int(daily_capacity),
            }
        )

        current_day = finish_day
        capacity_left = daily_capacity

    return pd.DataFrame(scheduled)


def status_for_day(schedule: pd.DataFrame, day: int) -> pd.DataFrame:
    if schedule.empty:
        return pd.DataFrame()
    out = schedule.copy()
    out["day"] = day
    out["status"] = np.select(
        [
            out["finish_day"] <= day,
            (out["start_day"] <= day) & (out["finish_day"] > day),
        ],
        ["installed", "in_progress"],
        default="waiting",
    )
    return out


def progress_by_day(schedule: pd.DataFrame) -> pd.DataFrame:
    if schedule.empty:
        return pd.DataFrame(columns=["day", "installed_quantity", "cumulative_installed_quantity"])
    max_day = int(schedule["finish_day"].max())
    rows = []
    for day in range(1, max_day + 1):
        installed = schedule.loc[schedule["finish_day"] <= day, "quantity"].sum()
        rows.append({"day": day, "cumulative_installed_quantity": float(installed)})
    prog = pd.DataFrame(rows)
    prog["installed_quantity"] = prog["cumulative_installed_quantity"].diff().fillna(prog["cumulative_installed_quantity"])
    return prog[["day", "installed_quantity", "cumulative_installed_quantity"]]


def summarize(schedule: pd.DataFrame) -> dict:
    if schedule.empty:
        return {"duration_days": 0, "installed_elements": 0, "total_delay_days": 0, "delayed_elements": 0}
    return {
        "duration_days": int(schedule["finish_day"].max()),
        "installed_elements": int(schedule["quantity"].sum()),
        "total_delay_days": int(schedule["delay_days"].sum()),
        "delayed_elements": int((schedule["delay_days"] > 0).sum()),
    }

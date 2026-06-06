from __future__ import annotations

import numpy as np
import pandas as pd

TASK_ORDER = {
    "Install columns": 1,
    "Install walls": 2,
    "Install members": 2,
    "Install beams": 3,
    "Install slabs": 4,
    "Install elements": 5,
}

REQUIRED_COLUMNS = ["guid", "name", "ifc_type", "storey", "zone", "task", "quantity"]


def normalize_elements(df: pd.DataFrame) -> pd.DataFrame:
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    out = df[REQUIRED_COLUMNS].copy()
    out["guid"] = out["guid"].astype(str)
    out["name"] = out["name"].astype(str)
    out["ifc_type"] = out["ifc_type"].astype(str)
    out["storey"] = pd.to_numeric(out["storey"], errors="coerce").fillna(1).astype(int)
    out["zone"] = out["zone"].fillna("A").astype(str)
    out["task"] = out["task"].fillna("Install elements").astype(str)
    out["quantity"] = pd.to_numeric(out["quantity"], errors="coerce").fillna(1).clip(lower=1)
    out["task_order"] = out["task"].map(TASK_ORDER).fillna(99).astype(int)
    return out.sort_values(["storey", "zone", "task_order", "ifc_type", "name"]).reset_index(drop=True)


def aggregate_elements(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate many IFC objects into installable work packages.

    Large production IFCs may contain tens of thousands of objects. For a first
    Streamlit pilot, it is safer to simulate work packages rather than every bolt,
    plate, assembly, or member as a separate visual row.
    """
    norm = normalize_elements(df)
    group_cols = ["storey", "zone", "task", "ifc_type"]
    grouped = (
        norm.groupby(group_cols, dropna=False, as_index=False)
        .agg(quantity=("quantity", "sum"), element_count=("guid", "count"))
        .sort_values(["storey", "zone", "task", "ifc_type"])
        .reset_index(drop=True)
    )
    grouped["guid"] = grouped.apply(
        lambda r: f"GROUP-S{r['storey']}-Z{r['zone']}-{r['task']}-{r['ifc_type']}", axis=1
    )
    grouped["name"] = grouped.apply(
        lambda r: f"{r['task']} | {r['ifc_type']} | S{r['storey']} | Zone {r['zone']} ({int(r['element_count'])} objs)",
        axis=1,
    )
    return grouped[["guid", "name", "ifc_type", "storey", "zone", "task", "quantity"]]


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

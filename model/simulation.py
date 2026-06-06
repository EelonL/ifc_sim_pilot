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


def normalize_elements(df: pd.DataFrame) -> pd.DataFrame:
    required = ["guid", "name", "ifc_type", "storey", "zone", "task", "quantity"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    out = df[required].copy()
    out["storey"] = pd.to_numeric(out["storey"], errors="coerce").fillna(1).astype(int)
    out["zone"] = out["zone"].astype(str).fillna("A")
    out["quantity"] = pd.to_numeric(out["quantity"], errors="coerce").fillna(1)
    out["task_order"] = out["task"].map(TASK_ORDER).fillna(99).astype(int)
    return out.sort_values(["storey", "zone", "task_order", "name"]).reset_index(drop=True)


def run_simulation(
    elements: pd.DataFrame,
    scenario_name: str,
    crew_count: int,
    crane_count: int,
    elements_per_crew_per_day: int,
    delivery_reliability: float,
    rework_probability: float,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run a simple discrete-day frame installation simulation.

    The pilot rule is deliberately transparent:
    - lower storey before higher storey
    - within each storey and zone: columns/walls/members -> beams -> slabs
    - daily capacity = min(crew capacity, crane capacity)
    - delivery and rework add stochastic waiting days
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
        if capacity_left <= 0:
            current_day += 1
            capacity_left = daily_capacity

        delivery_wait = 0 if rng.random() <= delivery_reliability else int(rng.integers(1, 4))
        rework_wait = int(rng.integers(1, 3)) if rng.random() <= rework_probability else 0
        start_day = current_day + delivery_wait
        finish_day = start_day + rework_wait

        delay_reason = []
        if delivery_wait:
            delay_reason.append("delivery")
        if rework_wait:
            delay_reason.append("rework")

        scheduled.append(
            {
                **row.to_dict(),
                "scenario": scenario_name,
                "start_day": start_day,
                "finish_day": finish_day,
                "delay_days": delivery_wait + rework_wait,
                "delay_reason": ", ".join(delay_reason) if delay_reason else "",
            }
        )
        capacity_left -= 1

    schedule = pd.DataFrame(scheduled)
    max_day = int(schedule["finish_day"].max()) if not schedule.empty else 0
    status_rows = []
    for day in range(1, max_day + 1):
        tmp = schedule.copy()
        tmp["day"] = day
        tmp["status"] = np.select(
            [
                tmp["finish_day"] <= day,
                (tmp["start_day"] <= day) & (tmp["finish_day"] > day),
            ],
            ["installed", "in_progress"],
            default="waiting",
        )
        status_rows.append(tmp)
    status_by_day = pd.concat(status_rows, ignore_index=True) if status_rows else pd.DataFrame()
    return schedule, status_by_day


def summarize(schedule: pd.DataFrame) -> dict:
    if schedule.empty:
        return {"duration_days": 0, "installed_elements": 0, "total_delay_days": 0, "delayed_elements": 0}
    return {
        "duration_days": int(schedule["finish_day"].max()),
        "installed_elements": int(len(schedule)),
        "total_delay_days": int(schedule["delay_days"].sum()),
        "delayed_elements": int((schedule["delay_days"] > 0).sum()),
    }

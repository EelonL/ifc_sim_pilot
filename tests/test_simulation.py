import pandas as pd

from model.simulation import aggregate_elements, run_simulation, summarize


def element_rows(count: int, quantity: int = 1) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "guid": f"E{index}",
                "name": f"Element {index}",
                "ifc_type": "IfcBeam",
                "storey": 1,
                "zone": "A",
                "task": "Install beams",
                "quantity": quantity,
            }
            for index in range(count)
        ]
    )


def test_daily_capacity_is_shared_across_small_packages() -> None:
    schedule = run_simulation(
        element_rows(10),
        scenario_name="capacity check",
        crew_count=1,
        crane_count=1,
        elements_per_crew_per_day=4,
        delivery_reliability=1.0,
        rework_probability=0.0,
        seed=42,
    )

    installed_per_day = schedule.groupby("finish_day")["quantity"].sum()

    assert summarize(schedule)["duration_days"] == 3
    assert installed_per_day.to_dict() == {1: 4, 2: 4, 3: 2}
    assert installed_per_day.max() <= 4


def test_crane_capacity_is_the_bottleneck() -> None:
    elements = element_rows(1, quantity=16)

    one_crane = run_simulation(
        elements,
        "one crane",
        crew_count=2,
        crane_count=1,
        elements_per_crew_per_day=4,
        delivery_reliability=1.0,
        rework_probability=0.0,
    )
    two_cranes = run_simulation(
        elements,
        "two cranes",
        crew_count=2,
        crane_count=2,
        elements_per_crew_per_day=4,
        delivery_reliability=1.0,
        rework_probability=0.0,
    )

    assert summarize(one_crane)["duration_days"] == 4
    assert summarize(two_cranes)["duration_days"] == 2


def test_aggregation_retains_mean_placement() -> None:
    elements = element_rows(2)
    elements["x"] = [0.0, 10.0]
    elements["y"] = [2.0, 6.0]
    elements["z"] = [4.0, 4.0]

    grouped = aggregate_elements(elements)

    assert len(grouped) == 1
    assert grouped.loc[0, "quantity"] == 2
    assert grouped.loc[0, "x"] == 5.0
    assert grouped.loc[0, "y"] == 4.0
    assert grouped.loc[0, "z"] == 4.0

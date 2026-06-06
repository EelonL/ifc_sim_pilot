# IFC Frame Simulation Pilot

A lightweight Streamlit pilot for connecting IFC model objects to a simple production simulation.

## What it does

- Reads frame/structure-like IFC objects with IfcOpenShell.
- Shows IFC diagnostics: entity counts and which classes the pilot uses.
- Optionally aggregates thousands of IFC objects into work packages.
- Runs a simple scenario simulation with crews, cranes, installation rate, delivery reliability and rework probability.
- Exports results to Excel.

## Why aggregation is the default

Real IFC files may contain tens of thousands of elements. Simulating and drawing every object as a separate timeline row can make Streamlit slow or memory-heavy. For the first pilot, the recommended mode is:

```text
IFC objects -> work packages by storey + zone + task + IFC type -> simulation
```

## Deploy on Streamlit Community Cloud

1. Push this repository to GitHub.
2. In Streamlit Community Cloud, select this repository.
3. Set the main file to `app.py`.
4. Deploy.

The repository includes `runtime.txt` with Python 3.12.

## Local run

```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
streamlit run app.py
```

## Input CSV columns

CSV mode expects:

```text
guid,name,ifc_type,storey,zone,task,quantity
```

## Current limitations

- No 3D geometry viewer yet.
- No true construction sequencing from geometry.
- Storey and zone inference is still rough.
- The simulation is intentionally transparent and simple.

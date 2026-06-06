from __future__ import annotations

from io import BytesIO
import pandas as pd
import plotly.express as px
import streamlit as st

from bim.ifc_reader import read_ifc_elements, diagnose_ifc
from model.simulation import (
    run_simulation,
    summarize,
    normalize_elements,
    aggregate_elements,
    status_for_day,
    progress_by_day,
)

st.set_page_config(page_title="IFC Frame Simulation Pilot", layout="wide")

st.title("IFC-pohjainen runkosimulaatio — pilotti")
st.caption("Kevyt versio: IFC/CSV → runko-osat tai työpaketit → skenaario → eteneminen")

@st.cache_data
def load_sample_elements() -> pd.DataFrame:
    return pd.read_csv("data/sample_elements.csv")

@st.cache_data
def load_sample_scenarios() -> pd.DataFrame:
    return pd.read_csv("data/scenarios.csv")

with st.sidebar:
    st.header("1. Lähtödata")
    data_mode = st.radio("Valitse lähtödata", ["Esimerkkidata", "Lataa IFC", "Lataa oma CSV"])
    uploaded = None
    if data_mode == "Lataa IFC":
        uploaded = st.file_uploader("IFC-tiedosto", type=["ifc"])
        aggregate_ifc = st.checkbox("Ryhmittele IFC-objektit työpaketeiksi", value=True)
        max_objects = st.number_input(
            "Enintään luettavia IFC-objekteja ennen ryhmittelyä",
            min_value=100,
            max_value=100000,
            value=25000,
            step=100,
        )
    elif data_mode == "Lataa oma CSV":
        uploaded = st.file_uploader("CSV, jossa sarakkeet guid,name,ifc_type,storey,zone,task,quantity", type=["csv"])
        aggregate_ifc = False
        max_objects = None
    else:
        aggregate_ifc = False
        max_objects = None

    st.header("2. Skenaario")
    scenarios = load_sample_scenarios()
    selected = st.selectbox("Valmis skenaario", scenarios["scenario"].tolist())
    row = scenarios.loc[scenarios["scenario"] == selected].iloc[0]

    crew_count = st.number_input("Työryhmien määrä", 1, 10, int(row["crew_count"]))
    crane_count = st.number_input("Nosturien määrä", 1, 10, int(row["crane_count"]))
    rate = st.number_input("Elementtiä / työryhmä / päivä", 1, 500, int(row["elements_per_crew_per_day"]))
    delivery_reliability = st.slider("Toimitusvarmuus", 0.0, 1.0, float(row["delivery_reliability"]), 0.01)
    rework_probability = st.slider("Uudelleentyön todennäköisyys", 0.0, 0.5, float(row["rework_probability"]), 0.01)
    seed = st.number_input("Satunnaissiementä", 1, 9999, 42)

try:
    diagnostics = None
    if data_mode == "Esimerkkidata":
        raw_elements = load_sample_elements()
    elif data_mode == "Lataa IFC" and uploaded is not None:
        diagnostics = diagnose_ifc(uploaded)
        raw_elements = read_ifc_elements(uploaded, max_objects=int(max_objects))
    elif data_mode == "Lataa oma CSV" and uploaded is not None:
        raw_elements = pd.read_csv(uploaded)
    else:
        raw_elements = load_sample_elements()
        st.info("Ladataan toistaiseksi esimerkkidata, kunnes valitset tiedoston.")

    raw_count = len(raw_elements)
    elements = normalize_elements(raw_elements)
    if data_mode == "Lataa IFC" and aggregate_ifc:
        elements = aggregate_elements(elements)
except Exception as exc:
    st.error(f"Lähtödatan lukeminen epäonnistui: {exc}")
    st.stop()

if diagnostics is not None:
    with st.expander("IFC-diagnostiikka: objektityyppien lukumäärät", expanded=False):
        st.write("Pilotin käyttämät IFC-luokat on merkitty sarakkeessa `used_by_pilot`.")
        st.dataframe(diagnostics.head(80), width="stretch")
        supported_total = int(diagnostics.loc[diagnostics["used_by_pilot"], "count"].sum())
        st.info(f"Tästä IFC:stä löytyi tekstidiagnostiikan perusteella {supported_total} pilotin käyttämää rakenne-/runko-objektia.")

if elements.empty:
    st.warning(
        "IFC/CSV luettiin, mutta simulaatioon sopivia rakenneosia ei löytynyt. "
        "Avaa IFC-diagnostiikka ja tarkista, missä IFC-luokissa objektit ovat."
    )
    st.stop()

st.success(f"Lähtödatasta löytyi {raw_count} objektiriviä. Simulaatiossa käytetään {len(elements)} riviä/työpakettia.")

st.subheader("Simulaatioon menevät runko-osat / työpaketit")
st.dataframe(elements.head(1000), width="stretch")
if len(elements) > 1000:
    st.caption("Näytetään ensimmäiset 1000 riviä, jotta selain ei hidastu.")

schedule = run_simulation(
    elements=elements,
    scenario_name=selected,
    crew_count=crew_count,
    crane_count=crane_count,
    elements_per_crew_per_day=rate,
    delivery_reliability=delivery_reliability,
    rework_probability=rework_probability,
    seed=int(seed),
)
summary = summarize(schedule)
progress = progress_by_day(schedule)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Kesto", f"{summary['duration_days']} päivää")
c2.metric("Asennettu määrä", summary["installed_elements"])
c3.metric("Viivepäiviä yhteensä", summary["total_delay_days"])
c4.metric("Viivästyneitä rivejä", summary["delayed_elements"])

st.subheader("Kumulatiivinen eteneminen")
if not progress.empty:
    fig_prog = px.line(progress, x="day", y="cumulative_installed_quantity")
    fig_prog.update_layout(xaxis_title="Simulaatiopäivä", yaxis_title="Asennettu määrä, kumulatiivinen")
    st.plotly_chart(fig_prog, width="stretch")

st.subheader("Aikataulu")
timeline_df = schedule.copy()
if len(timeline_df) > 500:
    st.info("Aikataulussa on paljon rivejä, joten kuvaajassa näytetään 500 ensimmäistä. Excelissä ovat kaikki rivit.")
    timeline_df = timeline_df.head(500)
fig = px.timeline(
    timeline_df,
    x_start="start_day",
    x_end="finish_day",
    y="name",
    color="task",
    hover_data=["ifc_type", "storey", "zone", "quantity", "delay_reason"],
)
fig.update_yaxes(autorange="reversed")
fig.update_layout(xaxis_title="Simulaatiopäivä", yaxis_title="Rakenneosa / työpaketti", height=700)
st.plotly_chart(fig, width="stretch")

st.subheader("Päiväkohtainen tilanne")
if not schedule.empty:
    day = st.slider("Valitse päivä", 1, int(schedule["finish_day"].max()), 1)
    day_df = status_for_day(schedule, day)
    pivot = day_df.groupby(["storey", "zone", "status"], dropna=False)["quantity"].sum().reset_index(name="quantity")
    st.dataframe(day_df[["guid", "name", "ifc_type", "storey", "zone", "task", "quantity", "status", "finish_day", "delay_reason"]].head(1000), width="stretch")
    bar = px.bar(pivot, x="zone", y="quantity", color="status", facet_row="storey", barmode="stack")
    st.plotly_chart(bar, width="stretch")

st.subheader("Lataa tulokset")
output = BytesIO()
with pd.ExcelWriter(output, engine="openpyxl") as writer:
    elements.to_excel(writer, index=False, sheet_name="elements_or_packages")
    schedule.to_excel(writer, index=False, sheet_name="schedule")
    progress.to_excel(writer, index=False, sheet_name="progress_by_day")
    if diagnostics is not None:
        diagnostics.to_excel(writer, index=False, sheet_name="ifc_diagnostics")
st.download_button(
    "Lataa Excel",
    data=output.getvalue(),
    file_name="ifc_simulation_results.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

with st.expander("Mitä tämä pilotti tekee ja mitä se ei vielä tee?"):
    st.markdown(
        """
        Tämä versio näyttää peruslogiikan: rakennusosat luetaan IFC:stä tai CSV:stä, ne järjestetään kerroksen, lohkon ja työvaiheen mukaan, ja simulaatio tuottaa etenemisen.

        Suurissa IFC-malleissa kannattaa käyttää työpakettiryhmittelyä. Muuten selain ja Streamlit voivat hidastua, koska yksittäisiä objekteja voi olla kymmeniä tuhansia.

        Tämä ei vielä sisällä oikeaa 3D-geometriavisualisointia, törmäystarkastelua, tarkkaa asennusjärjestystä, logistiikkareittejä tai tuotannonohjauksen optimointia. Ne voidaan lisätä seuraavissa versioissa.
        """
    )

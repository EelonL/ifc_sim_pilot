from __future__ import annotations

from io import BytesIO
import pandas as pd
import plotly.express as px
import streamlit as st

from bim.ifc_reader import read_ifc_elements
from model.simulation import run_simulation, summarize, normalize_elements

st.set_page_config(page_title="IFC Frame Simulation Pilot", layout="wide")

st.title("IFC-pohjainen runkosimulaatio — pilotti")
st.caption("Ensimmäinen kevyt versio: IFC/CSV → runko-osat → skenaario → päiväkohtainen eteneminen")

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
    elif data_mode == "Lataa oma CSV":
        uploaded = st.file_uploader("CSV, jossa sarakkeet guid,name,ifc_type,storey,zone,task,quantity", type=["csv"])

    st.header("2. Skenaario")
    scenarios = load_sample_scenarios()
    selected = st.selectbox("Valmis skenaario", scenarios["scenario"].tolist())
    row = scenarios.loc[scenarios["scenario"] == selected].iloc[0]

    crew_count = st.number_input("Työryhmien määrä", 1, 10, int(row["crew_count"]))
    crane_count = st.number_input("Nosturien määrä", 1, 10, int(row["crane_count"]))
    rate = st.number_input("Elementtiä / työryhmä / päivä", 1, 50, int(row["elements_per_crew_per_day"]))
    delivery_reliability = st.slider("Toimitusvarmuus", 0.0, 1.0, float(row["delivery_reliability"]), 0.01)
    rework_probability = st.slider("Uudelleentyön todennäköisyys", 0.0, 0.5, float(row["rework_probability"]), 0.01)
    seed = st.number_input("Satunnaissiementä", 1, 9999, 42)

try:
    if data_mode == "Esimerkkidata":
        elements = load_sample_elements()
    elif data_mode == "Lataa IFC" and uploaded is not None:
        elements = read_ifc_elements(uploaded)
    elif data_mode == "Lataa oma CSV" and uploaded is not None:
        elements = pd.read_csv(uploaded)
    else:
        elements = load_sample_elements()
        st.info("Ladataan toistaiseksi esimerkkidata, kunnes valitset tiedoston.")

    raw_count = len(elements)
    elements = normalize_elements(elements)
except Exception as exc:
    st.error(f"Lähtödatan lukeminen epäonnistui: {exc}")
    st.stop()

if elements.empty:
    st.warning(
        "IFC/CSV luettiin, mutta simulaatioon sopivia rakenneosia ei löytynyt. "
        "Tämä tarkoittaa yleensä, että IFC:n objektit ovat eri IFC-luokissa kuin pilotin nykyinen lukija etsii, "
        "tai malli on arkkitehti-/talotekniikkamalli ilman runko-osia."
    )
    st.stop()

st.success(f"Lähtödatasta löytyi {len(elements)} simuloitavaa osaa.")
st.subheader("Lähtömallista luetut runko-osat")
st.dataframe(elements, width="stretch")

schedule, status_by_day = run_simulation(
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

c1, c2, c3, c4 = st.columns(4)
c1.metric("Kesto", f"{summary['duration_days']} päivää")
c2.metric("Asennettuja osia", summary["installed_elements"])
c3.metric("Viivepäiviä yhteensä", summary["total_delay_days"])
c4.metric("Viivästyneitä osia", summary["delayed_elements"])

st.subheader("Aikataulu")
fig = px.timeline(
    schedule,
    x_start="start_day",
    x_end="finish_day",
    y="name",
    color="task",
    hover_data=["ifc_type", "storey", "zone", "delay_reason"],
)
fig.update_yaxes(autorange="reversed")
fig.update_layout(xaxis_title="Simulaatiopäivä", yaxis_title="Rakenneosa", height=600)
st.plotly_chart(fig, width="stretch")

st.subheader("Päiväkohtainen eteneminen")
if not status_by_day.empty:
    day = st.slider("Valitse päivä", 1, int(status_by_day["day"].max()), 1)
    day_df = status_by_day[status_by_day["day"] == day]
    pivot = day_df.groupby(["storey", "zone", "status"]).size().reset_index(name="count")
    st.dataframe(day_df[["guid", "name", "ifc_type", "storey", "zone", "task", "status", "finish_day", "delay_reason"]], width="stretch")
    bar = px.bar(pivot, x="zone", y="count", color="status", facet_row="storey", barmode="stack")
    st.plotly_chart(bar, width="stretch")

st.subheader("Lataa tulokset")
output = BytesIO()
with pd.ExcelWriter(output, engine="openpyxl") as writer:
    elements.to_excel(writer, index=False, sheet_name="elements")
    schedule.to_excel(writer, index=False, sheet_name="schedule")
    status_by_day.to_excel(writer, index=False, sheet_name="status_by_day")
st.download_button(
    "Lataa Excel",
    data=output.getvalue(),
    file_name="ifc_simulation_results.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

with st.expander("Mitä tämä pilotti tekee ja mitä se ei vielä tee?"):
    st.markdown(
        """
        Tämä versio näyttää peruslogiikan: rakennusosat luetaan IFC:stä tai CSV:stä, ne järjestetään kerroksen, lohkon ja työvaiheen mukaan, ja simulaatio tuottaa päiväkohtaisen etenemisen.

        Tämä ei vielä sisällä oikeaa 3D-geometriavisualisointia, törmäystarkastelua, tarkkaa asennusjärjestystä, logistiikkareittejä tai tuotannonohjauksen optimointia. Ne voidaan lisätä seuraavissa versioissa.
        """
    )

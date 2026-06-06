from __future__ import annotations

from io import BytesIO
import pandas as pd
import plotly.express as px
import streamlit as st

from bim.ifc_reader import read_ifc_elements, diagnose_ifc, diagnose_materials
from model.simulation import (
    run_simulation,
    summarize,
    normalize_elements,
    filter_elements,
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
        prefer_assemblies = st.checkbox(
            "Käsittele assemblyt asennusyksikköinä",
            value=True,
            help=(
                "Jos esim. teräsristikon osat ovat IfcElementAssemblyn lapsia, "
                "lapsiosia ei lasketa erillisinä asennettavina objekteina."
            ),
        )
        aggregate_ifc = st.checkbox("Ryhmittele IFC-objektit työpaketeiksi", value=True)
        aggregate_by_material = st.checkbox("Pidä materiaalit erillään työpaketeissa", value=True)
        max_objects = st.number_input(
            "Enintään luettavia IFC-objekteja ennen suodatusta/ryhmittelyä",
            min_value=100,
            max_value=100000,
            value=50000,
            step=100,
        )
    elif data_mode == "Lataa oma CSV":
        uploaded = st.file_uploader(
            "CSV, jossa vähintään sarakkeet guid,name,ifc_type,storey,zone,task,quantity",
            type=["csv"],
        )
        prefer_assemblies = False
        aggregate_ifc = False
        aggregate_by_material = True
        max_objects = None
    else:
        prefer_assemblies = False
        aggregate_ifc = False
        aggregate_by_material = True
        max_objects = None

    st.header("2. Skenaario")
    scenarios = load_sample_scenarios()
    selected = st.selectbox("Valmis skenaario", scenarios["scenario"].tolist())
    row = scenarios.loc[scenarios["scenario"] == selected].iloc[0]

    crew_count = st.number_input("Työryhmien määrä", 1, 10, int(row["crew_count"]))
    crane_count = st.number_input("Nosturien määrä", 1, 10, int(row["crane_count"]))
    rate = st.number_input("Asennusyksikköä / työryhmä / päivä", 1, 500, int(row["elements_per_crew_per_day"]))
    delivery_reliability = st.slider("Toimitusvarmuus", 0.0, 1.0, float(row["delivery_reliability"]), 0.01)
    rework_probability = st.slider("Uudelleentyön todennäköisyys", 0.0, 0.5, float(row["rework_probability"]), 0.01)
    seed = st.number_input("Satunnaissiementä", 1, 9999, 42)

try:
    diagnostics = None
    material_diagnostics = None
    if data_mode == "Esimerkkidata":
        raw_elements = load_sample_elements()
    elif data_mode == "Lataa IFC" and uploaded is not None:
        diagnostics = diagnose_ifc(uploaded)
        material_diagnostics = diagnose_materials(uploaded)
        raw_elements = read_ifc_elements(uploaded, max_objects=int(max_objects))
    elif data_mode == "Lataa oma CSV" and uploaded is not None:
        raw_elements = pd.read_csv(uploaded)
    else:
        raw_elements = load_sample_elements()
        st.info("Ladataan toistaiseksi esimerkkidata, kunnes valitset tiedoston.")

    raw_count = len(raw_elements)
    normalized = normalize_elements(raw_elements)
except Exception as exc:
    st.error(f"Lähtödatan lukeminen epäonnistui: {exc}")
    st.stop()

if diagnostics is not None:
    with st.expander("IFC-diagnostiikka: objektityyppien lukumäärät", expanded=False):
        st.write("Pilotin käyttämät IFC-luokat on merkitty sarakkeessa `used_by_pilot`.")
        st.dataframe(diagnostics.head(80), width="stretch")
        supported_total = int(diagnostics.loc[diagnostics["used_by_pilot"], "count"].sum())
        st.info(f"Tästä IFC:stä löytyi tekstidiagnostiikan perusteella {supported_total} pilotin käyttämää rakenne-/runko-objektia.")

if material_diagnostics is not None:
    with st.expander("IFC-diagnostiikka: materiaalit", expanded=True):
        st.dataframe(material_diagnostics.head(80), width="stretch")
        st.caption("Materiaalit luetaan IFC:n IfcRelAssociatesMaterial-suhteista silloin, kun ne ovat saatavilla.")

st.subheader("Rajaukset ennen simulaatiota")
left, right = st.columns(2)
with left:
    available_categories = sorted([x for x in normalized["material_category"].dropna().unique().tolist() if x])
    default_categories = available_categories
    selected_categories = st.multiselect(
        "Materiaalikategoriat",
        available_categories,
        default=default_categories,
        help="Esim. Steel, Concrete, Insulation. Voit rajata mallin vain teräkseen tai betoniin.",
    )
with right:
    material_pool = normalized.loc[normalized["material_category"].isin(selected_categories), "material"].dropna().unique().tolist()
    material_pool = sorted([x for x in material_pool if x])
    selected_materials = st.multiselect(
        "Tarkemmat materiaalit",
        material_pool,
        default=[],
        help="Jätä tyhjäksi, jos kategoriarajaus riittää. Valitse esim. STEEL/S355J2 tai CONCRETE/C30/37.",
    )

filtered = filter_elements(
    normalized,
    material_categories=selected_categories,
    materials=selected_materials,
    prefer_assemblies=prefer_assemblies,
)

if data_mode == "Lataa IFC" and aggregate_ifc:
    elements = aggregate_elements(filtered, include_material=aggregate_by_material)
else:
    elements = filtered

if elements.empty:
    st.warning(
        "Rajauksilla ei jäänyt simuloitavia rakenneosia. "
        "Kokeile palauttaa jokin materiaalikategoria tai poistaa tarkka materiaalirajaus."
    )
    st.stop()

st.success(
    f"Lähtödatasta löytyi {raw_count} objektiriviä. "
    f"Rajauksen jälkeen rivejä on {len(filtered)}. Simulaatiossa käytetään {len(elements)} riviä/työpakettia."
)

if data_mode == "Lataa IFC":
    assembly_children = int((normalized["parent_assembly_guid"] != "").sum())
    if assembly_children:
        st.info(
            f"IFC:ssä löytyi {assembly_children} objektia, jotka ovat IfcElementAssemblyn lapsiosia. "
            "Kun 'Käsittele assemblyt asennusyksikköinä' on päällä, näitä ei lasketa erillisinä asennuksina."
        )

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
c2.metric("Asennettava määrä", summary["installed_elements"])
c3.metric("Viivepäiviä yhteensä", summary["total_delay_days"])
c4.metric("Viivästyneitä rivejä", summary["delayed_elements"])

st.subheader("Kumulatiivinen eteneminen")
if not progress.empty:
    fig_prog = px.line(progress, x="day", y="cumulative_installed_quantity")
    fig_prog.update_layout(xaxis_title="Simulaatiopäivä", yaxis_title="Asennettava määrä, kumulatiivinen")
    st.plotly_chart(fig_prog, width="stretch")

st.subheader("Materiaalikohtainen yhteenveto")
material_summary = (
    elements.groupby(["material_category", "material"], dropna=False)["quantity"]
    .sum()
    .reset_index()
    .sort_values("quantity", ascending=False)
)
st.dataframe(material_summary, width="stretch")

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
    color="material_category",
    hover_data=["ifc_type", "storey", "zone", "task", "quantity", "material", "delay_reason"],
)
fig.update_yaxes(autorange="reversed")
fig.update_layout(xaxis_title="Simulaatiopäivä", yaxis_title="Rakenneosa / työpaketti", height=700)
st.plotly_chart(fig, width="stretch")

st.subheader("Päiväkohtainen tilanne")
if not schedule.empty:
    day = st.slider("Valitse päivä", 1, int(schedule["finish_day"].max()), 1)
    day_df = status_for_day(schedule, day)
    pivot = day_df.groupby(["storey", "zone", "status"], dropna=False)["quantity"].sum().reset_index(name="quantity")
    show_cols = [
        "guid", "name", "ifc_type", "storey", "zone", "task", "quantity",
        "material_category", "material", "status", "finish_day", "delay_reason",
    ]
    st.dataframe(day_df[show_cols].head(1000), width="stretch")
    bar = px.bar(pivot, x="zone", y="quantity", color="status", facet_row="storey", barmode="stack")
    st.plotly_chart(bar, width="stretch")

st.subheader("Lataa tulokset")
output = BytesIO()
with pd.ExcelWriter(output, engine="openpyxl") as writer:
    raw_elements.to_excel(writer, index=False, sheet_name="raw_elements")
    filtered.to_excel(writer, index=False, sheet_name="filtered_elements")
    elements.to_excel(writer, index=False, sheet_name="elements_or_packages")
    schedule.to_excel(writer, index=False, sheet_name="schedule")
    progress.to_excel(writer, index=False, sheet_name="progress_by_day")
    material_summary.to_excel(writer, index=False, sheet_name="material_summary")
    if diagnostics is not None:
        diagnostics.to_excel(writer, index=False, sheet_name="ifc_diagnostics")
    if material_diagnostics is not None:
        material_diagnostics.to_excel(writer, index=False, sheet_name="material_diagnostics")
st.download_button(
    "Lataa Excel",
    data=output.getvalue(),
    file_name="ifc_simulation_results.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

with st.expander("Mitä tämä pilotti tekee ja mitä se ei vielä tee?"):
    st.markdown(
        """
        Tämä versio näyttää peruslogiikan: rakennusosat luetaan IFC:stä tai CSV:stä, ne rajataan materiaalin mukaan, järjestetään kerroksen, lohkon ja työvaiheen mukaan, ja simulaatio tuottaa etenemisen.

        Suurissa IFC-malleissa kannattaa käyttää työpakettiryhmittelyä ja assembly-logiikkaa. Muuten yksittäiset palkin, levyn tai ristikon osat voivat vääristää simulaatiota, vaikka ne työmaalla asennettaisiin yhtenä kokonaisuutena.

        Tämä ei vielä sisällä oikeaa 3D-geometriavisualisointia, törmäystarkastelua, tarkkaa asennusjärjestystä, logistiikkareittejä tai tuotannonohjauksen optimointia. Ne voidaan lisätä seuraavissa versioissa.
        """
    )

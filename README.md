# IFC Frame Simulation Pilot

Kevyt Streamlit-pilotti, jolla kytketään IFC-mallin runko-osat yksinkertaiseen diskreettiin rakennusjärjestyssimulaatioon.

## Ensimmäisen version idea

- IFC tai CSV tuottaa rakenneosat.
- Simulaatio järjestää ne kerroksen, lohkon ja työvaiheen mukaan.
- Käyttäjä valitsee skenaarion: työryhmät, nosturit, asennusnopeus, toimitusvarmuus ja uudelleentyön todennäköisyys.
- Sovellus tuottaa aikataulun, päiväkohtaisen statuksen ja Excel-latauksen.

## Kansiorakenne

```text
.
├── app.py
├── requirements.txt
├── .streamlit/
│   └── config.toml
├── bim/
│   └── ifc_reader.py
├── model/
│   └── simulation.py
├── data/
│   ├── sample_elements.csv
│   └── scenarios.csv
└── outputs/
```

## Paikallinen ajo

```bash
py -m venv .venv
.venv\Scripts\activate
py -m pip install -r requirements.txt
streamlit run app.py
```

Mac/Linux:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
streamlit run app.py
```

## Streamlit Community Cloud

1. Luo GitHub-repositorio.
2. Lisää nämä tiedostot repositorion juureen.
3. Mene osoitteeseen https://share.streamlit.io.
4. Valitse GitHub-repositorio ja entrypointiksi `app.py`.
5. Valitse Python-versioksi mieluiten 3.11 tai 3.12.
6. Deploy.

## CSV-muoto omalle datalle

CSV:ssä pitää olla nämä sarakkeet:

```text
guid,name,ifc_type,storey,zone,task,quantity
```

Esimerkki:

```csv
guid,name,ifc_type,storey,zone,task,quantity
C1,Column A1,IfcColumn,1,A,Install columns,1
B1,Beam A1-A2,IfcBeam,1,A,Install beams,1
S1,Slab A,IfcSlab,1,A,Install slabs,1
```

## Seuraavat kehitysaskeleet

1. IFC-geometrian vienti kevyempään visualisointimuotoon.
2. GUID-kohtainen 3D-väritys statuksen mukaan.
3. Tarkempi riippuvuuslogiikka: pilari → palkki → laatta → seuraava kerros.
4. Nosturin, toimitusten, varastoinnin ja työryhmien agenttipohjainen mallinnus.
5. Useiden skenaarioiden rinnakkainen vertailu.

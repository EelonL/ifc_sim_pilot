# IFC Frame Simulation Pilot

Streamlit-pilotti, jossa IFC- tai CSV-lähtödata muutetaan yksinkertaiseksi runkoasennuksen tuotantosimulaatioksi.

## Uutta v4-versiossa

- Materiaalidiagnostiikka IFC:stä
- Materiaalikategorian mukainen rajaus, esimerkiksi Steel / Concrete / Insulation
- Tarkempi materiaalirajaus, esimerkiksi STEEL/S355J2 tai CONCRETE/C30/37
- Assembly-logiikka: jos osa on `IfcElementAssembly`-kokonaisuuden lapsi, lapsiosaa ei lasketa erillisenä asennuksena, kun asetus on päällä
- Työpakettien ryhmittely voidaan tehdä materiaaleittain

## Paikallinen ajo

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Streamlit Community Cloud

1. Vie tiedostot GitHub-repositorioon.
2. Valitse Streamlit Community Cloudissa `app.py` päämoduuliksi.
3. Käytä mieluiten Python 3.12 -runtimea (`runtime.txt`).

## CSV-sarakkeet

Vähintään:

```text
guid,name,ifc_type,storey,zone,task,quantity
```

Lisäksi v4 ymmärtää nämä vapaaehtoiset sarakkeet:

```text
material,material_category,parent_assembly_guid,parent_assembly_name
```

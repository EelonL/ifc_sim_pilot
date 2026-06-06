# IFC Frame Simulation Pilot v5

Kevyt Streamlit-pilotti, jossa IFC- tai CSV-lähtödata muunnetaan runko-osiksi / työpaketeiksi ja simuloidaan asennuksen etenemistä eri skenaarioissa.

## Uutta v5-versiossa

- Kevyt 3D-statusnäkymä Streamlitissä Plotlyllä.
- Päiväliukusäädin näyttää, mitkä osat / työpaketit ovat valmiita, käynnissä tai odottamassa.
- IFC:stä yritetään lukea likimääräinen `x`, `y`, `z`-sijainti `ObjectPlacement`-tiedosta.
- Jos sijaintia ei löydy, käytetään synteettistä 3D-asettelua, jotta näkymä toimii myös CSV- ja esimerkkidatalla.
- Työpakettien 3D-sijainti muodostetaan ryhmään kuuluvien IFC-objektien sijaintien keskiarvona.

## Asennus paikallisesti

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Streamlit Community Cloud

- Vie tiedostot GitHub-repositorioon.
- Entry point: `app.py`.
- `requirements.txt` asentaa tarvittavat Python-paketit.
- `runtime.txt` pyytää Python 3.12 -ympäristöä.

## Tärkeä rajaus

3D-näkymä ei ole vielä tarkka BIM-geometriaviewer. Se näyttää asennusyksiköt tai työpaketit pisteinä IFC-sijainnin perusteella. Seuraavat mahdolliset kehitysvaiheet ovat bounding box -geometria, glTF/IFC-viewer ja tarkempi GUID-kohtainen väritys.

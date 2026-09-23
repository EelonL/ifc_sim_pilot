# IFC Frame Simulation Pilot v5.2

Streamlit-pilotti, joka muuntaa IFC- tai CSV-lähtödatan rakennusrungon
asennustyöpaketeiksi ja tuottaa yksinkertaisen päiväkohtaisen
tuotantosimulaation.

## Toiminnot

- IFC-, CSV- ja sisäänrakennettu esimerkkiaineisto
- rakenneosien, kerrosten, lohkojen, materiaalien ja assembly-suhteiden luku
- materiaalirajaus ja IFC-objektien ryhmittely työpaketeiksi
- työryhmä- ja nosturikapasiteetin, toimitusvarmuuden sekä uudelleentyön
  huomioiva skenaariosimulaatio
- Gantt-kaavio, kumulatiivinen eteneminen ja päiväkohtainen tilanne
- kevyt 3D-statusnäkymä IFC:n likimääräisten sijoituskoordinaattien perusteella
- tulosten vienti Exceliin

V5.2 sisältää v5-versiossa esitellyn 3D-näkymän ja v5.1:n yhden päivän
aikataulun päivävalitsimen korjauksen. Lisäksi päiväkapasiteetti jaetaan nyt
työpakettien kesken ja ladatun IFC-mallin väliaikaistiedosto poistetaan heti
lukemisen jälkeen.

## Asennus ja käynnistys

Python 3.12 on suositeltu versio.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Streamlit Community Cloudissa sovelluksen entry point on `app.py`.

## Lähtöaineisto

CSV-tiedoston pakolliset sarakkeet ovat:

```text
guid,name,ifc_type,storey,zone,task,quantity
```

Vapaaehtoiset sarakkeet ovat:

```text
material,material_category,parent_assembly_guid,parent_assembly_name,x,y,z
```

IFC-lukija käsittelee tavallisimpia runko- ja rakennusosia, kuten pilareita,
palkkeja, laattoja, seiniä, levyjä ja `IfcElementAssembly`-kokoonpanoja.
Esimerkkiaineisto on synteettinen eikä kuvaa todellista hanketta.

## Simulaatiologiikka

Päiväkapasiteetti lasketaan kaavalla:

```text
min(työryhmien määrä, nosturien määrä) × asennusyksikköä / ryhmä / päivä
```

Työpaketit järjestetään kerroksen, lohkon ja tehtävätyypin perusteella. Pienet
paketit voivat käyttää saman päivän jäljellä olevaa kapasiteettia. Satunnaiset
toimitus- ja uudelleentyöviiveet määräytyvät skenaarioparametrien ja käyttäjän
valitseman satunnaissiemenen perusteella.

Malli on tutkimus- ja demonstraatioprototyyppi. Se ei sisällä kattavaa
riippuvuusverkkoa, työryhmäkohtaista kalenteria, logistiikkareittejä,
törmäystarkastelua eikä tuotannonohjauksen optimointia. Tuloksia ei pidä käyttää
rakennushankkeen toteutusaikatauluna ilman erillistä validointia ja kalibrointia.

## 3D-näkymän rajaus

3D-näkymä käyttää IFC:n `ObjectPlacement`-tietoa ja näyttää elementit pisteinä.
Sijainti on likimääräinen, koska paikallisten koordinaatistojen kiertoja ja
varsinaista IFC-geometriaa ei käsitellä. Jos koordinaatteja ei ole saatavilla,
sovellus muodostaa synteettisen esityksen.

## Tietosuoja

Sovellus käsittelee käyttäjän lataaman IFC-tiedoston palvelimella. Lukemista
varten luotu väliaikaistiedosto poistetaan heti, kun IfcOpenShell on avannut
mallin, eikä sovellus tallenna tiedostoa repoon. Julkiseen Streamlit-palveluun
ei silti pidä ladata luottamuksellista mallia ilman organisaation lupaa ja
palvelun tietosuojakäytäntöjen tarkistamista.

`.gitignore` estää IFC-mallien, paikallisten salaisuuksien ja tuotettujen
tulostiedostojen tavallisen lisäämisen repoon.

## Testit

```bash
pip install -r requirements-dev.txt
pytest
```

Testit tarkistavat muun muassa päiväkapasiteetin toteutumisen,
työryhmä–nosturi-pullonkaulan, 3D-koordinaattien aggregoinnin ja ladatun
IFC-tiedoston väliaikaiskopion poistamisen.

## Lisenssi

Ohjelmisto on julkaistu [MIT-lisenssillä](LICENSE).

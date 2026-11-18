# Hyperliquid logger: navodila za zagon

Program vsako minuto (nastavljivo) prebere izbrane denarnice na Hyperliquidu, shrani podatke v SQLite in jih
pokaže na lokalni strani s grafi skozi čas. Uporablja samo javni Hyperliquid API (brez ključa).

## Kaj potrebujete

- Windows z nameščenim **Python 3.9 ali novejšim** (ukaz `python --version` mora delovati).
- Internetno povezavo do `api.hyperliquid.xyz`.
- Nobenih dodatnih paketov (`pip install` ni potreben).

## Zagon

Odprite PowerShell v mapi projekta (`D:\claude\bojantest\hyperliquid-logger`) in zaženite:

```bash
python app.py
```

ali dvokliknite **`start.cmd`**. Okno pustite odprto: dokler teče, program zbira podatke. Ustavite ga s **Ctrl+C**.

Nato v brskalniku odprite **http://127.0.0.1:8765**. Prva runda traja približno 15 s, do takrat stran kaže
"No data yet". Z drugih naprav v omrežju glejte razdelek "Dostop iz drugih naprav".

## Najprej preverite, da vse deluje

```bash
python app.py --check
```

ali dvokliknite **`check.cmd`**. Izpiše po eno vrstico `OK`, `WARN` ali `FAIL` za: Python, konfiguracijo, vrata,
bazo, dostop do Hyperliquid API-ja, vsako denarnico in zadnje napake v dnevniku. Ob težavi izpiše tudi, kaj
poskusiti. Izhodni status je 0, če nič ni odpovedalo. Preverjanje ne zažene zbiranja in ne piše v pravo bazo.

Primer:

```
OK   Python 3.11.8
OK   config D:\...\config.json: 2 wallet(s), interval 60 s, port 8765
OK   port 8765 is free
OK   database D:\...\hyperliquid.sqlite: 24.1 MB, 612 rounds, last round 18:20:11 (1 min ago)
OK   Hyperliquid API reachable (11 perp dexes, 310 ms)
OK   Wintermute: 133 positions, equity $47,452,311, 2398 open orders, 40 spot balances
OK   BTC short whale: 1 positions, equity $16,310,226, 16 open orders, 0 spot balances
OK   log D:\...\logs\hyperliquid-logger.log: no errors in the last 400 lines
Result: all OK
```

## Dostop iz drugih naprav v lokalnem omrežju

Nastavitev `"host": "0.0.0.0"` v `config.json` (zdaj privzeta v tem projektu) naredi stran dosegljivo tudi z drugih
naprav v istem omrežju (telefon, prenosnik). Ob zagonu program izpiše naslove, na primer:

```
dashboard http://127.0.0.1:8765  http://10.0.0.4:8765  ...
```

Na telefonu (v istem Wi-Fi) odprite naslov z IP-jem računalnika, npr. **http://10.0.0.4:8765**. Računalnik mora teči in biti
prižgan. Če je IP drug, ga pokaže zagonski izpis in `python app.py --check`.

- **Požarni zid:** Windows ob prvem zagonu vpraša, ali sme Python komunicirati v omrežju. Dovolite **zasebna omrežja**.
  Če se telefon kljub temu ne poveže, v Windows Defender Firewall dovolite Python za zasebna omrežja.
- **Ni gesla.** Vsak v vašem omrežju lahko stran vidi. Uporabljajte samo v zaupanja vrednem domačem omrežju (ne v javnem
  Wi-Fi). Stran ne kaže ključev ali gesel, kaže pa podatke o denarnicah, ki jih spremljate.
- **Druge naprave so samo za branje.** Dodajanje in odstranjevanje denarnic deluje samo na računalniku, kjer teče program.
  Če želite urejanje tudi z drugih naprav, nastavite `"allow_remote_edit": true` (velja takoj, brez ponovnega zagona).
- **Zaščita pred tujimi stranmi:** program odgovarja samo na naslove, ki jih pozna (127.0.0.1, `localhost`, ime računalnika,
  njegovi IP-ji). Za dodatno ime (npr. DNS ime v domači mreži) ga dodajte v `"allowed_hosts": ["ime:8765"]`.
- Samo lokalno spet: `"host": "127.0.0.1"` in ponovni zagon.

## Nastavitve (`config.json`)

| Ključ | Pomen | Privzeto |
|---|---|---|
| `interval_seconds` | razmik med zbiranjem (najmanj 5). Razvoj: 60, običajno: 300 (5 min) | 300 |
| `addresses` | denarnice: `address`, `label`, `fills` | prazno |
| `port` | vrata strani | 8765 |
| `host` | `127.0.0.1` = samo ta računalnik, `0.0.0.0` = tudi lokalno omrežje (glej zgoraj) | `127.0.0.1` |
| `allow_remote_edit` | smejo druge naprave dodajati/odstranjevati denarnice | `false` |
| `allowed_hosts` | dodatna imena, pod katerimi je stran dosegljiva | prazno |
| `db` | datoteka baze | `hyperliquid.sqlite` |
| `log_dir`, `log_level` | mapa dnevnika, `DEBUG` (vse) ali `INFO` (brez HTTP klicev) | `logs`, `DEBUG` |

Spremembe `interval_seconds` in denarnic veljajo takoj (program prebere datoteko pred vsako rundo in ob shranjevanju
začne novo). Za `host`, `port`, `db`, `log_dir` in `log_level` program ponovno zaženite.
Denarnice lahko dodajate in odstranjujete tudi na strani z gumbom **Wallets**.

## Kaj se dogaja: izpisi in dnevnik

**Konzola** (okno, v katerem teče program) kaže: zagon, začetek in konec vsake runde, eno vrstico na denarnico
(število pozicij, equity, uPnL), povzetek "N position changes", opozorila in napake. Vsako posamezno spremembo pozicije
in vsak HTTP klic izpišete z `python app.py --verbose`.

**Debug** (gumb v glavi strani) kaže iste dogodke v živo: številko runde, trajanje, odštevanje do naslednje in
dogodke. Kljukica "HTTP calls" prikaže tudi vsak klic z odzivnim časom. Povezava **log file** odpre zadnjih 500 vrstic
dnevnika, tudi iz časa pred zadnjim ponovnim zagonom.

**Dnevnik** je datoteka `logs\hyperliquid-logger.log` (rotira pri 2 MB, 5 kopij).

Vrstica pod naslovom strani kaže čas zadnjega zbiranja in opozori, če je starejše od 2,5 intervala
(`collector looks stalled`) ali če je pri denarnici napaka.

## Napake in kaj storiti

| Sporočilo | Vzrok | Rešitev |
|---|---|---|
| `port 8765 is already in use ...` ob zagonu | že teče druga kopija programa (ali drug program uporablja vrata) | odprite http://127.0.0.1:8765, ustavite drugo kopijo ali v `config.json` spremenite `port` |
| `cannot start with config file ...` | `config.json` ni veljaven JSON | popravite vejico ali narekovaj, zaženite `--check` |
| `cannot reach api.hyperliquid.xyz` | ni interneta, VPN ali požarni zid | preverite povezavo; program poskusi znova v naslednji rundi |
| `rate limited ... HTTP 429` | preveč klicev | povečajte `interval_seconds` ali odstranite denarnico |
| `Hyperliquid server error (HTTP 5xx)` | težava na strani Hyperliquida | običajno mine sama |
| `the database is locked` | drug program ali druga kopija uporablja bazo | zaprite jo |
| `cannot write to the database file` | ni pravic ali je disk poln | preverite mapo in prostor |
| `this address is not allowed - open the dashboard at one of: ...` (403) | stran je odprta pod imenom, ki ga program ne pozna | uporabite enega od naštetih naslovov ali ime dodajte v `allowed_hosts` |
| `changing wallets is only allowed on the computer running the app` (403) | urejanje iz druge naprave | uredite na računalniku ali nastavite `allow_remote_edit` |
| telefon se ne more povezati | požarni zid, drugo omrežje ali `host` je `127.0.0.1` | dovolite Python za zasebna omrežja; isti Wi-Fi; `host: 0.0.0.0` in ponovni zagon |
| `is the address right?` | denarnica nima pozicij, sredstev ali stanj | preverite naslov (0x + 40 znakov) |
| stran je prazna ali se ne osvežuje | star zavihek ali program ne teče | **Ctrl+F5**; preverite okno s programom |
| `unexpected API response format` | Hyperliquid je spremenil odgovor | pošljite izpis iz dnevnika |

Napake pri eni denarnici ne ustavijo zbiranja za ostale. Celoten Python izpis napake (traceback) je v Debug plošči
(miška čez dogodek) in v dnevniku.

## Pogoste stvari

- **Program se ustavi, ko zaprete okno** (ali sejo, v kateri je bil zagnan). Za stalno zbiranje ga zaženite v svojem
  oknu ali kot opravilo ob prijavi v Windows.
- **Baza raste:** pri intervalu 5 minut približno 0,5 GB na mesec (pri 60 s približno 2 GB). Starih podatkov program
  ne briše.
- **Testi:** `python -m unittest`.
- Opis delovanja po zmožnostih je v `openspec\specs\`, tehnični opis v `README.md`.

# MarketVision - Documentazione Tecnica

## Nota di contesto
Questo repository rappresenta una **fase preliminare** del progetto completo descritto nel PDF. L'obiettivo attuale è verificare e validare la **raccolta dati** che costituirà la base informativa del sistema di AI finale. Le componenti di intelligenza artificiale non sono ancora incluse in questa versione del progetto.

## 1. Obiettivo del progetto
MarketVision è una dashboard web per analizzare profili Instagram e contenuti pubblici, con focus su:

- recupero dei post recenti di profili pubblici Instagram;
- calcolo di metriche base come like, commenti, views e frequenza di pubblicazione;
- confronto tra profili;
- analisi normalizzata foto/video;
- lettura degli insights ufficiali dell'account proprietario tramite API Meta/Instagram;
- salvataggio locale degli snapshot storici.

Questa implementazione serve come **pipeline di raccolta e validazione dati** da utilizzare successivamente nei moduli AI del progetto completo.

## 2. Stack tecnologico

### Linguaggio
- **Python**

### Framework / runtime UI
- **Streamlit** per la dashboard interattiva

### Data processing e visualizzazione
- **pandas** per manipolazione dati
- **plotly** per grafici interattivi

### Persistenza locale
- **SQLite** per salvare gli snapshot dei post

### Accesso alle API / scraping
- **requests** per chiamate HTTP
- **instaloader** per lo scraping dei profili pubblici e la gestione sessione Instagram
- **Playwright** come fallback browser-based per alcune pagine/profili Instagram

### Configurazione ambiente
- **python-dotenv** per caricare i segreti da file `.env`

## 3. Struttura del progetto

- `app.py` - interfaccia Streamlit e orchestrazione della dashboard
- `InstaIntegration.py` - logica di acquisizione dati Instagram e calcolo metriche
- `db.py` - gestione SQLite e snapshot storici
- `requirements.txt` - dipendenze Python
- `.env` - segreti e token di configurazione
- `data/marketvision.db` - database locale creato automaticamente

## 4. Librerie usate

### Streamlit
Usata per costruire la UI web, con:
- sidebar di configurazione;
- card metriche;
- tabelle dati;
- grafici Plotly.

### pandas
Usata per:
- convertire i record dei post in DataFrame;
- fare aggregazioni;
- calcolare medie, mediane, rolling mean e confronti tra gruppi;
- costruire dataset per i grafici.

### plotly
Usata per:
- bar chart;
- line chart;
- violin plot;
- visualizzazioni comparative tra profili e tra tipi di post.

### instaloader
Usata per:
- tentare il fetch dei profili pubblici Instagram;
- caricare sessioni salvate;
- leggere cookie di sessione;
- recuperare post e metadati base quando Instagram lo permette.

### requests
Usata per:
- chiamate HTTP dirette alle API Meta Graph;
- chiamate di fallback verso endpoint Instagram web;
- lettura degli insights ufficiali;
- supporto al fallback per profili pubblici.

### Playwright
Usata come fallback quando Instaloader o le richieste HTTP non bastano:
- apertura browser headless;
- lettura della pagina profilo renderizzata;
- estrazione di link ai post e timestamp.

### sqlite3
Usata per il database locale senza dipendenze esterne.

## 5. API e fonti dati

### 5.1 Instagram pubblici
Il progetto usa più strategie per recuperare i post pubblici:

1. **Instaloader** come prima scelta;
2. **fallback HTTP** sulla pagina profilo e su `web_profile_info`;
3. **fallback Playwright** per il rendering browser.

L'obiettivo è ottenere una lista di post con:
- shortcode;
- URL del post;
- tipo post (`photo`, `video`, `reel`, `carousel`);
- data di pubblicazione;
- like;
- commenti;
- views quando disponibili.

### 5.2 Meta Graph API / Instagram Insights
La dashboard usa l'API ufficiale per l'account proprietario.

Endpoint principali:

- `GET /{ig_user_id}/insights`
- `GET /{ig_user_id}/media`
- `GET /{media_id}/insights`

Metriche usate o previste:
- `profile_views`
- `views`
- eventuali metriche media come `engagement`, `reach`, `impressions`, `saved`, `video_views` quando supportate

L'app legge i parametri da:
- `ACCESS_TOKEN`
- `IG_USER_ID`

## 6. Modello dati

### 6.1 Record post
In `InstaIntegration.py` i post vengono rappresentati dal dataclass `PostRecord`.

Campi principali:
- `username`
- `shortcode`
- `post_url`
- `post_type`
- `posted_at`
- `likes`
- `comments`
- `views`
- `caption`

### 6.2 Snapshot storici
Nel database SQLite ogni snapshot salva:
- account;
- shortcode;
- post URL;
- tipo post;
- data pubblicazione;
- likes;
- comments;
- views;
- caption;
- timestamp di snapshot.

## 7. Flusso applicativo

1. L'utente inserisce uno o più profili Instagram nella sidebar.
2. `app.py` chiama `fetch_public_profile_posts()` per ogni profilo.
3. `InstaIntegration.py` prova il fetch tramite Instaloader.
4. Se necessario, il codice usa fallback HTTP o Playwright.
5. I dati vengono normalizzati in `pandas`.
6. La dashboard mostra:
   - metriche sintetiche;
   - grafici;
   - tabella dei post;
   - confronto tra profili;
   - analisi foto vs video;
   - insights account proprietario.
7. I post vengono salvati in SQLite tramite `db.py`.

## 8. Normalizzazione foto/video
Il progetto include un indice comune per confrontare foto e video.

### Scelta metodologica
- Le **views** non vengono usate nel confronto diretto foto/video perché sono una metrica video-only.
- Il confronto comune usa soltanto metriche condivise:
  - like;
  - commenti.

### Metriche derivate
- `z_likes`
- `z_comments`
- `common_appreciation_score` = media degli z-score di like e commenti
- `video_reach_score` = z-score delle views, usato solo per i video

### Grafici principali
- indice medio foto vs video;
- distribuzione dell'indice comune;
- trend temporale dell'indice;
- top post per indice comune;
- copertura views video.

## 9. Gestione della configurazione
Il progetto usa un file `.env` per i segreti e la configurazione.

Variabili principali:
- `ACCESS_TOKEN`
- `IG_USER_ID`
- `IG_LOGIN_USERNAME`
- `IG_LOGIN_PASSWORD`

## 10. Persistenza locale
La persistenza è gestita da `db.py` con SQLite.

Funzioni principali:
- `init_db()`
- `save_posts_snapshot()`
- `fetch_snapshots()`
- `list_accounts()`

Il file database viene creato in:
- `data/marketvision.db`

## 11. Esecuzione locale

### Installazione dipendenze
```bash
pip install -r requirements.txt
```

### Avvio dashboard
```bash
streamlit run app.py
```

## 12. Limiti noti
- Instagram può bloccare alcune richieste o restituire risposte incomplete.
- Le views non esistono per tutte le foto e non vanno forzate.
- I dati pubblici possono variare in base a rate limit, login state e policy di Instagram.
- L'account proprietario deve essere Business o Creator per usare gli insights ufficiali.

## 13. Estensioni future
- per-media insights ufficiali dalla Graph API;
- confronto aggregato per settore o brand;
- salvataggio storico più strutturato con timestamp e versioning;
- esportazione CSV/Excel;
- alert automatici su variazioni anomale dell'engagement.

## 14. Note finali
Il progetto è pensato come prototipo operativo: privilegia l'analisi rapida di profili pubblici e l'uso delle API ufficiali per l'account proprietario, con persistenza locale degli snapshot e una dashboard interattiva.

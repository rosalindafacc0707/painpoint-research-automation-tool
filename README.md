# FFD — Agente di Ricerca Pain-Point (CVC / Content Operations)

Repository di avvio per l'agente che automatizza la produzione di report di
ricerca sui pain-point delle Content Operations di aziende prospect, a
supporto del team sales (soluzioni Content Value Chain / MarTech
nell'ecosistema Adobe).

## Fase attuale: Phase 1 — Prompt Prototyping

Non esiste ancora una pipeline scriptata. L'obiettivo di questa fase è
validare un unico system prompt su 2-3 aziende reali tramite test manuali,
con revisione umana dell'output. Non c'è output strutturato né export Word:
solo iterazione sul prompt.

## Struttura del repository

```
ffd-painpoint-research/
├── README.md
├── .gitignore
├── .env.example
├── .env.development           # config non-segreta (modello, provider, ecc.)
├── requirements.txt
├── config.py                  # modello, provider attivo, versione prompt
├── providers/
│   ├── base.py                # RunResult condiviso tra i provider
│   ├── azure_provider.py      # Azure OpenAI / Azure AI Foundry + web_search_ddg + fetch_url
│   ├── gemini_provider.py     # Google Gemini + web_search_ddg + fetch_url
│   ├── ollama_provider.py     # Modello open-weight locale + web_search_ddg + fetch_url
│   └── mistral_provider.py    # Mistral La Plateforme, a due fasi/due modelli + web_search_ddg + fetch_url
├── mcp_server/
│   └── scraper_server.py      # tool MCP: fetch_url, web_search_ddg
├── prompts/
│   ├── system_prompt_v1.md ... system_prompt_v8.md  # versioni storiche, vedi CHANGELOG.md
│   └── CHANGELOG.md           # storico delle versioni del prompt (PROMPT_VERSION attiva in .env.development)
├── inputs/
│   ├── sample_company_input.md  # template di intake: solo nome azienda + campi opzionali
│   └── moscow/
│       └── FFD_Pain_Point_Research_Automation_MoSCoW_BriefingRequirements.csv
├── scripts/
│   └── run_prompt_test.py     # test manuale: 1 azienda per esecuzione
├── main.py                    # app FastAPI (monta il router + serve frontend/)
├── routers/
│   └── routers.py             # endpoint /painpoint-researcher/*
├── schemas/
│   ├── requests.py            # GenerateMdDocRequest
│   └── responses.py           # GenerateMdDocResponse
├── services/
│   ├── report_service.py      # stessa logica di run_prompt_test.py, richiamabile da FastAPI
│   └── docx_export.py         # converte il markdown del report in un .docx
├── frontend/
│   └── index.html             # UI statica (no build step) che consuma le API sopra
├── outputs/                    # report generati (non committati, vedi .gitignore)
├── docs/
│   └── project_context.md     # contesto e piano di sviluppo del progetto
└── tests/                      # riservato a test futuri
```

## Setup

1. Clona il repo e crea un virtual environment:
   ```
   python -m venv .venv
   source .venv/bin/activate
   ```
2. Installa le dipendenze:
   ```
   pip install -r requirements.txt
   ```
3. Copia `.env.example` in `.env` e inserisci `MISTRAL_API_KEY` (provider di
   default — vedi "Switch di provider" più sotto per le alternative).

## Uso

1. Copia `inputs/sample_company_input.md` e compila **solo** il nome azienda
   (obbligatorio) ed eventualmente i campi opzionali (sito, paese/regione,
   divisione, settore, lente di ricerca). Non serve raccogliere evidenze a
   mano: è l'agente a farlo da sé tramite il web search tool, seguendo il
   piano di ricerca definito nel system prompt.
2. Lancia il test:
   ```
   python scripts/run_prompt_test.py inputs/il_tuo_file.md --company "Nome Azienda"
   ```
3. Lo script usa il provider configurato in `config.py`/`.env.development`
   (default: `mistral`) e il system prompt in
   `prompts/system_prompt_{PROMPT_VERSION}.md`. Versione del prompt,
   "agent version" e data di run vengono iniettate automaticamente dallo
   script. L'output viene stampato a schermo e salvato in `outputs/` come
   `{azienda}_{versione_prompt}_{provider}_{timestamp}.md` **e** come
   `.docx` corrispondente (stesso nome base), generato da
   `services/docx_export.py` — heading, elenchi, tabelle, grassetto/corsivo
   e le citazioni `[Source: ...]` (queste ultime come hyperlink veri e
   propri sull'intero blocco tra parentesi quadre, senza mostrare l'URL)
   vengono convertiti in un vero documento Word, non solo un export testuale.

## Switch di provider: Mistral, Azure OpenAI, Gemini o Ollama

Lo script supporta quattro provider, scelti da `PROVIDER` in
`.env.development` oppure passando `--provider` da riga di comando:

```
# Mistral La Plateforme (default) — vedi "Provider Mistral" più sotto
python scripts/run_prompt_test.py inputs/il_tuo_file.md --provider mistral

# Azure OpenAI / Azure AI Foundry
python scripts/run_prompt_test.py inputs/il_tuo_file.md --provider azure

# Google Gemini
python scripts/run_prompt_test.py inputs/il_tuo_file.md --provider gemini

# Modello open-weight locale via Ollama
python scripts/run_prompt_test.py inputs/il_tuo_file.md --provider ollama
```

Per Gemini imposta `GEMINI_API_KEY` in `.env` e, opzionalmente,
`GEMINI_MODEL` in `.env.development` (default: `gemini-2.5-pro`). Gemini usa
gli stessi due tool MCP locali del provider Azure: `web_search_ddg` per
scoprire fonti e `fetch_url` per leggerle.

### Provider locale open-weight: Ollama + Qwen

Per chiamate senza costi per richiesta usa il provider `ollama`: il modello
gira sul computer, quindi non richiede API key. Su questo MacBook Air M4 con
16 GB di memoria il default raccomandato è `qwen3.5:9b`, scelto perché supporta
tool calling e lascia memoria sufficiente per un contesto di 32k token.

Installa Ollama, avvialo e scarica il modello una sola volta:

```bash
ollama serve
ollama pull qwen3.5:9b
```

Poi esegui il comando con `--provider ollama` oppure imposta
`PROVIDER=ollama` in `.env.development`. Puoi cambiare host, modello, contesto
e temperatura con le variabili `OLLAMA_*` nello stesso file. Il modello è
locale ma il tool `web_search_ddg` continua a interrogare il web per reperire
le fonti; mantieni quindi la revisione umana obbligatoria prima dell'uso
commerciale.

### Provider Mistral

Usa `mistral` per chiamare l'API La Plateforme di Mistral. I limiti di
rate limit per modello di La Plateforme differiscono di due ordini di
grandezza (verificato dal vivo in console): `mistral-large` regge solo
~0.07 richieste/secondo (1 ogni 14s circa) mentre `ministral-8b` regge
~3.13 richieste/secondo. Il loop di ricerca di questo agente (più chiamate
consecutive, una per giro di tool call) satura Large quasi subito (HTTP
429 anche dopo 30s di retry). Per questo il provider `mistral` divide il
lavoro in due fasi con due modelli diversi (`providers/mistral_provider.py`):

1. **Ricerca** (`MISTRAL_RESEARCH_MODEL`, default `ministral-8b-2512`) — il
   loop con i tool (`web_search_ddg`, `fetch_url`) che produce una bozza.
2. **Finalizzazione** (`MISTRAL_SYNTHESIS_MODEL`, default
   `mistral-large-2512`) — un'unica chiamata senza tool che rilegge la
   bozza contro le stesse regole del system prompt e scrive il report
   finale. Una sola chiamata resta ampiamente dentro il rate limit stretto
   di Large, indipendentemente da quanto è stata "a raffica" la fase 1.

Aggiungi `MISTRAL_API_KEY` in `.env` (crea la chiave su console.mistral.ai),
poi seleziona `--provider mistral`. Usa gli stessi due tool MCP locali del
provider Azure/Gemini per la fase di ricerca: `web_search_ddg` per
scoprire fonti e `fetch_url` per leggerle. I due modelli si configurano
con `MISTRAL_RESEARCH_MODEL` / `MISTRAL_SYNTHESIS_MODEL` in
`.env.development`; `MISTRAL_MAX_RETRIES` / `MISTRAL_RETRY_BASE_SECONDS`
controllano il retry-con-backoff su un HTTP 429.

Per usare Azure, dalla pagina della risorsa in Azure AI Foundry servono due
valori (oltre alla API key):

- `AZURE_OPENAI_API_KEY` → in `.env` (è un segreto, come `MISTRAL_API_KEY`)
- `AZURE_OPENAI_ENDPOINT` → in `.env.development`, deve finire in
  **`/openai/v1`** (es. `https://<risorsa>.services.ai.azure.com/openai/v1`)
  — è la superficie OpenAI-compatibile "v1" della risorsa Foundry, confermata
  funzionante; non l'endpoint classico `openai.azure.com` né il project
  endpoint nudo senza `/openai/v1`
- `AZURE_OPENAI_DEPLOYMENT` → in `.env.development`, il nome esatto del
  deployment come appare in Azure AI Foundry → Deployments (non
  necessariamente il nome del modello sottostante)

Nota architetturale: Azure OpenAI non ha un tool di web search integrato
lato server, quindi il path `azure` usa due tool MCP locali (`web_search_ddg`
per scoprire le fonti + `fetch_url` per leggerle) — condivide lo stesso
`mcp_server/scraper_server.py` e lo stesso system prompt degli altri
provider "senza search integrata" (Gemini, Ollama, Mistral).

Scelta implementativa: il provider Azure usa il client `openai.OpenAI`
semplice (non `AzureOpenAI`, non serve `api_version` su questa superficie) e
la **Responses API** (`client.responses.create`), perché è quello che
risulta effettivamente funzionante contro la risorsa Foundry — non la Chat
Completions API usata invece dagli altri provider.

## API FastAPI e frontend

Oltre allo script CLI (`scripts/run_prompt_test.py`), la stessa logica di
generazione è esposta come API tramite `main.py` + `routers/routers.py`, con
un frontend statico a pagina singola (`frontend/index.html`, nessun build
step: HTML/CSS/JS vanilla) che la consuma.

Avvio:

```
uvicorn main:app --reload
```

`main.py` monta `frontend/` come static file alla radice, quindi l'interfaccia
è raggiungibile direttamente su **`http://localhost:8000/`**, sulla stessa
origine dell'API (nessuna configurazione CORS necessaria in questo caso).
È comunque attivo un `CORSMiddleware` permissivo, utile se preferisci servire
`frontend/index.html` da un altro processo durante lo sviluppo (es.
`python -m http.server` su un'altra porta) — in quel caso imposta
`window.RESEARCH_API_BASE` in cima al file prima che venga caricato lo
script, o modifica direttamente il fallback nel file.

Endpoint disponibili (prefisso `/painpoint-researcher`):

- `POST /generate-pain-point-md` — body `GenerateMdDocRequest`
  (`company_name` obbligatorio; `website`, `country_region`, `department`,
  `industry`, `research_lens`, `provider` opzionali). Esegue lo stesso
  agentic loop dello script CLI e salva il report in `outputs/` sia come
  `.md` che come `.docx`. Risponde con `GenerateMdDocResponse` (`filename`,
  `docx_filename`, `company`, `provider`, `model`, `prompt_version`,
  `stop_reason`, `truncated`, `download_url`, `docx_download_url`).
- `GET /download/{filename}` — restituisce il file richiesto (`.md` o
  `.docx`) con il `Content-Type` corretto, come allegato scaricabile.
- `GET /reports` — indice di tutti i report generati, da Supabase (lista
  vuota se non configurato — vedi "Deploy su Render" più sotto).
- `GET /reports/{id}/content` — testo markdown di un report passato.
- `GET /reports/{id}/download?kind=md|docx` — redirect a una signed URL
  Supabase (download diretto dal bucket, mai proxato dal backend).
- `GET /health` — liveness check, non richiede Basic Auth.

Il frontend fa un form di intake (stessi campi di
`inputs/sample_company_input.md`, incluso lo switch di provider), chiama
`generate-pain-point-md`, poi `download/{filename}` sul `.md` per leggere e
renderizzare il contenuto del report a schermo, e tiene uno storico delle
run in `localStorage` del browser (nessun salvataggio server-side oltre ai
file in `outputs/`). Il pulsante "Download .docx" punta invece direttamente
a `docx_download_url`: scarica il file Word generato lato server, non
un export testuale creato nel browser. La vista "in corso" con i passi di
ricerca è puramente cosmetica: il backend risponde con un'unica chiamata
sincrona, non ci sono eventi di progresso reali durante l'esecuzione
dell'agente.

## Deploy su Render (+ Supabase, + Basic Auth)

Oltre all'uso locale descritto sopra, il progetto può girare come piccolo
prodotto interno raggiungibile da un URL, gratis, senza subscription. Tre
pezzi, tutti opzionali e a costo zero:

- **Hosting**: [Render](https://render.com) piano free (no carta di
  credito, HTTPS automatico). Limite noto: l'istanza va in sleep dopo ~15
  minuti di inattività — il primo utilizzo dopo una pausa richiede 30-60s
  di cold start.
- **Provider LLM**: Ollama non è utilizzabile su un host senza GPU/modello
  locale — `render.yaml` usa `mistral` a due fasi/due modelli
  (`ministral-8b-2512` per la ricerca, `mistral-large-2512` per la
  finalizzazione), che non richiede carta di credito (vedi "Provider
  Mistral" più sopra per il perché dello split).
- **Storage persistente + tracking dei report**: [Supabase](https://supabase.com)
  progetto free (Postgres per l'indice dei report + Storage per i file).
  Necessario perché il disco di Render è effimero (si azzera a ogni
  restart/redeploy) — senza questo, i report generati sparirebbero e la
  history resterebbe solo nel browser di chi li ha generati.
- **Accesso**: HTTP Basic Auth (una sola coppia utente/password, in
  variabili d'ambiente) protegge sia la UI sia le API — senza, chiunque
  abbia l'URL può usare il tool.

Nessuna di queste variabili è obbligatoria per l'uso locale descritto nel
resto di questo README: se non impostate, l'app si comporta esattamente
come prima (nessuna regressione).

### Setup Supabase (una tantum)

1. Crea un account e un progetto gratuito su supabase.com.
2. SQL Editor → incolla ed esegui `supabase/schema.sql` (crea la tabella
   `reports`).
3. Storage → New bucket → nome `reports` (deve combaciare con
   `SUPABASE_BUCKET`), **Public bucket disattivato** — tutti i download
   passano da signed URL temporanee generate dal backend
   (`services/storage_service.py`), mai da URL pubbliche permanenti.
4. Project Settings → API → copia `Project URL` (→ `SUPABASE_URL`) e la
   **`service_role` key** (→ `SUPABASE_SERVICE_ROLE_KEY`; **non** la
   `anon` key — la service role serve solo lato backend e non va mai
   esposta al frontend).

### Setup Render (una tantum)

1. Crea un account gratuito su render.com e collega il repository GitHub.
2. New → Blueprint → seleziona questo repo: Render legge `render.yaml` e
   configura automaticamente il servizio (piano free, build/start command,
   health check su `/health`).
3. Nella dashboard del servizio, inserisci a mano i valori dei secret
   marcati `sync: false` in `render.yaml`: `MISTRAL_API_KEY`,
   `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `BASIC_AUTH_USER`,
   `BASIC_AUTH_PASSWORD` (e opzionalmente `TAVILY_API_KEY`).
4. Deploy. L'URL assegnato da Render è quello da condividere con il capo
   — comunica utente/password Basic Auth separatamente (non via email in
   chiaro).

Se questo branch sostituisce un deploy Render esistente basato su un altro
branch, ricollega semplicemente il servizio Render (o il Blueprint) a questo
branch/repo: `render.yaml` verrà riletto automaticamente al prossimo deploy.

## Regole ferree di questa fase

- Un'azienda per esecuzione — mai batch.
- Revisione umana obbligatoria prima che un report raggiunga il team sales.
- Nessun nome reale di stakeholder — solo gruppi di ruolo ipotizzati.
- Nessuna integrazione CRM: output solo come file scaricabile.
- Ogni modifica sostanziale al system prompt richiede un nuovo file
  `prompts/system_prompt_vN.md` e una voce in `prompts/CHANGELOG.md`.

## Origine dei requisiti

I requisiti derivano dal file MoSCoW fornito dal management
(`inputs/moscow/...csv`), organizzato per EPIC: Input & prospect intake,
Evidence & research, CVC analysis framework, Workflow mapping, Deliverable
output, Commercial relevance, Quality control. Il contesto completo del
progetto è in `docs/project_context.md`.

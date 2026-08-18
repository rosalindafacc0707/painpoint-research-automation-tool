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
│   ├── anthropic_provider.py  # Claude + web_search (server-side) + fetch_url
│   ├── azure_provider.py      # Azure OpenAI / Azure AI Foundry + web_search_ddg + fetch_url
│   ├── gemini_provider.py     # Google Gemini + web_search_ddg + fetch_url
│   ├── gemma_provider.py      # Google-hosted Gemma + web_search_ddg + fetch_url
│   ├── ollama_provider.py     # Modello open-weight locale + web_search_ddg + fetch_url
│   ├── groq_provider.py       # GPT-OSS open-weight veloce + web_search_ddg + fetch_url
│   └── mistral_provider.py    # Mistral La Plateforme + web_search_ddg + fetch_url
├── mcp_server/
│   └── scraper_server.py      # tool MCP: fetch_url, web_search_ddg
├── prompts/
│   ├── system_prompt_v1.md    # versione iniziale (superata)
│   ├── system_prompt_v2.md    # seconda versione (superata)
│   ├── system_prompt_v3.md    # versione corrente da validare
│   └── CHANGELOG.md           # storico delle versioni del prompt
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
3. Copia `.env.example` in `.env` e inserisci la tua `ANTHROPIC_API_KEY`.

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
3. Lo script usa il modello configurato in `config.py`
   (default: `claude-sonnet-5`) con il web search tool abilitato, e il
   system prompt in `prompts/system_prompt_v3.md`. Versione del prompt,
   "agent version" e data di run vengono iniettate automaticamente dallo
   script. L'output viene stampato a schermo e salvato in `outputs/` come
   `{azienda}_{versione_prompt}_{provider}_{timestamp}.md` **e** come
   `.docx` corrispondente (stesso nome base), generato da
   `services/docx_export.py` — heading, elenchi, tabelle, grassetto/corsivo
   e le citazioni `[Source: ...]` (queste ultime come hyperlink veri e
   propri sull'intero blocco tra parentesi quadre, senza mostrare l'URL)
   vengono convertiti in un vero documento Word, non solo un export testuale.

## Switch di provider: Anthropic, Azure OpenAI, Gemini, Gemma, Ollama, Groq o Mistral

Lo script supporta sette provider, scelti da `PROVIDER` in `.env.development`
oppure passando `--provider` da riga di comando:

```
# Anthropic (default) — usa Claude + web_search server-side + fetch_url
python scripts/run_prompt_test.py inputs/il_tuo_file.md --provider anthropic

# Azure OpenAI / Azure AI Foundry
python scripts/run_prompt_test.py inputs/il_tuo_file.md --provider azure

# Google Gemini
python scripts/run_prompt_test.py inputs/il_tuo_file.md --provider gemini

# Google-hosted Gemma
python scripts/run_prompt_test.py inputs/il_tuo_file.md --provider gemma

# Modello open-weight locale via Ollama
python scripts/run_prompt_test.py inputs/il_tuo_file.md --provider ollama

# Modello open-weight veloce via Groq
python scripts/run_prompt_test.py inputs/il_tuo_file.md --provider groq

# Mistral La Plateforme
python scripts/run_prompt_test.py inputs/il_tuo_file.md --provider mistral
```

Per Gemini imposta `GEMINI_API_KEY` in `.env` e, opzionalmente,
`GEMINI_MODEL` in `.env.development` (default: `gemini-2.5-pro`). Gemini usa
gli stessi due tool MCP locali del provider Azure: `web_search_ddg` per
scoprire fonti e `fetch_url` per leggerle.

Gemma è ospitato sulla stessa Gemini API e può riutilizzare `GEMINI_API_KEY`;
imposta `GEMMA_API_KEY` solo se desideri una chiave distinta. Il modello si
configura con `GEMMA_MODEL` (default: `gemma-4-26b-a4b-it`).

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

### Provider open-weight veloce: Groq + GPT-OSS 120B

Per la qualità del report senza la lentezza dell'inferenza locale usa
`groq`. Il default `openai/gpt-oss-120b` è un modello open-weight da 120B
servito da Groq a circa 500 token/s, con 131k token di contesto e supporto ai
tool. Aggiungi `GROQ_API_KEY` in `.env`, poi seleziona `--provider groq`.

Non è un servizio illimitato: usa una API key e ha costi e rate limit. Per il
piano Developer documentato, GPT-OSS 120B ha un limite di 250k token/minuto e
1.000 richieste/minuto; per questo prototipo è molto più vicino a “quanto
voglio” rispetto a un endpoint tradizionale, ma non sostituisce un piano
commerciale per un carico continuo.

Un account Groq on-demand può avere un limite iniziale molto più basso (ad
esempio 8k token/minuto). Il provider limita automaticamente output e testo
delle fonti per evitare richieste rifiutate; le variabili GROQ_MAX_COMPLETION_TOKENS,
GROQ_TPM_LIMIT e GROQ_TOOL_RESULT_MAX_CHARS devono essere aumentate solo dopo
un upgrade del piano.

### Provider Mistral

Usa `mistral` per chiamare l'API La Plateforme di Mistral. Il default
`mistral-large-latest` è il modello flagship con supporto al tool calling.
Aggiungi `MISTRAL_API_KEY` in `.env` (crea la chiave su console.mistral.ai),
poi seleziona `--provider mistral`. Usa gli stessi due tool MCP locali del
provider Azure/Gemini: `web_search_ddg` per scoprire fonti e `fetch_url` per
leggerle. Il modello si configura con `MISTRAL_MODEL` in `.env.development`.

Per usare Azure, dalla pagina della risorsa in Azure AI Foundry servono due
valori (oltre alla API key):

- `AZURE_OPENAI_API_KEY` → in `.env` (è un segreto, come `ANTHROPIC_API_KEY`)
- `AZURE_OPENAI_ENDPOINT` → in `.env.development`, deve finire in
  **`/openai/v1`** (es. `https://<risorsa>.services.ai.azure.com/openai/v1`)
  — è la superficie OpenAI-compatibile "v1" della risorsa Foundry, confermata
  funzionante; non l'endpoint classico `openai.azure.com` né il project
  endpoint nudo senza `/openai/v1`
- `AZURE_OPENAI_DEPLOYMENT` → in `.env.development`, il nome esatto del
  deployment come appare in Azure AI Foundry → Deployments (non
  necessariamente il nome del modello sottostante)

Nota architetturale: Claude ha un tool di web search integrato lato server,
Azure no. Per questo il path `azure` usa due tool MCP locali (`web_search_ddg`
per scoprire le fonti + `fetch_url` per leggerle), mentre il path `anthropic`
usa solo `fetch_url` (la scoperta la fa `web_search` di Claude). Entrambi i
path condividono lo stesso `mcp_server/scraper_server.py` e lo stesso system
prompt — quello che cambia è il modello, l'API sottostante (Anthropic
Messages API vs Responses API) e come vengono esposti i tool.

Scelta implementativa: il provider Azure usa il client `openai.OpenAI`
semplice (non `AzureOpenAI`, non serve `api_version` su questa superficie) e
la **Responses API** (`client.responses.create`), perché è quello che
risulta effettivamente funzionante contro la risorsa Foundry — non la Chat
Completions API usata invece per il path open-source/generico.

**Se ricevi `Your credit balance is too low` con il provider Anthropic**: non
è un bug, è il credito API esaurito sull'account collegato alla
`ANTHROPIC_API_KEY` in uso. Vai sulla Anthropic Console
(console.anthropic.com), sezione Plans & Billing, e ricarica il credito o
aggiorna il piano. Nel frattempo puoi continuare a testare il prompt con
`--provider azure`.

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

## Fuori scope per ora

Il piano di sviluppo complessivo prevede una Fase 2 (pipeline scriptata,
output strutturato, export Word) e una Fase 3 (interfaccia interna
semplice, testing con i colleghi sales). L'API FastAPI e il frontend
descritti sopra sono un primo prototipo tecnico in questa direzione, ma
restano strumenti di test interno: niente export Word, nessun testing
strutturato con i colleghi sales, nessuna delle rimanenti "Should"
requirement di Fase 3. Il repository non verrà esteso oltre questo finché
il system prompt non sarà validato su aziende reali.

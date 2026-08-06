# FFD — Agente di Ricerca Pain-Point (CVC / Content Operations)

Repository di avvio per l'agente che automatizza la produzione di report di
ricerca sui pain-point delle Content Operations di aziende prospect, a
supporto del team sales (soluzioni Content Value Chain / MarTech
nell'ecosistema Adobe).

## Fase attuale: Phase 1 — Prompt Prototyping

Non esiste ancora una pipeline scriptata end-to-end (Fase 2). L'obiettivo di
questa fase è validare i prompt su aziende reali tramite test manuali, con
revisione umana obbligatoria dell'output. **Un solo percorso architetturale
è supportato: quello multi-agente** (N agenti di ricerca paralleli, uno per
topic, più un agente di sintesi — vedi "Modalità multi-agente" sotto). Il
vecchio percorso single-agent (un unico system prompt, un'unica chiamata
sequenziale) è stato ritirato — vedi `prompts/CHANGELOG.md` v7 per il
perché; le sue versioni di prompt restano archiviate in
`prompts/_deprecated/` solo per riferimento storico.

## Struttura del repository

```
ffd-painpoint-research/
├── README.md
├── .gitignore
├── .env.example
├── .env.development           # config non-segreta (provider di default, modelli, ecc.)
├── requirements.txt
├── config.py                  # provider/modello per ruolo, versione prompt
├── providers/
│   ├── base.py                # RunResult + registro provider condiviso
│   ├── ollama_provider.py     # Modello open-weight locale — default: nessun rate limit esterno
│   ├── anthropic_provider.py  # Claude + web_search (server-side) + fetch_url
│   ├── azure_provider.py      # Azure OpenAI / Azure AI Foundry + web_search_ddg + fetch_url
│   ├── gemini_provider.py     # Google Gemini + web_search_ddg + fetch_url
│   └── groq_provider.py       # GPT-OSS 120B via Groq — veloce, budget free-tier stretto
├── mcp_server/
│   └── scraper_server.py      # tool MCP: fetch_url (trafilatura), web_search_ddg (Tavily o ddgs)
├── prompts/
│   ├── multiagent_research_prompt.md   # sub-agente di ricerca (1 topic)
│   ├── multiagent_synthesis_prompt.md  # agente di sintesi/scrittura
│   ├── CHANGELOG.md           # storico delle versioni dei prompt
│   └── _deprecated/           # system_prompt_v1.md…v6.md — percorso single-agent ritirato, solo storico
├── inputs/
│   ├── sample_company_input.md  # template di intake: solo nome azienda + campi opzionali
│   └── moscow/
│       └── FFD_Pain_Point_Research_Automation_MoSCoW_BriefingRequirements.csv
├── scripts/
│   └── run_prompt_test.py     # test manuale della pipeline multi-agente: 1 azienda per esecuzione
├── main.py                    # app FastAPI (monta il router + serve frontend/)
├── routers/
│   └── routers.py             # endpoint /painpoint-researcher/*
├── schemas/
│   ├── requests.py            # GenerateMdDocRequestMultiAgent
│   └── responses.py           # GenerateMdDocResponse
├── services/
│   ├── multiagent_service.py  # orchestratore multi-agente: N agenti di ricerca in parallelo + 1 di sintesi
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
3. Il provider di default (`ollama`) è locale e gratuito: non serve nessuna
   API key, basta installare Ollama e scaricare il modello (vedi "Provider
   locale open-weight: Ollama + Qwen" sotto). Copia comunque `.env.example`
   in `.env` se vuoi usare uno degli altri provider (`ANTHROPIC_API_KEY`,
   `GEMINI_API_KEY`, `AZURE_OPENAI_API_KEY`).

## Uso

1. Non serve compilare un file di evidenze: basta il nome azienda
   (obbligatorio) ed eventualmente i campi opzionali (sito, paese/regione,
   divisione, settore, lente di ricerca) — `inputs/sample_company_input.md`
   mostra lo stesso set di campi usati dal form del frontend, a scopo di
   riferimento. È l'agente a fare la ricerca da sé, tramite gli 8 agenti
   paralleli descritti in "Modalità multi-agente" sotto.
2. Lancia il test da riga di comando:
   ```
   python scripts/run_prompt_test.py --company "Nome Azienda"
   python scripts/run_prompt_test.py --company "Nome Azienda" --website acme.com --region EMEA
   ```
3. Lo script esegue `services/multiagent_service.py`: 8 agenti di ricerca in
   parallelo (provider/modello da `RESEARCH_AGENT_PROVIDER`/`_MODEL`) più un
   agente di sintesi (`SYNTHESIS_AGENT_PROVIDER`/`_MODEL`), entrambi
   default a `ollama` in `.env.development`. Versione del prompt, provider
   e data di run vengono iniettate automaticamente. L'output viene stampato
   a schermo e salvato in `outputs/` come
   `{azienda}_{versione_prompt}_multiagent_{timestamp}.md` **e** come
   `.docx` corrispondente (stesso nome base), generato da
   `services/docx_export.py` — heading, elenchi, tabelle, grassetto/corsivo
   e le citazioni `[Source: ...]` (queste ultime come hyperlink veri e
   propri sull'intero blocco tra parentesi quadre, senza mostrare l'URL)
   vengono convertiti in un vero documento Word, non solo un export testuale.

## Switch di provider: Ollama, Gemini, Anthropic, Azure OpenAI o Groq

Ogni ruolo (ricerca / sintesi) sceglie il proprio provider indipendentemente,
da `RESEARCH_AGENT_PROVIDER` / `SYNTHESIS_AGENT_PROVIDER` in
`.env.development`, oppure da riga di comando con
`--research-provider` / `--synthesis-provider`:

```
# Ollama (default per entrambi i ruoli) — locale, gratuito, nessun rate limit esterno
python scripts/run_prompt_test.py --company "Nome Azienda" --research-provider ollama --synthesis-provider ollama

# Google Gemini — free tier, ma rate limit stretto con 8 agenti in parallelo
python scripts/run_prompt_test.py --company "Nome Azienda" --research-provider gemini

# Anthropic — usa Claude + web_search server-side + fetch_url
python scripts/run_prompt_test.py --company "Nome Azienda" --synthesis-provider anthropic

# Azure OpenAI / Azure AI Foundry
python scripts/run_prompt_test.py --company "Nome Azienda" --research-provider azure

# Groq — GPT-OSS 120B su hardware LPU, free tier, molto più veloce di ollama
# ma con il budget gratuito più stretto tra tutti i provider qui
python scripts/run_prompt_test.py --company "Nome Azienda" --research-provider groq
```

### Provider di default: Ollama + Qwen (locale, nessun rate limit)

`ollama` è il default per entrambi i ruoli: il modello gira su questo
computer, quindi non richiede API key **e non ha alcun rate limit esterno**
— gli 8 agenti di ricerca in parallelo si accodano localmente invece di
fallire con un errore di rate limit. Questo è il motivo principale della
scelta: due provider hosted precedentemente usati come default (`groq`,
`gemma`) andavano in rate limit sotto il carico di 8 chiamate simultanee per
report (vedi `prompts/CHANGELOG.md` v8) — `gemma` è stato rimosso del tutto,
`groq` è stato reintrodotto come opt-in puntato su un modello diverso (vedi
sotto).

Su questo MacBook Air M4 con 16 GB di memoria il default raccomandato è
`qwen3.5:9b`, scelto perché supporta tool calling e lascia memoria
sufficiente per un contesto di 32k token.

Installa Ollama, avvialo e scarica il modello una sola volta:

```bash
ollama serve
ollama pull qwen3.5:9b
```

Poi esegui il comando con `--research-provider ollama` (o
`--synthesis-provider ollama`, già il default) oppure imposta
`RESEARCH_AGENT_PROVIDER=ollama` / `SYNTHESIS_AGENT_PROVIDER=ollama` in
`.env.development`. Puoi cambiare host, modello, contesto e temperatura con
le variabili `OLLAMA_*` nello stesso file. Il modello è locale ma il tool
`web_search_ddg` continua a interrogare il web per reperire le fonti;
mantieni quindi la revisione umana obbligatoria prima dell'uso commerciale.
Contropartita del "nessun rate limit": più lento di un provider hosted,
soprattutto con 8 agenti che si accodano sullo stesso modello locale.

### Provider hosted alternativo: Google Gemini

Per Gemini imposta `GEMINI_API_KEY` in `.env` e, opzionalmente,
`GEMINI_MODEL` in `.env.development` (default: `gemini-2.5-pro`). Gemini usa
gli stessi due tool MCP locali del provider Azure: `web_search_ddg` per
scoprire fonti e `fetch_url` per leggerle. Free tier senza carta di credito,
ma il limite di richieste/minuto può essere comunque stretto quando gli 8
agenti di ricerca lo chiamano tutti insieme — se ci finisci contro, torna a
`ollama`.

### Provider hosted più veloce: Groq + GPT-OSS 120B (budget gratuito stretto)

Per Groq imposta `GROQ_API_KEY` in `.env` (chiave gratuita su
console.groq.com, nessuna carta richiesta) e, opzionalmente, `GROQ_MODEL` in
`.env.development` (default: `openai/gpt-oss-120b`, servito sull'hardware
LPU di Groq). Stessa coppia di tool MCP locali di Azure/Gemini:
`web_search_ddg` per scoprire fonti, `fetch_url` per leggerle.

**Perché `openai/gpt-oss-120b` e non `llama-3.3-70b-versatile`**: testato
dal vivo su questo account, il tool-calling di Llama 3.3 su Groq è
inaffidabile — circa 1 richiesta su 6 con i tool attivi genera un tag
pitonico `<function=nome>{...}</function>` invece di una vera tool call
JSON (a volte come errore 400 `tool_use_failed`, a volte in silenzio dentro
`message.content` senza popolare `tool_calls`), indipendentemente da
temperatura, nome o numero di tool. Anche con 3 retry, circa 2 tentativi su
3 fallivano ancora in un test di stress. È lo stesso motivo per cui Groq
consiglia ora `openai/gpt-oss-120b` (o un modello Qwen) al posto dei modelli
Llama per un uso affidabile dei tool. `llama-3.3-70b-versatile` resta
disponibile impostando `GROQ_MODEL` esplicitamente, ma va bene solo per il
ruolo di sintesi (`enable_tools=False`, nessuna tool call), non per la
ricerca, che ha bisogno che ogni tool call vada a buon fine.

È il provider più rapido tra quelli qui, ma ha il budget free-tier più
stretto: circa 30 richieste/minuto e 8.000 token/minuto per questo modello.
`providers/groq_provider.py` gestisce questi limiti così:

- un rate limiter condiviso (`GROQ_RPM_LIMIT`, default `28`) distribuisce
  nel tempo ogni richiesta di questo processo, perché 8 agenti di ricerca
  paralleli che partono tutti nello stesso secondo saturano altrimenti il
  limite RPM all'istante (osservato dal vivo, prima che questo limiter
  esistesse);
- calcola `max_completion_tokens` in base a quanto payload resta nel budget
  configurato (`GROQ_TPM_LIMIT`, default `8000` — il valore osservato in
  concreto su questo account; alzalo se il tuo tier lo permette);
- se il contesto accumulato durante una ricerca (più iterazioni di tool
  call) supera comunque il budget, comprime in-place i risultati `tool` più
  vecchi (prima i risultati di `web_search`, poi quelli di `fetch_url`)
  invece di far fallire la run;
- `GROQ_REASONING_EFFORT` (default `low`, inviato solo se `GROQ_MODEL`
  contiene `gpt-oss`) tiene basso il consumo di token di reasoning nascosto
  di GPT-OSS, per non saturare lo stesso budget TPM già stretto;
- ritenta automaticamente sia gli errori transitori (429/5xx) sia il tag
  pitonico malformato descritto sopra, dato che un nuovo tentativo di solito
  recupera.

Se anche con questi accorgimenti la run va in rate limit, torna a `ollama`
(nessun limite esterno) o valuta un tier Groq a pagamento.

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
usa solo `fetch_url` (la scoperta la fa `web_search` di Claude). Tutti i
provider condividono lo stesso `mcp_server/scraper_server.py` e gli stessi
due prompt multi-agente — quello che cambia è il modello, l'API sottostante
(Anthropic Messages API vs Responses API vs Chat Completions) e come vengono
esposti i tool.

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
`--research-provider ollama --synthesis-provider ollama` (il default).

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

- `POST /generate-pain-point-md-multiagent` — vedi dettagli sotto.
- `GET /download/{filename}` — restituisce il file richiesto (`.md` o
  `.docx`) con il `Content-Type` corretto, come allegato scaricabile.

Il frontend fa un form di intake (stessi campi di
`inputs/sample_company_input.md`, più i selettori provider/modello per
ricerca e sintesi), chiama `generate-pain-point-md-multiagent`, poi
`download/{filename}` sul `.md` per leggere e renderizzare il contenuto del
report a schermo, e tiene uno storico delle run in `localStorage` del
browser (nessun salvataggio server-side oltre ai file in `outputs/`). Il
pulsante "Download .docx" punta invece direttamente a `docx_download_url`:
scarica il file Word generato lato server, non un export testuale creato
nel browser. La vista "in corso" con i passi di ricerca è in parte
cosmetica (i tempi delle singole barre sono simulati), ma riflette il reale
comportamento del backend: gli 8 topic partono in parallelo, poi la
sintesi finale parte solo dopo che tutti hanno risposto.

## Modalità multi-agente: ricerca parallela per topic + agente di sintesi

**N agenti di ricerca paralleli**, uno per ciascuno degli 8 topic del
"Research process" (Marketing transformation programs, Content workflow,
Governance, Global rollout, Embedded teams, Data ownership, Brand
integrity, AI in marketing — vedi `services/multiagent_service.py`),
ognuno con il proprio processo MCP e un contesto limitato al solo suo
topic, seguiti da **un agente di sintesi** che riceve i risultati di tutti
e scrive il report finale (`prompts/multiagent_synthesis_prompt.md`) —
senza tool propri, per non introdurre evidenze non passate dagli agenti di
ricerca.

Ogni ruolo (ricerca / sintesi) usa un provider e un modello configurabili
**indipendentemente**, così puoi scegliere un modello veloce/economico per
gli 8 agenti di ricerca in parallelo e uno più forte per la sintesi finale
(o viceversa, o lo stesso per entrambi):

```bash
# .env.development — default lato server, sovrascrivibili per singola richiesta
RESEARCH_AGENT_PROVIDER=ollama      # provider usato da ognuno degli 8 agenti di ricerca
RESEARCH_AGENT_MODEL=               # vuoto = modello di default di quel provider
SYNTHESIS_AGENT_PROVIDER=ollama     # provider usato dall'agente di sintesi
SYNTHESIS_AGENT_MODEL=
```

Endpoint dedicato:

- `POST /generate-pain-point-md-multiagent` — body `GenerateMdDocRequestMultiAgent`
  (`company_name` obbligatorio; `website`, `country_region`, `department`,
  `industry`, `research_lens`, `research_provider`, `research_model`,
  `synthesis_provider`, `synthesis_model` opzionali — se omessi usano i
  default di `.env.development` sopra). Risponde con `GenerateMdDocResponse`
  (`filename`, `docx_filename`, `company`, `provider`, `model`,
  `prompt_version`, `stop_reason`, `truncated`, `download_url`,
  `docx_download_url`); il campo `provider` riporta entrambi i provider
  usati (`multiagent(research=..., synthesis=...)`).

Nel frontend, i campi opzionali del form espongono direttamente le due
coppie provider/modello (ricerca e sintesi).

Costo di questo approccio rispetto a un singolo agente che facesse tutto in
sequenza: più chiamate al modello (8 di ricerca + 1 di sintesi) e 8
sottoprocessi MCP, in cambio di contesto per-agente limitato (niente
crescita illimitata della conversazione) e di vera parallelizzazione degli 8
topic invece di una ricerca sequenziale — a patto che il provider scelto
possa effettivamente assorbire 8 chiamate quasi simultanee, il motivo per
cui `gemma` è stato rimosso e `groq` era stato rimosso una prima volta
(vedi `prompts/CHANGELOG.md` v8) prima di essere reintrodotto con un budget
di token gestito esplicitamente (vedi sopra); `ollama` (nessun rate limit
esterno) resta il default.

## Regole ferree di questa fase

- Un'azienda per esecuzione — mai batch.
- Revisione umana obbligatoria prima che un report raggiunga il team sales.
- Nessun nome reale di stakeholder — solo gruppi di ruolo ipotizzati.
- Nessuna integrazione CRM: output solo come file scaricabile.
- Ogni modifica sostanziale a uno dei due prompt multi-agente
  (`prompts/multiagent_research_prompt.md`,
  `prompts/multiagent_synthesis_prompt.md`) richiede di incrementare
  `PROMPT_VERSION` (`config.py`) e aggiungere una voce in
  `prompts/CHANGELOG.md`.
- Un solo percorso architetturale è supportato: quello multi-agente. Il
  percorso single-agent è stato ritirato (`prompts/CHANGELOG.md` v7); non
  reintrodurlo senza una decisione esplicita.

## Performance e scelte di provider/scraping (2026-08-06)

Passaggio dedicato a velocità e precisione, senza toccare lo scope del
report (6 step CVC, disciplina delle evidenze, layer commerciale invariati).

**Web scraping — perché non ScrapeGraphAI.** ScrapeGraphAI (e strumenti
simili basati su LLM per l'estrazione) instrada ogni pagina scaricata
attraverso un modello per estrarne la struttura: aggiunge una chiamata al
modello — e quindi latenza e costo — per ogni fonte letta, e confronti
pubblici recenti mostrano risultati meno consistenti di un estrattore
basato su regole su questo tipo di contenuto (titoli/date/testo di pagine
aziendali). `fetch_url` (`mcp_server/scraper_server.py`) resta quindi su
httpx + trafilatura: nessuna chiamata LLM per pagina, quasi istantaneo,
gratuito. Il vero limite non era l'estrazione ma la **scoperta** delle
fonti: `web_search_ddg` passava per un elenco di backend di metasearch
generici (yandex, startpage, yahoo, wikipedia), alcuni dei quali già noti
per fallire (vedi i commenti storici in `scraper_server.py` su
duckduckgo/mojeek/grokipedia/google bloccati). È stata aggiunta l'opzione
**Tavily Search API** (pensata per agenti AI, risultati già puliti e
deduplicati, free tier 1.000 ricerche/mese senza carta di credito): se
`TAVILY_API_KEY` è impostata viene usata come backend primario, altrimenti
il tool ricade automaticamente sul percorso `ddgs` esistente — nessuna
configurazione obbligatoria in più.

**LLM dei due ruoli agente — storia dei cambi di default.** Tre iterazioni
in un giorno, ciascuna motivata da un problema reale riscontrato durante
l'uso:
1. `cerebras` (`providers/cerebras_provider.py`) aggiunto e impostato come
   default — poi tornato indietro perché la sua registrazione richiede un
   metodo di pagamento anche sul piano "free" (v7.1).
2. `groq` diventato default al suo posto — poi rimosso perché in uso reale
   andava in rate limit sotto il carico di 8 agenti paralleli (v8).
3. `gemma` rimosso insieme a `groq` per lo stesso motivo (v8).
`ollama` è ora il default per entrambi i ruoli: è l'unico provider
strutturalmente immune al rate limit, perché non è un servizio esterno —
gli 8 agenti di ricerca in parallelo si accodano sulla stessa istanza
locale invece di fallire. `gemini` resta disponibile come alternativa
hosted più rapida, ma il suo limite di richieste/minuto sul free tier può
avere lo stesso problema sotto 8-way parallelism. `anthropic` e `azure`
restano configurabili per ruolo, per chi preferisce un modello a pagamento.
`cerebras` è stato rimosso definitivamente (2026-08-06): non era mai stato
davvero gratuito, dato che la registrazione richiede un metodo di pagamento
anche sul piano "free". `groq` è stato reintrodotto lo stesso giorno
(`providers/groq_provider.py`), inizialmente puntato su
`llama-3.3-70b-versatile` — ma un test dal vivo su questo account ha
riscontrato tool-calling inaffidabile su quel modello (~1 richiesta su 6
con i tool attivi genera un tag pitonico invece di una vera tool call,
indipendentemente da temperatura/nome/numero di tool; anche con retry circa
2 tentativi su 3 falliscono ancora), quindi il default è stato spostato su
`openai/gpt-oss-120b` (consigliato da Groq stesso per un uso affidabile dei
tool). Sono stati aggiunti anche un budget di token gestito esplicitamente
(stima dei token disponibili prima di ogni richiesta + compattazione dei
risultati `tool` più vecchi quando il contesto accumulato lo eccede), un
rate limiter condiviso per il limite RPM (saturato all'istante da 8 agenti
paralleli che partono nello stesso secondo, prima che questo limiter
esistesse) e un controllo del reasoning effort di GPT-OSS per non saturare
lo stesso budget di token con ragionamento nascosto — insieme, il tentativo
di sopravvivere al carico di 8 agenti paralleli che aveva fatto rimuovere
`groq` la prima volta. Resta comunque il provider con il margine più
stretto tra quelli qui. Verifica sempre le condizioni di registrazione e i
limiti dei piani gratuiti prima di un uso oltre il prototipo: cambiano
senza preavviso.

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
i prompt multi-agente non saranno validati su aziende reali.

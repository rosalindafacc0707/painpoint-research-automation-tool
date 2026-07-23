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
│   └── opensource_provider.py # GPT-OSS/altri via endpoint OpenAI-compatible
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
   `{azienda}_{versione_prompt}_{provider}_{timestamp}.md`.

## Switch di provider: Anthropic vs open-source

Lo script supporta due provider, scelti da `PROVIDER` in `.env.development`
oppure passando `--provider` da riga di comando:

```
# Anthropic (default) — usa Claude + web_search server-side + fetch_url
python scripts/run_prompt_test.py inputs/il_tuo_file.md --provider anthropic

# Open-source — usa un endpoint OpenAI-compatible (es. GPT-OSS via Ollama)
python scripts/run_prompt_test.py inputs/il_tuo_file.md --provider opensource
```

Per usare GPT-OSS in locale via [Ollama](https://ollama.com):
```
ollama pull gpt-oss:20b
ollama serve
```
`OPENSOURCE_BASE_URL` in `.env.development` punta di default a
`http://localhost:11434/v1` (l'endpoint OpenAI-compatible di Ollama). Per
usare invece un provider hosted (Groq, Together, ecc.) basta cambiare
`OPENSOURCE_BASE_URL`, `OPENSOURCE_MODEL` e impostare `OPENSOURCE_API_KEY`
in `.env`.

Nota architetturale: Claude ha un tool di web search integrato lato server,
i modelli open-source no. Per questo il path `opensource` usa due tool MCP
locali (`web_search_ddg` per scoprire le fonti + `fetch_url` per leggerle),
mentre il path `anthropic` usa solo `fetch_url` (la scoperta la fa
`web_search` di Claude). Entrambi i path condividono lo stesso
`mcp_server/scraper_server.py` e lo stesso system prompt — quello che cambia
è solo il modello e come vengono esposti i tool.

**Se ricevi `Your credit balance is too low` con il provider Anthropic**: non
è un bug, è il credito API esaurito sull'account collegato alla
`ANTHROPIC_API_KEY` in uso. Vai sulla Anthropic Console
(console.anthropic.com), sezione Plans & Billing, e ricarica il credito o
aggiorna il piano. Nel frattempo puoi continuare a testare il prompt con
`--provider opensource`.

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
semplice, testing con i colleghi sales). Questo repository copre solo la
Fase 1 e non verrà esteso alle fasi successive finché il system prompt non
sarà validato su aziende reali.

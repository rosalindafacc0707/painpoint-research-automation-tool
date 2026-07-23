# Prompt Changelog

## v1 — 2026-07-23
- Prima bozza del system prompt, derivata dal file MoSCoW (EPIC: Input &
  prospect intake, Evidence & research, CVC analysis framework, Workflow
  mapping, Deliverable output, Commercial relevance, Quality control).
- Codifica: i 6 step CVC obbligatori, pain point come fallimento di un
  job-to-be-done, disciplina delle evidenze (nessuna claim senza fonte),
  divieto di nomi reali, layer commerciale ancorato a evidenze reali.

## v2 — 2026-07-23
- Corretto il flusso di ricerca: l'input dell'utente è solo nome azienda
  (obbligatorio) + campi opzionali (sito, paese/regione, divisione,
  settore, lente di ricerca), come da requisito Must "Single prospect
  intake". L'utente non fornisce più evidenze pre-raccolte.
- Aggiunta sezione "Research process" che istruisce l'agente a cercare
  PRIMA di scrivere (requisito Must "Structured search plan"), con ordine
  dei topic, priorità delle fonti, finestra di recency (24-36 mesi) e
  regola di triangolazione per i pain point principali.
- Aggiunta struttura completa del deliverable (executive summary 8-12
  bullet, tabella pain point con colonne fisse, sezione tooling, "what we
  still do not know", source list, metadata di run) per allinearsi
  all'EPIC "Deliverable output" e "Quality control" del file MoSCoW.
- Lo script di test ora abilita il web search tool lato API invece di
  aspettarsi un file di evidenze compilato a mano.

## v3 — 2026-07-23
- Aggiunto un secondo strumento di ricerca: oltre a `web_search` (scoperta
  delle fonti, lato API), l'agente ora dispone di `fetch_url`, servito da un
  MCP server locale (`mcp_server/scraper_server.py`, httpx + trafilatura) che
  scarica una pagina e ne estrae il testo leggibile principale. Regola di
  disciplina delle evidenze rafforzata: una fonte va letta con `fetch_url`
  prima di citarla, mai citata dal solo snippet di ricerca.
- Sezione "Tools available to you" che distingue esplicitamente scoperta
  (web_search) e lettura (fetch_url), con gestione di ERROR/WARNING.
- Raffinamenti al prompt: gestione del caso divisione/regione specificata,
  pattern ricorrenti di attrito global-to-local nella ricerca, distinzione
  tra "impacted stakeholders" (funzioni content-ops) e "buying committee",
  criteri espliciti per Severity/Confidence, e una sezione "Quality control"
  (merge dei pain point duplicati, niente forzatura di severità alta su ogni
  step CVC).
- Lo script di test (`scripts/run_prompt_test.py`) ora avvia l'MCP server
  come sottoprocesso stdio ed esegue un loop agentico che gestisce sia le
  tool call MCP sia il `pause_turn` del web search lato server.

---

Incrementare questa versione (e creare un nuovo file
`prompts/system_prompt_vN.md`) ogni volta che il system prompt viene
modificato in modo sostanziale. Conservare le versioni precedenti per poter
confrontare gli output durante la Fase 1.

# Prompt Changelog

## v8 — 2026-08-06 — groq and gemma removed as providers
- Both `providers/groq_provider.py` and `providers/gemma_provider.py` are
  removed: in real use, both kept tripping their free-tier rate limits under
  this project's load (8 parallel research agents + 1 synthesis agent per
  report fire enough simultaneous requests to exhaust a low RPM/RPD
  allowance fast). `groq` and `gemma` are dropped from
  `providers/base.py`'s PROVIDER_MODULES, `schemas/requests.py`'s
  ProviderName, config.py, `.env.example`/`.env.development`, the frontend
  provider dropdowns, and `scripts/run_prompt_test.py`'s `--research-provider`/
  `--synthesis-provider` choices. The two module files themselves are moved
  to `providers/_removed/` (kept for reference only, not imported by
  anything) — see the note in that folder if you want to delete them
  outright.
- `RESEARCH_AGENT_PROVIDER`/`SYNTHESIS_AGENT_PROVIDER` now default to
  `ollama`: the only remaining option with NO external rate limit at all,
  since inference runs on this machine — the 8 parallel research agents
  queue locally instead of failing. `gemini` remains available as a faster
  hosted alternative, but its free-tier requests-per-minute cap can hit the
  same wall under 8-way parallelism; `anthropic`, `azure`, and `cerebras`
  (opt-in, see v7.1) are also still configurable per role.
- No change to prompt wording or report scope.

## v7.1 — 2026-08-06 — Cerebras un-defaulted
- Correction to v7 below: Cerebras' signup asks for a payment method even on
  its "free" plan, so it's unsuitable as a no-cost default for this project.
  `providers/cerebras_provider.py` stays in the codebase as an opt-in
  provider, but `RESEARCH_AGENT_PROVIDER`/`SYNTHESIS_AGENT_PROVIDER` default
  back to `groq` (verified free tier, no card required) in both config.py
  and .env.development. (Superseded by v8 above: groq itself was removed
  the same day after also hitting rate limits.)

## v7 — 2026-08-06 — single-agent path retired
- The single-agent system prompt (this file's history below, v1-v6) and its
  test script have been retired: the project now runs ONLY the multi-agent
  architecture (prompts/multiagent_research_prompt.md +
  prompts/multiagent_synthesis_prompt.md, orchestrated by
  services/multiagent_service.py). This isn't a scope change to the report
  itself — the multi-agent prompts already carry forward every rule from v6
  (evidence discipline, the 6 CVC steps, severity/confidence labeling,
  commercial layer) — it removes a second, now-redundant code path
  (scripts/run_prompt_test.py used to load prompts/system_prompt_vN.md
  directly) that added maintenance surface without adding capability.
- `prompts/system_prompt_v1.md` through `v6.md` are preserved under
  `prompts/_deprecated/` for reference (e.g. to diff prompt wording against
  the multi-agent prompts) but are not read by any code path anymore.
- Also in this pass: added a Cerebras provider (providers/cerebras_provider.py)
  as the new default for both agent roles — same open-weight model as the
  Groq provider, run on faster hardware with a more generous free tier — and
  switched source discovery to the Tavily Search API when TAVILY_API_KEY is
  set (mcp_server/scraper_server.py), falling back to the existing
  ddgs-based metasearch when it isn't. Neither change touches prompt wording
  or report scope — see README.md "Performance and provider changes" for the
  rationale on both.

## v6 — 2026-07-28
- Runtime performance pass, no change to research scope or evidence
  standards: added a "Batch independent tool calls" rule to Tools available
  to you, telling the model to request multiple independent searches/reads
  in the same turn instead of one at a time when they don't depend on each
  other. Paired with a code change (providers/*.py, mcp_server/scraper_server.py)
  that now actually executes same-turn tool calls concurrently instead of
  sequentially — without this prompt nudge the model was mostly issuing one
  tool call per turn anyway, leaving that concurrency unused.

## v5 — 2026-07-28
- Diagnosed against the UI/DOCX rendering, not the model output itself: the
  workflow map and opportunity-recommendations lists (numbered top-level
  step/opportunity, sub-bullets for Inputs/Likely handoff/Inference/Evidence
  underneath) were being flattened downstream — the frontend's `mdToHtml`
  and `services/docx_export.py` treated every list line as top-level
  regardless of indentation, and closing the list on the blank line between
  each numbered step made every step reopen its own fresh list, so each one
  displayed as "1." instead of continuing 1, 2, 3... Both renderers were
  rewritten to track nesting depth from leading indentation and to keep a
  numbered list open across blank lines between siblings.
- Added an explicit "Markdown list formatting" rule to Output format: every
  sub-bullet must be indented 4 spaces (never a tab) relative to its parent
  marker, consistently at every nesting level, and a parent item with its
  own sub-detail must stay inside one list block rather than being split
  into separate top-level numbered points. Applied the same nesting
  instruction to the "Workflow mapping" section and to "Opportunity
  recommendations" in Deliverable structure, instead of only the latter.

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

## v4 — 2026-07-23
- Diagnosticato su un report reale (The North Face, provider Azure): il
  titolo di una fonte conteneva un carattere `|` non escapato ("The North
  Face | Case Study"), che rompeva la tabella markdown dei pain point
  durante la conversione in docx, spostando le colonne e facendo perdere in
  silenzio il vero valore di Confidence per una riga. Aggiunta regola
  esplicita in "Output format": mai un `|` letterale dentro una cella di
  tabella, riscrivere il titolo della fonte se necessario.
- Aggiunta regola in "Evidence discipline": se una fonte non ha una data di
  pubblicazione rilevabile (es. una pagina evergreen come careers o brand
  page), scrivere "n.d." invece di sostituire con la data di oggi o di
  accesso — nel report analizzato, 3 fonti su 6 avevano la stessa data
  sospetta (probabilmente fabbricata) invece di "n.d.".
- Corretto anche uno script bug (non del prompt): il refactor per lo switch
  di provider aveva rimosso l'iniezione a runtime di Prompt version / Agent
  version / Date of run nel system prompt — per questo nel report analizzato
  il modello aveva inventato "API research analyst" come Agent version.
  Reintrodotta in scripts/run_prompt_test.py.

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

Incrementare PROMPT_VERSION (config.py) e aggiungere una voce qui ogni volta
che uno dei due prompt multi-agente (`prompts/multiagent_research_prompt.md`,
`prompts/multiagent_synthesis_prompt.md`) viene modificato in modo
sostanziale. Le voci v1-v6 sopra documentano la storia del prompt
single-agent, ormai ritirato — vedi v7.

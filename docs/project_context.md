This project automates a task currently done manually: producing a pain-point research report on a prospect company's Content Operations, used by the sales team to prepare informed outreach (the company sells Content Value Chain / MarTech solutions in the Adobe ecosystem).

Requirements come from a MoSCoW file provided by management (EPICs: Input & prospect intake, Evidence & research, CVC analysis framework, Workflow mapping, Deliverable output, Commercial relevance, Quality control). No prior example report is available — output quality is judged directly against these requirements.

Development plan:

Phase 0 — Alignment (~1 week): confirm API access and review process
Phase 1 — Prompt prototype (2-3 weeks, current phase): validate system prompt on 2-3 real companies, no code pipeline yet
Phase 2 — Alpha (4-5 weeks): scripted pipeline, structured output, Word export
Phase 3 — Beta (4-5 weeks): simple internal interface, remaining "Should" requirements, testing with sales colleagues

Total estimated timeline: ~11-14 weeks to a working Beta.

Guardrails throughout: one company per run (no batch), mandatory human review before any report reaches sales, output as a downloadable file (no CRM integration yet), no real stakeholder names — only hypothesized role groups.
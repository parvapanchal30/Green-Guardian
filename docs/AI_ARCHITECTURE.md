# AI / Intelligence Architecture

## Honesty taxonomy (enforced in code and UI)
| Kind | Meaning | Example | UI label |
|---|---|---|---|
| **RULE** | Deterministic threshold/logic | `last_inspection > 21d` | "Rule" |
| **STATISTICAL** | Simple stats on own data | z-score of health drop, linear trend | "Statistical" |
| **MODEL** | Trained ML / CV model | Disease classifier | "Model vX" + confidence |
| **LLM** | Language reasoning | Explain, summarize, NL query | "AI-generated" |
| **PREDICTION** | Quantitative forecast with interval + version | 90-day survival | range + confidence |
| **RECOMMENDATION** | Suggested action with explanation, produced by any of the above | "Create inspection task" | method badge + "Why?" |

Never label a rule as ML. Never show a prediction without interval/confidence. Never ship mock predictions to production.

## Botanical Operations Agent (MVP)
A worker job per workspace on a schedule (default hourly) and on events (`observation.created`, `task.overdue`):

```
load rule_config → select candidate subjects (asset_state / history windows)
  → evaluate Rule.evaluate(ctx) → [Finding]
  → dedupe (rule, subject, window) vs open/dismissed recommendations
  → write recommendation(explanation, evidence, proposed_action, severity)
  → record job_run stats
```
`Rule` interface: `key`, `params_schema`, `evaluate(context) -> list[Finding]`, `explain(finding) -> str`. Context provides read-only repositories scoped to the workspace; rules never write directly. Acceptance (human) calls the normal Issue/Task services, so all domain invariants and history apply. Auto-acceptance is off by default (possible later per rule with audit).

MVP rules: see PRD §10. Each ships with table-driven unit tests (boundary conditions, dedupe, suppression after dismissal for N days).

## Extension interfaces (defined now, implemented later)
```python
class Detector(Protocol):   # CV/sensor → Observation
    key: str; version: str
    def detect(self, media: Media, asset: AssetRef) -> DetectionResult: ...   # label, confidence, severity, area_pct
class Predictor(Protocol):  # → Prediction (value, lower, upper, confidence, inputs)
    key: str; version: str; kind: str
    def predict(self, subject: SubjectRef, horizon: timedelta) -> Prediction: ...
class Recommender(Protocol):# → Recommendation
    def recommend(self, ctx) -> list[Recommendation]: ...
class WeatherProvider(Protocol): def forecast(...); def observed(...)
class LLMProvider(Protocol): def complete(...)
```
A `ModelRegistry` (table + code) tracks `key, version, kind, trained_on, metrics, status`. Every Prediction/Detection stores `model_key + model_version + inputs` for audit and back-testing against outcomes (resolved issues, harvests, survival).

## Planned capability pipelines
- **Disease:** image → validate → Detector → Observation(source=model, confidence) → (human review if < threshold) → optional Issue → Task.
- **Survival/Growth:** features from `asset_state` + history + weather + inspection gap → baseline (rule-weighted score, labelled RULE) → ML once labelled outcomes exist → Prediction with interval → feeds task priority.
- **Irrigation:** water balance (rain forecast, ET estimate, soil moisture, crop stage) → Recommendation (rule) → later optimizer.
- **Yield/Harvest/Profit:** needs seasons of own data or validated crop models; until then absent.
- **Crop recommendation:** knowledge base + soil/weather/market → ranked list with uncertainty and explanation.
- **LLM layer:** explain recommendations/predictions from structured data (grounded; cite inputs), NL → structured query over the API (never raw SQL), report narrative drafts. LLM output is always labelled and never the sole basis for creating records without human acceptance.

## Data capture for future ML (MVP responsibility)
Capture now: timestamped health/growth/symptom observations, treatments applied + outcomes, costs, harvest quantities, weather snapshots, task completion times, issue resolution outcomes, photos with metadata. Without these records, V2/V3 models cannot be trained or validated.

## Safety & governance
Confidence thresholds, human-in-the-loop for low confidence, "decision support — not a diagnosis" copy for disease output, model version pinned per prediction, kill-switch via `capabilities`, bias/coverage notes per model (species/region it was trained on).

## Implemented: the rule-based Botanical Operations Agent (2026-10-07)

**What it is:** deterministic rules over recorded data → explained, de-duplicated recommendations → a person accepts (creating an issue/task via the normal services) or dismisses (with a reason). **What it is not:** machine learning, prediction, or a language model; the API says so (`AgentRunOut.note`, method labels `rule` / `statistical`, capability technique "Rules + statistics") and the UI shows a method badge and "this is not a prediction".

| Rule | Method | Fires when | Proposes |
|---|---|---|---|
| `critical_health` | rule | latest health score below the critical threshold (default 40) and no open issue | open an issue (high; critical below half the threshold) |
| `health_decline` | statistical | health fell ≥ 15 points between the oldest and newest scores within 14 days (≥ 2 scores), no open issue; the baseline restarts after an issue is resolved | open an issue (medium/high) |
| `inspection_gap` | rule | no observation for > 21 days (a just-registered asset is not overdue) and no open inspection task | create an inspection task |

Behaviour: runs right after each observation (for that asset) and on demand for the workspace; at most one *issue* proposal per asset per run; an open recommendation is never duplicated (partial unique index); a dismissed one is suppressed for 7 days; thresholds come from `workspace.settings.agent` and malformed overrides fall back to defaults. `symptom_cluster` exists in the rules library but is not wired (needs multi-asset issues).

**Weather boundary (ADR-024):** `Agent → WeatherContextProvider (agent-owned port, app/modules/intelligence/ports.py) ← ForecastWeatherContext (adapter) → WeatherService → WeatherProvider → Open-Meteo | mock | future`. The agent package imports nothing from `app.modules.weather` (AST test). No current rule consumes weather; the port and `WeatherContext` (rain next 24 h, rain probability, top-soil moisture, temperature; unknown = `None`, never zero) are in place for the irrigation-deferral rule.

**Extension path unchanged:** `Detector`, `Predictor`, `Recommender` interfaces and model provenance fields as described above; nothing ML-shaped has been added.

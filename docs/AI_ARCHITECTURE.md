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

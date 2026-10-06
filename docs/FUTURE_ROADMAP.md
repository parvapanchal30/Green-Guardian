# Future Roadmap

Evolution (ADR-012; matches the Stage-2 deck):

```
MVP  Operational foundation   →   V2  Prediction   →   V3  Recommendation   →   V4  Optimization
```

Ordering reflects dependency on data and platform maturity, not calendar commitments. Every stage needs real recorded data; the MVP therefore captures time-stamped observations, treatments, costs and outcomes from day one.

## V2 — Prediction (what will happen?)
- **Disease detection** (computer vision): vetted pretrained model first, per-crop fine-tuning later; image → model → Observation → Issue → Task; human review for low confidence.
- **Growth and survival prediction:** baseline statistical → ML once enough outcomes exist; forecast bands in the UI; survival feeds task priority.
- **Yield and harvest prediction:** only once enough of the user's own history (or a validated crop model) exists; ranges with confidence, never point values.
- **Field operations:** PWA offline sync, QR tag scanning, bulk import (CSV/KML/GeoJSON), notifications (email/WhatsApp/push), recurring schedules and SLAs.
- **Platform:** Celery/RQ + Redis workers, SSO/OIDC, i18n (Hindi/Marathi), time-partitioned history tables, PDF reports.

## V3 — Recommendation (what should we do?)
- **Crop recommendation:** soil + weather + location + water + season + market → ranked crops with suitability, expected yield range, cost and profit range, risk, explanation. "Start Project" creates the project and batch.
- **Irrigation recommendation:** water balance from weather, soil moisture, crop and growth stage → recommended volume/time → Create Irrigation Task.
- **Profitability:** yield range × price range − cost (costs captured from task/treatment records since the MVP).
- **LLM layer:** grounded explanations of recommendations/predictions, natural-language questions over the structured API, report narratives.
- **Canopy estimation** (satellite/drone/CV) and canopy projection.

## V4 — Optimization (how should the whole operation run?)
Given land, water, labour, weather, crop economics and risk constraints, determine the best operating strategy: irrigation optimization, maintenance-crew allocation, intervention prioritization with predicted survival uplift, crop-mix/profit optimization. Plus IoT/sensor ingestion, 3D/time-slider map, enterprise multi-org administration, public API and webhooks.

## Standing technical investments
Model registry and back-testing against outcomes; feature store derived from history tables; data-quality dashboards; load testing at municipal scale (1M assets); cost controls for imagery/LLM.

## Open product questions (to resolve with users)
1. Default health scoring: numeric 0–100 vs categorical field input — which do field workers actually use?
2. Survival definition per organization (alive at 90 d? 1 yr?) — configurable.
3. Population batches: how often are individual plants registered inside batches in practice?
4. Preferred notification channel for workers (WhatsApp vs SMS vs app).
5. Basemap/imagery provider and licensing for production.

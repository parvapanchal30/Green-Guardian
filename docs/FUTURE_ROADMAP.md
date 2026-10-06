# Future Roadmap

Ordering reflects dependency on data and platform maturity, not calendar commitments.

## V2 — Intelligence on real data
- **Disease detection** (CV): vetted pretrained model first, per-crop fine-tuning later; Observation → Issue → Task integration; human review for low confidence.
- **Growth & survival forecasting:** baseline statistical → ML when ≥ N outcomes; forecast bands in UI; survival feeds task priority.
- **Irrigation intelligence:** water-balance rules with soil moisture + forecast; Create Irrigation Task.
- **LLM layer:** grounded explanations of recommendations/predictions, NL questions over structured API, report narratives.
- **Field operations:** PWA offline sync, QR tag scanning, bulk import (CSV/KML/GeoJSON), notifications (email/WhatsApp/push), recurring schedules & SLAs.
- **Reports:** PDF with charts, scheduled delivery, donor/impact templates.
- **Platform:** Celery/RQ + Redis workers, SSO/OIDC, audit export, i18n (Hindi/Marathi), time-partitioned history tables.

## V3 — Planning & optimization
- Yield and harvest prediction; revenue/profitability forecasting with market price feeds.
- Crop recommendation (soil + weather + water + season + market + budget) with uncertainty.
- Canopy estimation (satellite/drone/CV), canopy projection, coverage analytics.
- Optimization: irrigation volume/timing, maintenance crew allocation under budget, intervention prioritization with predicted survival uplift, crop-mix/profit optimization.
- IoT/sensor ingestion, 3D/time-slider map, enterprise multi-org administration, public API & webhooks, marketplace/integrations.

## Standing technical investments
Model registry & back-testing against outcomes; feature store derived from history tables; data-quality dashboards; load testing at municipal scale (1M assets); cost controls for imagery/LLM.

## Open product questions (to resolve with users)
1. Default health scoring: numeric 0–100 vs categorical field input — which do field workers actually use?
2. Survival definition per organization (alive at 90 d? 1 yr?) — configurable.
3. Population batches: how often are individual plants registered inside batches in practice?
4. Preferred notification channel for workers (WhatsApp vs SMS vs app).
5. Basemap/imagery provider and licensing for production.

# UX Flows

## 1. Onboarding
Sign up → create organization → **choose mode** (Green Management / Agricultural Production, with one-line explanation each) → name workspace → first project → draw/define first location (field/zone) on map → add first assets (single / quick-add grid / CSV in V2) → land on Home with checklist ("Add assets, record first observation, review attention rules").

## 2. Register asset
Assets → New → pick species/crop (search) → kind auto-set → place pin on map (or "use my location") → planted date, stage (defaults from lifecycle template), label/tag → optional first observation + photo → Save → asset profile. Population batch variant: estimated count + location polygon/field instead of pin.

## 3. Record observation (field, mobile)
Task or asset → "Observe" → health picker (Healthy / Minor / Stressed / Critical + optional 0–100 slider) → symptom chips → growth inputs (mode-specific) → photo(s) → note → Save. Immediate feedback: state updated, "agent re-evaluated" toast if it produced something.

## 4. Attention inbox (Home)
List of open recommendations sorted by severity/age, each with subject, one-line explanation, method badge, **Why?** (inputs), actions **Create task / Create issue / Dismiss**. Accept opens a prefilled sheet (editable) → confirm → entity created and recommendation marked accepted with link.

## 5. Issue lifecycle
Issue detail: header (key, title, severity, state stepper from workflow template), subject + map thumbnail, evidence strip (observations/photos), tasks list ("Add task"), history timeline. Transition control shows only legal next states; requires note for resolve/close. Resolve prompts "Add verification observation" (skippable with reason). Reopen available from Resolved.

## 6. Task execution
My tasks (due-sorted, grouped: Overdue / Today / Upcoming) → task detail (asset, location, issue context, map link) → Start → Complete (+ notes, optional observation, optional cost) → if linked to issue, prompt to move issue to Monitoring/Verified.

## 7. Map exploration
Layer panel (Assets, Health, Issues, Tasks, Boundaries; disabled "Soon": hotspots, soil moisture, irrigation, growth, canopy, survival risk, yield) + filters (stage, health band, species) → click feature → drawer with summary + actions (Observe, Create issue/task) → "Open profile".

## 8. Dashboards
Mode-shaped KPI tiles (each tile: value + basis tooltip or "Not enough data — how to enable") → health distribution chart → attention list → inspection gaps → recent issues/tasks. Agri mode shows Yield/Harvest/Revenue tiles in a "Forecasts — Coming soon" group, not as numbers.

## 9. Future-feature surfaces (all share the pattern)
Page header with technique badge ("Computer vision", "Machine learning", "Optimization") + `Coming soon` · real form/layout with disabled inputs · "What this will do" short description · optional "Notify me" / "Data we're already collecting for this" panel showing readiness (e.g. "42 labelled photos recorded") — **real counts only**.
- *Crop Recommendation:* the planning form (location, area, soil, pH, water, season, market, budget) disabled.
- *Disease Detection:* asset select, upload dropzone, analyze button disabled; result layout skeleton.
- *Growth/Survival/Yield/Harvest:* panel placeholders with "Not enough data / not yet available".
- *Irrigation:* shows real soil moisture/weather if present; recommendation card "Coming soon".

## 10. Error / empty / edge states
Offline banner + queued submissions; empty lists explain the next action; permission-denied view names the role needed; weather/provider failures degrade the tile only; long-running generation shows job status.

## 11. Role views
Worker: My tasks, observe, map. Manager: + issues, tasks assign, agent inbox. Admin/Owner: + settings, members, rules. Viewer: read-only everywhere, no action buttons.

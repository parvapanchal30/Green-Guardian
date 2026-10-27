# Redesign gaps

Things found while building the Field Ledger redesign (ADR-069) that were left for later, so that each phase stays
small. Each phase adds its own section. None of these blocks using the app; they are to be worked through after the
redesign. "Where" names the file or page; "Suggested fix" is a starting point, not a decision.

## Phase 1 · Foundations (ADR-069)

| # | Gap | Where | Suggested fix |
|---|---|---|---|
| G1 | **Text written by the server stays English on the Hindi screen**: suggestion titles and explanations ("Gulmohar #09 health is critical"), activity and timeline lines ("created as todo — Task created", "Observation (health)"), KPI bases and reasons, capability names and techniques, error messages. | API responses shown as-is | Send codes and values from the API and compose the text in the frontend catalogs (already in TODO as "API codes for server-composed text"). |
| G2 | The Hindi catalog has not been reviewed by a native speaker. | `i18n/catalog.hi.ts` | Review session; fix wording in one pass. |
| G3 | Role names are lower case wherever they are shown alone ("owner", "worker"). | `role.*` keys | Capitalise in the catalog, keep lower case only inside sentences. |
| G4 | Dark mode: the map tiles (OpenStreetMap) stay light, and pages not yet redesigned were only spot-checked in dark. | Map, phases 5–6 pages | Dim the tile layer in dark mode; check every page in dark at the end of phase 6. |
| G5 | Dates appear in two styles: the page eyebrows use the browser's long form ("Monday, October 26"), the rest uses "Oct 26, 2026"; the design used "26 Oct". | `i18n` formatters, Home | One date style per language, through `fmt`, everywhere. |

## Phase 2 · Frame and navigation (ADR-070)

| # | Gap | Where | Suggested fix |
|---|---|---|---|
| G6 | Search shows at most five plants, issues and tasks each, with no "see all results", no arrow-key movement through results, and does not find species or places. | `shell/SearchBox.tsx` | A results page; listbox keyboard pattern; add species and locations. |
| G7 | Tasks have no page of their own, so search and "Due next" open the task's issue or plant instead. | Tasks | A task detail panel or page. |
| G8 | The light/dark choice (like the language) is kept in this browser only, not on the account. | `lib/theme.ts` | Store both on the user profile. |
| G9 | The workspace switcher is still a native select; the design shows a button with the mode under the name. | `WorkspaceLayout.tsx` | A small menu button with the same choices. |
| G10 | The desktop menu cannot collapse to icons. | `WorkspaceLayout.tsx` | Optional collapse, remembered per browser. |

## Phase 3 · Today (ADR-071)

| # | Gap | Where | Suggested fix |
|---|---|---|---|
| G11 | Activity lines repeat their type ("Observation" tag, then "Observation: Neem sapling #201"), because the title comes from the server. | Home activity | Part of G1: the API sends the type and subject; the page writes the line. |
| G12 | Recent activity is the server's latest 10 events with no "show more". | `dashboard/service.py` (`ACTIVITY_LIMIT`) | A paged activity endpoint or a link to the audit log for managers. |
| G13 | "Due next" lists every open task, also for field workers, who mostly want their own. | Home | Show "Mine" first for workers, "All open" for managers (as the Tasks page will). |
| G14 | With a location or type filter on, the summary sentence does not say that it covers only that part ("in Zone 4"). | `lib/summary.ts` | Add the filter to the sentence. |

## Phase 4 · Plant page and Record sheet (ADR-072)

| # | Gap | Where | Suggested fix |
|---|---|---|---|
| G15 | The forms inside the Record sheet keep their earlier layout: symptoms are typed as comma-separated text (the design has chips), the phone design's large health-band buttons are not built, and each form still has its own box. | `asset/ObservationForm.tsx`, `ActionPanel.tsx`, `LifecyclePanel.tsx`, `EvidenceGallery.tsx` | Rework the four forms in Field Ledger style (symptom chips from a fixed list plus "Other", band buttons with an optional score). |
| G16 | The timeline marks an observation "with a photo" but shows no thumbnail. | Plant page timeline | Show the small image beside the entry. |
| G17 | Thumbnails download the full image; there are no small image versions. | Evidence storage | Make thumbnails on upload; also needed for photo cards (phase 5). |
| G18 | The chart shows the latest 100 observations only. | `useObservations` | A health-history endpoint with the full series. |
| G19 | "Show on map" opens the map but does not centre on the plant. | Map | Accept a plant in the map address and select it. |
| G20 | The issue card on the plant page does not show "Did the work help?", which the design had. | Plant page | Reuse the verification card. |
| G21 | Opening an issue is still an inline form on the page, not part of the Record sheet. | Plant page | Add "Issue" as a fifth tab, or a sheet of its own. |
| G22 | Correcting a work record opens the correction form inside the narrow side card. | `ActionPanel.tsx` | Open the correction in the Record sheet. |
| G23 | The Record sheet does not say when an observation will count as the follow-up check for an open issue (the design did). | `asset/RecordSheet.tsx` | Read the open issue's verification state and show one line. |
| G24 | The recurring-inspection, growth and lifecycle cards keep their earlier inner styling. | Side cards | Restyle with the building blocks during phase 6. |

## Phase 5 · Lists (ADR-073)

| # | Gap | Where | Suggested fix |
|---|---|---|---|
| G25 | Each photo card asks for its plant's latest photo separately (up to 25 requests per page) and downloads the full image. | `asset/AssetCard.tsx` | Send the latest photo's id with each asset in the list response; serve thumbnails (G17). |
| G26 | On phones the ledger cards show every column, zero counts included, so "All assets" cards are long. | `LedgerTable` | A per-column option to hide a cell on phones when it is empty or zero. |
| G27 | The Cards / Table choice on the kind tabs is not remembered. | `AssetsPage.tsx` | Keep it per browser, like the theme. |
| G28 | Tasks are grouped by due date within one page of 25, so a group can continue on the next page; the tabs show no counts. | `TasksPage.tsx` | Ask the server for counts per group and per tab, or load open work by group. |
| G29 | The Issues page has no category or assignee filter, although the API has both; "Waiting for a check" does not exist for harvest readiness. | `IssuesPage.tsx` | Add the two filters; decide whether "ready" counts as waiting. |
| G30 | Fields and zones counts only plants placed directly in a place, not in the places inside it ("Main campus: 0 living assets" while its zones hold six). | `locations` service | Count down the tree, or show both numbers. |
| G31 | Species and Fields and zones lists are not paged (species loads at most 200). | `SpeciesPage.tsx`, `LocationsPage.tsx` | Page them like Assets. |
| G32 | Inspections due are one list (not grouped by due date) and are completed on the Tasks page, not here. | `InspectionsPage.tsx` | Reuse the Tasks groups and its Complete form. |
| G33 | On phones the table becomes cards through CSS; some screen readers (Safari VoiceOver) may then stop announcing it as a table. | `LedgerTable` | Test with VoiceOver; add explicit table roles if needed. |
| G34 | Task titles on phones wrap in a narrow column because priority and status sit beside them. | `TasksPage.tsx` | Put the chips under the title on phones. |

## Phase 6 · Remaining pages (ADR-074 to ADR-077)

| # | Gap | Where | Suggested fix |
|---|---|---|---|
| G36 | The design's "Agent thresholds" settings tab is not built; thresholds are still set in workspace settings JSON. | Settings | A form over `settings.agent` for owners and admins, with the allowed ranges. |
| G37 | There is no password reset; the sign-in page says so. | Auth | An email reset flow (needs an email provider) or an owner-issued reset link. |
| G38 | The workspaces list shows no counts (plants, open issues, waiting suggestions) as the design did; the list endpoint does not return them. | `WorkspacesPage.tsx`, workspaces API | Add a small summary per workspace to the list response. |
| G39 | Members are added only if they already registered; there is no invitation by email. | Members | Invitations with a link (needs an email provider). |
| G40 | Weather "Work due" and the day counts cover the whole workspace, not only the chosen place. | `WeatherPage.tsx` | Filter tasks by the place (tasks with that location, or assets placed there). |
| G41 | The Rain advice panel repeats the rule's thresholds and default values in the frontend. | `lib/weather.ts` | Return the evaluated rule result from the server for a coordinate. |
| G42 | The weather map has no keyboard way to move the pin precisely (search and "Use my location" are the keyboard paths). | `weather/PinMap.tsx` | Arrow-key nudging, or latitude and longitude fields. |
| G43 | Saved weather places can be renamed only by removing and saving again. | Weather | A rename action. |
| G44 | The issue page, harvests page, dataset and protocol detail pages and the "planned" placeholder pages were not part of this redesign and keep their earlier styling. | `IssueDetailPage.tsx`, `HarvestsPage.tsx`, `DatasetDetailPage.tsx`, `ProtocolsPage.tsx` (detail), `PlannedPage.tsx` | Restyle with the building blocks; the issue page has a design (L-Issue). |
| G45 | Visually hidden text inside a horizontally scrolling area widened phone pages (fixed in Weather, Coming next, the shared table and two report tables by giving the area `position: relative`). | Any new scroll area | Keep `relative` on scroll containers; consider a lint or test for it. |
| G46 | Health and Growth charts are drawn per page; the period switch does not carry over between Health and Growth. | Monitor | Keep the period in the address. |

## Joining a workspace and roles (found in discussion, 2026-10-27)

How it works today: a new account belongs to no workspace. A person either creates a workspace (and becomes its owner)
or is added by an owner or admin under Settings → Members, by the email they registered with; the person adding them
chooses the role. Roles belong to a person in one workspace, so the same person can be an owner in one and a worker or
viewer in another. A viewer sees everything and changes nothing (for example a funder, municipal officer, auditor,
landowner or the college guide).

| # | Gap | Where | Suggested fix |
|---|---|---|---|
| G47 | A new user is not told that someone else can add them to a workspace; the empty page only says to create one, so people may create a duplicate workspace. | `WorkspacesPage.tsx` | An empty state that explains both ways in: ask for a join link, or create a workspace if you manage the plants. |
| G48 | There is no join link or code; the person must register first and then tell the owner their email outside the app (G39 covers email invitations). | Members | Join links created by an owner or admin for a chosen role, with an expiry and a use limit; shareable on WhatsApp, no email provider needed. |
| G49 | Nobody is told when they are added to a workspace; it just appears in their list. | Members | A notice on the next sign-in ("You were added to X as worker by Y"). |
| G50 | A person cannot ask to join a workspace. | Workspaces | A "request access" flow that an owner or admin approves, if join links prove not enough. |
| G51 | Members below admin cannot leave a workspace themselves; only an owner or admin can remove them. | Members | "Leave workspace" for everyone except the last owner. |
| G52 | Handing a workspace over is "add a second owner, then demote yourself", with no guided step. | Members | A transfer-ownership action with confirmation. |
| G53 | What each role can do is explained only on the Members page, which a new user may never open. | Workspaces, account menu | Show the person's role and its one-line meaning on the workspaces list and in the account menu. |

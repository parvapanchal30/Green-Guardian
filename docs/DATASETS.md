# Datasets and data foundations (Stage D)

_Status 2026-10-18. The data foundations are built and tested on **synthetic fixtures only**. **No external dataset has been downloaded, no model has been trained, and no dataset is approved.** Licence statements were read from web pages, not from legal advice; the application records evidence and enforces a policy, it does not decide law._

## 1. Policy (owner decision, 2026-10-18)
- **CC0 and CC BY are accepted provisionally**, subject to verification at the source.
- **CC BY-SA, CC BY-NC, CC BY-ND and unclear licences are excluded.** Any other licence cannot be approved inside the application. There is no override: an exception is a decision the owner records in `DECISION_LOG.md` and a code change, not a setting.
- A dataset is **not downloaded** unless its status is `approved`. The application enforces the part it can: samples of a real dataset cannot be registered, and splits cannot be made, before approval.
- Rights are examined separately for **images** and **annotations**, and for commercial use, redistribution and attribution.
- PlantDoc is **not** assumed approved (see 3).

## 2. What is implemented (all under `backend/app/modules/datasets`)
| Piece | What it does | Where |
|---|---|---|
| Catalog | a record per dataset version: source URL, access date, licence (dataset, images, annotations), attribution, commercial use, redistribution, intended use, status `proposed` > `under_review` > `approved` / `rejected` | `models.py`, `service.py`, 16 API routes under `/workspaces/{ws}/datasets` |
| Licence verification | `licences.py` classifies a licence (eligible / excluded / needs review) and lists every **blocker** to approval; approval by an owner or admin is refused while any remain; the blockers are returned and stored in the approval history | `licences.py` |
| Evidence | append-only rows: URL, kind, scope (images / annotations / both), the licence that source states, a quoted excerpt, whether the source is official, access date, who recorded it | `dataset_evidence` |
| Label review | per-sample states `unreviewed`, `under_review`, `accepted`, `rejected`, `corrected`; every change is an append-only row with reviewer (the signed-in user), timestamp, old and new status and label, written evidence, and the reviewer's *declared* qualification | `review.py`, `label_reviews` |
| Data quality | invalid or truncated files, exact duplicates (SHA-256), near duplicates (64-bit difference hash), duplicates across groups, missing labels, groups and provenance, class imbalance, rare classes, single class, too few groups, review coverage | `quality.py` |
| Grouped splits | whole groups go to one split; deterministic from a seed; greedy label balancing; an independent leakage checker (groups, identical files, near-identical images); a checksummed, append-only, numbered version | `splits.py`, `dataset_splits` |
| Reviewer agreement | Cohen's kappa over samples decided by two different reviewers, from the review history; says it measures consistency, not correctness | `agreement.py`, `GET .../agreement` |
| Evaluation harness | confusion matrix, per-class precision / recall / F1 with Wilson intervals, accuracy next to the majority-class baseline, abstentions counted as errors, calibration error | `evaluation.py` (no model exists; it is exercised with made-up labels) |
| Claim gate | lists what blocks any performance claim today | `evaluation.claim_readiness`, `GET .../claim-readiness` |

Database guarantees (PostgreSQL): evidence, approval history, label reviews and splits reject UPDATE and DELETE; samples and splits cannot reference another tenant's dataset (composite foreign keys); an approved real dataset must have an approver; row-level security on all six tables.

## 3. Candidate datasets: where each stands
Nothing below is approved. "Evidence gathered" means a page was read; the app's catalog is where an owner records and approves it.

| Dataset | Finding | Why it is not approvable now | What would change that |
|---|---|---|---|
| **PlantDoc** | the official repository (github.com/pratikkayal/PlantDoc-Dataset) states **CC BY 4.0** in its README and sidebar; the paper (arXiv 1911.10317) says the images were **scraped from Google Images and Ecosia** and the paper says nothing about copyright or licensing | CC BY 4.0 is declared for the dataset, but the images are third-party web images and no source shows the authors had the right to license them; the **image** licence is therefore not established. The annotations (bounding boxes drawn by the authors) have no separate licence statement. Access date of this reading: 2026-10-18 | written confirmation from the authors of the rights in the images, or a documented review that accepts the risk (the owner's call, outside the application's rules); the LICENSE.txt text itself was not read |
| PlantVillage | sources conflict: CC0 1.0 (a derived-dataset repository), CC BY-SA 3.0 with a share-alike clause reaching trained algorithms (the dataset paper), Kaggle derivatives under Kaggle's terms | conflicting evidence and a possible share-alike (excluded) licence | the publisher's own current licence statement; if it is CC BY-SA, excluded |
| Cassava Leaf Disease (Mendeley) | licence not seen | unconfirmed | read the licence on the Mendeley record |
| PlantNet-300K | code BSD-2-Clause; dataset reported CC BY 4.0 by a redistributor only | only second-hand evidence; species identification, not disease | read the licence at the Zenodo record (10.5281/zenodo.5645731) |
| Plant Pathology 2021 (Kaggle FGVC8) | not found | competition terms usually restrict use | read the competition rules |

Scientific risks that licences do not remove: PlantVillage is lab imagery that overstates field accuracy; PlantDoc is small; cassava is one crop; PlantNet is species, not health.

## 4. The exact evidence needed to approve a dataset
An owner or admin can approve only when the catalog shows **no blockers**. For each real dataset record:
1. **Source URL** (https) and the **date it was accessed**.
2. **Licence of the images** and, if there are annotations, **of the annotations**, each one of `CC0-1.0`, `CC-BY-2.0`, `CC-BY-2.5`, `CC-BY-3.0`, `CC-BY-4.0`; and the **image origin**: `publisher_created` or `third_party_licensed` (the publisher documents the licences or permissions of third-party images). `third_party_scraped` and `unknown` block approval.
3. **Evidence from an official source** (the publisher or host, not a mirror, article or summary) for the images, and for the annotations if present: URL, kind, scope, the licence that source states, a quoted excerpt of the statement, access date. At least one such record per scope.
4. **No contradicting evidence**: any recorded source naming a different licence for the same scope blocks approval until resolved.
5. **Commercial use confirmed `yes`**, **redistribution** recorded (`yes` or `no`), **attribution** recorded as required or not, with the attribution text when required.
6. **Intended use** in words.
7. The approval by an **owner or admin**, who is recorded with the time. Re-opening a dataset (`under_review`) clears the approval and locks nothing else; rejection is final for that version.

Not checkable by the application (so a human must): that the evidence is genuine and current, that the publisher actually owns the rights it licenses, and whether the licence text has terms beyond its headline.

## 5. Plant-health review: what is and is not claimed
There is no confirmed qualified reviewer. The workflow therefore records **who decided, when, on what written evidence, and what changed**, and the reviewer's own statement of qualification, which is stored as `declared` and marked `qualification_verified: false` everywhere. The application cannot verify a qualification, so **no label is ever described as expert-validated**; the review summary reports `qualified_reviewers_verified: 0`. Only `accepted` and `corrected` labels count as reviewed; splits use only those unless `include_unreviewed` is set, which is recorded on the split and warned about.

## 6. Why nothing may be claimed yet
`claim-readiness` returns blockers. Two of them cannot be cleared inside the application today: **no verified qualified reviewer** and **no registered evaluation protocol** (field-domain test data, acceptance thresholds, intended use). The rest are data conditions: dataset approved, quality checks passed, no leakage, at least 95 % of labels reviewed, at least 200 test items and 30 per class. These thresholds are engineering gates, not scientific guarantees. Disease-model training and any accuracy claim stay blocked until licensed data, label quality and an evaluation protocol exist.

## 7. Limitations
- The quality report compares near duplicates pairwise and skips that check above 5,000 hashed samples (it says so). Analyses are capped at 20,000 samples per request.
- Image bytes are not stored; the catalog holds metadata and fingerprints. `scan_directory` fingerprints a LOCAL folder; it never downloads.
- Splits balance labels greedily; with few or very uneven groups they cannot be balanced and the result warns.
- A dataset's description is immutable except its status; a correction is a new version.
- Not built: a screen for any of this (API only), label import from files, inter-reviewer agreement statistics, a protocol registry, retention of dataset records.

## 8. Candidate worksheet and the next task
`docs/datasets/candidates.json` holds the candidates above in the exact shape the API accepts (`POST /datasets`, `POST /datasets/{id}/evidence`). Evidence is recorded only for a page that was actually read (PlantDoc's repository README); a test fails if any candidate becomes approvable without new evidence, or if evidence is recorded for an unread page. Inter-reviewer agreement is built.

**Recommended next:** a Datasets page (catalog with its blocker checklist, evidence entry, review queue with the evidence field, quality and claim panels), because the review workflow is only usable by people through the API today. After that, an evaluation-protocol registry, which needs the owner to decide the acceptance criteria and the field-domain test data first.

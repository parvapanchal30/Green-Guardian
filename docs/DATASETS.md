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

## 3. Candidate datasets: what was verified at the source (2026-10-18)
Evidence below was gathered from official sources by reading the pages and records themselves; it is recorded in `docs/datasets/candidates.json` and loads into the catalog with `python -m app.tools.dataset_worksheet`. Each evidence record says how it was verified: **read in full text** (a document extracted and read), **page-reader tool quote** (a tool summarised the page and returned quoted fragments; only those fragments are quoted, and they were not compared with the raw HTML), or **API field** (a host's machine-readable record). Quotes marked with the second method should be re-confirmed by a person before they are relied on for an approval. **Nothing is approved, and a hosting repository's licence is never treated as proof that its uploader could license third-party images.**

| Candidate | Verified at the source | Still unresolved | Outcome |
|---|---|---|---|
| **PlantDoc** | the repository README states CC BY 4.0 for the dataset; the paper says the images were scraped from Google Images and Ecosia and says nothing about copyright | the authors' right to license scraped images; commercial use and redistribution not stated | **Excluded by owner decision (2026-10-18).** Its authors are not to be contacted and it is not to be approved unless the owner explicitly authorises that later. |
| **PlantVillage** | the creators' paper (read in full text) states CC BY-SA 3.0 *with the clarification that algorithms trained on the data fall under the same license*; PlantVillage's own terms of service say its content is licensed CC BY-SA 3.0 unless marked otherwise (tool quote); the creators' images were taken at university research stations. The common GitHub mirror states no licence and is not the creators' site | whether the terms have since changed (no sign of it) | **Excluded by policy** (share-alike). An owner or admin should reject it in the catalog. Models trained on it would themselves be share-alike, which the project cannot accept. |
| **Cassava Leaf Disease (Mendeley)** | the host shows CC BY 4.0; authors from IIT Kharagpur; images "collected manually" in commercial fields in western Tamil Nadu; Creative Commons states CC BY 4.0 allows use "for any purpose, even commercially" with credit | **who took the photographs and whether field owners permitted publication**; no associated paper found; the host's footer reserves text-and-data-mining and AI-training rights beside the CC label, and the two statements are not reconciled on the pages read | **Blocked on image origin** (the only open catalog blocker). |
| **PlantNet-300K** | the Zenodo record's own metadata gives CC BY 4.0; the images come from the Pl@ntNet citizen observatory; the code is BSD-2-Clause and the metadata file holds a per-image author and licence | **the licence of each contributed image** (inside the download, which is not allowed before approval); whether CC BY could be applied to all of them; it identifies species, not disease | **Blocked**: images licence unknown; also off-scope. |
| **Irish Potato Imagery (Tanzania, Zenodo)** | Zenodo metadata gives CC BY 4.0, open access; 58,709 field images of healthy, early and late blight leaves captured by researchers, farmers and extension officers on farms with smartphones, labels validated by plant pathologists (article, itself CC BY); consent for data collection reported | whether every photo was taken by the project team or by farmers, and whether consent covers release under CC BY; no inter-rater agreement reported | **Blocked on image origin only.** The closest to approvable and the best fit for the proposed protocol. |
| **Tomato diseases, greenhouse (Mendeley)** | the host shows CC BY 4.0; boxes annotated in LabelImg under expert guidance; greenhouse images, one contributor and no institution given | the associated article is **CC BY-NC**, which conflicts with the dataset label; the photographer and owner are not named | **Blocked**: conflicting licence statements; any non-commercial licence on the work is excluded until clarified. |
| Plant Pathology 2021 (Kaggle FGVC8) | the research tools could not retrieve the rules or data pages (script-rendered) | everything | Not entered; unresolved. |
| Common bean, Tanzania (Data in Brief 2026) | a promising lead: field images reviewed by extension officers and plant pathologists, article CC BY | its Zenodo record was not identified and no dataset licence was read | Not entered; a lead only. |

Scientific risks that licences do not remove: PlantVillage is lab-like imagery that overstates field accuracy; PlantDoc is small; Cassava and Irish potato are single crops; the Irish potato set covers two diseases, mostly well-lit images and mainly one variety; PlantNet is species, not health.

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
- Built since: the Datasets and protocol pages, CSV sample import (ADR-050), reviewer agreement, the protocol registry, cluster-bootstrap statistics (ADR-049). Not built: importing the images themselves, bulk label updates, retention of dataset records.

## 8. Worksheet, UI and next steps
`docs/datasets/candidates.json` holds the candidates in the exact shape the catalog accepts, with the evidence above. `python -m app.tools.dataset_worksheet --workspace <id> --user-email <manager>` loads it (a dry run unless `--apply`) through the same service code as the API, as a named workspace member; it creates `proposed` datasets only, never approves anything, never fetches or downloads, and skips what already exists. Tests keep every candidate blocked until its open questions are answered, and fail if any evidence is added without saying how it was verified.

The **Datasets page** (`/w/:ws/ai/datasets`) shows the catalog, candidate versus approved, licence and image-origin status, evidence with its quoted statements, approval blockers, the review and approval workflow for authorised users (the server decides; the page never checks blockers for it), samples and review queue with history, quality reports, splits, reviewer agreement with Cohen's kappa, and the claim gate. The **evaluation-protocol registry** is described in `EVALUATION_PROTOCOL.md`.

**Next:** the owner reads the remaining open questions (who took the Cassava and Irish potato photographs; whether PlantNet's per-image licences allow it) and decides on the PlantVillage rejection; a qualified, verifiable plant-health reviewer and a qualification-verification mechanism are the structural gaps; the cluster bootstrap and risk-coverage metrics named in the protocol still need implementing.

## 9. Registering samples (CSV import)
Managers add samples in the Samples tab: choose a `.csv`, **preview** (the server validates and reports row-level errors, writes nothing), then import. Columns: `external_id` (required), `group_key`, `label`, `content_sha256`, `phash`, `file_status`, `width`, `height`, `source` (required for real datasets). The file is accepted or refused as a whole; a retry is safe; a row that already exists with different values is an error (an import never overwrites a sample or a reviewed label). **Every imported label is unreviewed**, and a column carrying review status (`label_status`, `reviewed`, `validated`, `reviewer` ...) is refused. Real datasets accept imports only once approved. See ADR-050.

## 10. Evaluation statistics and the claim gate
`statistics.py` provides the cluster bootstrap over groups (documented estimand, 2,000 replicates, explicit seed, honest handling of too few groups and missing classes) and risk-coverage metrics for selective prediction (abstentions never covered, ties handled). The claim gate now enforces the protocol's sample-size rule: **at least two classes with 139 or more test images each**, others excluded from claims. Neither clears the reviewer or protocol blockers, and no model is trained or scored.

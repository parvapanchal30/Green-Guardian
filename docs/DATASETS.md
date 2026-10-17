# Datasets and data foundations (Stage D investigation)

_Status 2026-10-18: investigation only. **No dataset has been downloaded, no model trained, no labelling tool built.** Licence statements below come from one round of web search and are marked by how well they were confirmed. Every licence must be re-read at the official source before a download or any redistribution._

## What Stage D must deliver (from the roadmap)
Dataset catalog with licences, labelling workflow, versioned train/validation/test splits, an evaluation harness, data-quality checks. Stages E to M depend on it. Nothing in D is useful without knowing which data we may legally and scientifically use.

## What GreenGuardian itself can supply today
Only data users record: observations (health score 0-100, symptoms as free tags, notes), photos (evidence), issues with resolutions, tasks. There are **no confirmed diagnoses, no growth measurements in a fixed protocol, no yield or irrigation records and no sensor data**. Any model trained on today's own data would learn from unlabelled or self-reported labels. So early models must use public data for pre-training and own data only for evaluation once a reviewed label exists.

## Candidate public datasets for disease image work (Stage E)
| Dataset | Content | Licence finding | Confirmation | Main scientific risk |
|---|---|---|---|---|
| PlantVillage (Hughes and Salathe) | tens of thousands of leaf images, 14 crops, lab background | **sources conflict**: CC0 1.0 (a derived-dataset repository), CC BY-SA 3.0 with a share-alike clause that reaches trained algorithms (the dataset paper on arXiv), and Kaggle derivatives under Kaggle's default terms | **not settled** | single leaf on a plain background: models score very high and fail in the field (domain shift) |
| PlantDoc | about 2.6k field images, 13 plants, 27 classes, bounding boxes | CC BY 4.0 (attribution) | confirmed in three places (paper table, Roboflow, official repository) | small; image count differs between sources (2,569 vs 2,598) |
| Cassava Leaf Disease (Mendeley) | about 21,400 field images, 5 classes | not seen | **unconfirmed**; the Kaggle competition copy is a different distribution with its own rules | one crop only |
| PlantNet-300K | species identification, about 300k images | code is BSD-2-Clause; dataset reported as CC BY 4.0 by a redistributor | **unconfirmed** at the Zenodo record (10.5281/zenodo.5645731) | species, not disease: useful for species identification, not health |
| Plant Pathology 2021 (Kaggle FGVC8) | apple foliar disease images | not found | **unconfirmed**; Kaggle competition rules usually restrict use | competition terms |

## Consequences
1. **A share-alike or competition licence can bind a trained model or restrict commercial use.** Until counsel or the licensor confirms, PlantVillage-derived weights must not be shipped in a product. Prefer CC BY or CC0 data with a recorded source URL, version and checksum.
2. **Domain shift is the dominant technical risk.** A model must be evaluated on field photos of the kind users upload (PlantDoc-like, and later the users' own reviewed photos), never only on a random split of a lab dataset. Reporting accuracy from a random split of PlantVillage would overstate real performance and is not acceptable as a product claim.
3. **Labels come from experts.** The label for a user's photo is only useful after a qualified person has reviewed it. The labelling workflow therefore needs reviewer roles, disagreement handling and an "uncertain" outcome.
4. **Splits must be grouped** (by plant, field and date) so near-duplicate photos of one plant cannot sit on both sides of a split.

## Non-image Stage F-M inputs: what exists
Growth, survival, yield and crop recommendation need measured series (soil tests, weather history, yields, costs). Public crop-recommendation datasets circulating on Kaggle are widely reported as small and synthetic and are not an acceptable basis for a product claim; no source was verified here. These stages stay blocked on real data from pilot users or a verified agronomic source.

## Proposed order of work (decision ADR-043)
1. **Now (no external data needed):** a dataset catalog record type (name, source URL, version, licence text and SPDX id, retrieval date, checksum, allowed uses, review status), an evaluation-harness skeleton with grouped splits and metrics (per class precision/recall, calibration, confusion matrix, confidence intervals), and data-quality checks (duplicates by perceptual hash, label noise flags, EXIF/GPS handling). These are testable on synthetic fixtures and carry no licence risk.
2. **Needs a human decision:** which licences are acceptable (for example CC0 and CC BY only), and whether a licence review by someone qualified is available.
3. **Then:** verify licences at source, download one small dataset (PlantDoc is the best-confirmed), build a baseline, and report honestly on the held-out field set. No model is exposed in the product until it has been evaluated on field data and labelled as MODEL with its measured limits behind `CapabilityGate`.

## Not decided here
Whether to collect the users' own labelled photos (privacy, consent, GPS in EXIF, retention); which expert reviews labels; compute budget and where training runs.

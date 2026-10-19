# Evaluation protocol for a future plant-disease model (proposal P-DIS-1)

_Status 2026-10-18: **PROPOSED. Not approved. Nothing here has been signed off by anyone qualified, no model exists, and no dataset is approved.** This document proposes a protocol so that, when data and people exist, the evaluation is fixed before any model is trained. It is stored in the application as a protocol template (`GET /evaluation-protocols/template`); the registry (ADR-047) records versions and sign-offs, refuses invented thresholds, and cannot mark a protocol approved while qualifications are unverifiable. Where a number would need domain expertise it is **not invented**: it is left empty and marked pending._

## 1. Intended use
- **What it is for:** decision support. Given one or more photographs of a single plant part (leaf, fruit or stem) taken with a smartphone by a grower or field worker, suggest up to **k = 3** candidate conditions, each with a calibrated confidence, or abstain ("unsure, ask an expert"). A person decides. A suggestion can become a botanical issue only when a person accepts it.
- **What it is not for:** a diagnosis, a treatment or dose recommendation, pesticide decisions, regulatory or certification decisions, or any use on species, regions or conditions outside section 2.
- **Output labelling:** every output is labelled MODEL with its measured scope and limits, behind `CapabilityGate`; it is never shown as a rule or as an expert opinion.

## 2. Target population, species and classes
- **Users and imagery:** growers and field staff using ordinary phones, in daylight, in the field (not a lab).
- **Initial scope (proposal, to be confirmed by the domain approver):** **one crop family only**, chosen because licensed field data exist for it: potato (healthy, early blight, late blight) is the candidate with the closest-to-approvable data today (Irish Potato Imagery Dataset, CC BY 4.0, blocked only by image origin); cassava (healthy, cassava bacterial blight, cassava mosaic disease) is the second candidate. Every other species is **out of scope** and the product must say so.
- **Required "other" class:** an `other/unknown` class and an abstention path, because users will photograph things that are not in the list (open-set behaviour). A model without it must not be offered.
- **Pending:** the final species and class list is a domain decision.

## 3. Inclusion and exclusion criteria for evaluation data
- **Include:** RGB photographs of one plant part of one species in the scope, taken outdoors, effective resolution at least 224 px on the short side after cropping, with a recorded source, licence, collection site and date.
- **Exclude from the test set:** laboratory or plain-background images (they may be used for training only and never for a field claim); multiple species in frame; images that are not of a plant; corrupt or invalid files; exact or near duplicates (by hash and perceptual hash) of any training image; images whose origin or licence is not established; images without a recorded site.
- **Exclude entirely:** anything from a dataset that is not approved in the catalog (CC0 and CC BY only, with verified evidence and a documented image origin of `publisher_created` or `third_party_licensed`).

## 4. Dataset and label-quality requirements
1. Approved dataset(s) only; the quality report has no error-level issue.
2. **Labels:** every test image labelled by **two independent qualified reviewers**; disagreements adjudicated by a third; each decision recorded with written evidence (the review workflow already does this). At least 95% of all labels reviewed (existing gate).
3. **Reviewer qualification must be verified.** The application cannot verify qualifications today; this requirement therefore cannot be met yet (a deliberate blocker).
4. **Label reliability:** report Cohen's kappa between the two reviewers on the test set. Proposed minimum: **kappa of at least 0.60**, the lower edge of the band commonly called "substantial" (Landis and Koch convention). *Pending domain approval:* a pathologist may require more for diseases that look alike.
5. Class balance and rarity are reported, never hidden; a class with too few test images is **excluded from claims** rather than reported with a wide interval.

## 5. Grouping strategy (preventing leakage)
- **Group hierarchy:** farm or site, then plot, then plant, then collection date. Images of one plant, one plot or one visit are near-copies and must never be on both sides of a split.
- **Test split by site (and season where known):** the held-out test set contains **whole farms/sites that the model never saw**, because the product's promise is "works on a new farm". The validation set is split by plot within the training sites.
- **If the source data records no site:** the best available group is used, and the claim is **downgraded** to "recognises these conditions on photographs like those in the dataset", never "works on new farms".
- The independent leakage checker (groups, identical files, near duplicates) must report no violations, and the split version and checksum are recorded.

## 6. Training, validation and held-out test methodology
- **Pre-registration:** this protocol version, the metrics, the thresholds and the split version are fixed **before training**. Changing any of them creates a new protocol version, and the change is visible.
- **Training set:** model fitting only. **Validation set:** model selection, early stopping, the abstention threshold and calibration (temperature scaling) fitted here and nowhere else.
- **Held-out test set:** frozen and checksummed. Each model version is evaluated on it **once**. Re-evaluating after seeing results, or tuning on it, makes the result **exploratory** and it may not support a claim; a fresh test set is then needed.
- **External validation (required for any field claim):** one further evaluation on an independent dataset from different sites and cameras, evaluated once. A large drop relative to the internal test is reported and limits the claim.
- **Seeds and runs:** several training runs with different seeds; report the spread, not the best run.

## 7. Baselines and per-class metrics
- **Baselines (all required):** (a) always predict the majority class; (b) a simple non-deep model (colour and texture features with logistic regression); (c) a standard pretrained image classifier fine-tuned with ordinary settings. The model must beat each with the **lower confidence bound of the difference in macro-F1 above zero**.
- **Human reference:** model-versus-adjudicated-label agreement is shown next to reviewer-versus-reviewer agreement (section 4.4).
- **Metrics, reported per class and overall:** confusion matrix; precision, recall and F1 per class; macro-F1; accuracy shown **beside the majority-class baseline**; abstention rate and selective accuracy at that rate (risk-coverage curve); top-3 hit rate. No single headline number.

## 8. Confidence intervals and calibration
- **Proportions** (accuracy, per-class recall and precision): Wilson 95% intervals (implemented).
- **Overall and macro metrics:** **cluster bootstrap resampling whole groups** (at least 1,000 resamples), because images within a group are not independent and ordinary intervals would be too narrow. *Not implemented yet; a follow-up.*
- **Calibration:** reliability diagram, expected calibration error (10 bins, implemented) and Brier score, on the held-out test set, with the calibration fitted on validation only. Confidence shown to users must come from the calibrated output.
- **Status of the implementation (ADR-049):** the cluster bootstrap and risk-coverage metrics described in this section are implemented in `statistics.py` (estimand, resampling unit, replicates, seed, degenerate cases and limits are stated in its docstring and in the report); the dataset claim gate now enforces the sample-size rule below (at least two classes with 139 or more test images each; other classes are excluded from claims). Implementing the method is not domain approval of any threshold.
- **Sample size:** a per-class recall interval with half-width at most 0.05 needs about **139 test images per class** if recall is near 0.90, and **385** in the worst case (recall near 0.50): n = z² p (1 - p) / h², with z = 1.96 (normal approximation, rounded up: 138.3 becomes 139, 384.2 becomes 385). This is arithmetic, not a judgement. The earlier engineering gate (200 images in total, 30 per class) was weaker and has been replaced by this rule. It is a planning rule for measuring recall with a given precision under independence; it does not show that a model is accurate, and with correlated images more may be needed (the cluster bootstrap shows how much).

## 9. False positives and false negatives
- **False negative** (disease missed): delayed treatment and spread; likely the costlier error for fast-spreading diseases such as late blight.
- **False positive** (disease suggested where there is none): unnecessary treatment, cost and pesticide use, and loss of trust.
- **Operating point:** chosen on the validation set, not the test set, to meet a recall target for the disease classes, and the resulting false-positive rate is reported with its interval. The abstention path is the safety valve: low-confidence cases go to a person.
- *Pending domain approval:* the relative cost of the two errors per disease, and the recall target. The application cannot supply these.

## 10. Acceptance thresholds, and who must approve them
| Item | Proposed rule | Basis | Status |
|---|---|---|---|
| Test images per class | at least 139 | arithmetic above (half-width 0.05 at recall 0.9) | proposed, needs sign-off |
| Distinct test sites | at least 3 | engineering judgement: fewer sites cannot show new-farm generalisation | pending domain approval |
| Labels reviewed | at least 95% | existing engineering gate | proposed, needs sign-off |
| Inter-reviewer kappa | at least 0.60 | common convention ("substantial") | pending domain approval |
| Beat each baseline | lower bound of macro-F1 difference above 0 | statistical design | proposed, needs sign-off |
| Per-class recall, lower 95% bound | **no value proposed** | needs domain expertise (cost of a missed disease) | **pending domain approval** |
| False-positive rate at the operating point | **no value proposed** | needs domain expertise | **pending domain approval** |
| Expected calibration error | **no value proposed** | needs domain and product input | **pending domain approval** |
| Maximum drop on external validation | **no value proposed** | needs domain input | **pending domain approval** |

**Required sign-offs (all three, each by a different person):**
1. **Plant pathologist** with verified qualification: classes, label rules, error costs and every domain threshold.
2. **Data owner** (the workspace owner): licences, image origin, intended use.
3. **Independent evaluator** (not involved in training the model): methodology, leakage control, statistics.

The protocol is **approved only when all three have signed AND each signer's qualification is verified**. The application records sign-offs and declared qualifications but has **no way to verify a qualification**, so a protocol cannot reach `approved` today. That is intended.

## 11. Limitations, and when claims are prohibited
**No claim may be made, and the interface must say so, when:**
- the dataset is not approved, or its approval is later withdrawn;
- labels are unreviewed, were reviewed by unverified reviewers, or kappa is below the protocol minimum;
- the data are synthetic, laboratory-background, or from unknown origin;
- the split leaks (any violation), the test set was used for tuning, or it was evaluated more than once;
- the test set is below the size requirement, or a class has too few images (that class is excluded from the claim);
- the result is for other species, regions, seasons, cameras or growth stages than those tested;
- there is no external validation (then no "works in the field" claim);
- the statement would be a diagnosis, a treatment recommendation, or an accuracy figure without its interval and scope.

**Known limitations of this proposal:** no qualification verification exists, and the statistical code is only as good as the test set it is given; image-level site metadata may be missing from public datasets, which would downgrade the claim; open-set behaviour is hard to measure without a deliberately collected "other" set.

## 12. Maintenance
Any change to a threshold, class, dataset or split creates a new protocol version that needs fresh sign-offs. A model is re-evaluated under the then-current protocol before each release, and retired if the field distribution (new diseases, varieties or cameras) drifts outside the tested scope.

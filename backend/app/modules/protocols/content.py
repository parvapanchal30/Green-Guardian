"""Evaluation-protocol content: what a protocol must say, and rules that stop it from claiming more than it can.

A protocol is a plan fixed BEFORE any model is trained (see docs/EVALUATION_PROTOCOL.md). The schema refuses the two ways
such plans usually cheat: thresholds with no stated basis, and thresholds that need domain expertise but arrive with an
invented number. A threshold that depends on domain judgement must be marked pending and may carry no value.
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import Field, model_validator

from app.core.schemas import StrictModel

REQUIRED_ROLES = ("plant_pathologist", "data_owner", "independent_evaluator")
Role = Literal["plant_pathologist", "data_owner", "independent_evaluator"]
Basis = Literal[
    "statistical_derivation",  # arithmetic from stated assumptions (for example a sample size)
    "statistical_design",  # a rule about how to compare (for example a lower confidence bound above zero)
    "existing_gate",  # a gate already enforced elsewhere in the application
    "convention",  # a published convention, still needing a domain approver
    "engineering_judgement",  # a sensible engineering choice, still needing a domain approver
    "pending_domain_input",  # cannot be set without domain expertise: no value may be given
]
DOMAIN_BASES = {"convention", "engineering_judgement", "pending_domain_input"}


class Threshold(StrictModel):
    id: str = Field(min_length=3, max_length=60, pattern=r"^[a-z0-9_]+$")
    metric: str = Field(min_length=3, max_length=120)
    scope: str = Field(min_length=3, max_length=200)
    comparator: Literal["ge", "le", "gt", "lt"]
    value: float | None = None
    basis: Basis
    requires_domain_expertise: bool
    status: Literal["proposed", "pending_domain_approval"]
    justification: str = Field(min_length=20, max_length=1000)

    @model_validator(mode="after")
    def _no_invented_numbers(self) -> Threshold:
        needs_domain = self.requires_domain_expertise or self.basis in DOMAIN_BASES
        if needs_domain and self.status != "pending_domain_approval":
            raise ValueError(
                f"threshold {self.id!r} depends on domain judgement, so its status must be pending_domain_approval"
            )
        if self.basis == "pending_domain_input" and self.value is not None:
            raise ValueError(f"threshold {self.id!r} needs domain input and must not carry an invented value")
        if self.value is None and self.status != "pending_domain_approval":
            raise ValueError(f"threshold {self.id!r} has no value, so it can only be pending_domain_approval")
        return self


class Grouping(StrictModel):
    hierarchy: list[str] = Field(min_length=2, max_length=8)
    test_split_unit: str = Field(min_length=3, max_length=120)
    claim_downgrade_if_no_site: str = Field(min_length=10, max_length=500)


class ErrorCosts(StrictModel):
    false_negative: str = Field(min_length=10, max_length=1000)
    false_positive: str = Field(min_length=10, max_length=1000)
    operating_point: str = Field(min_length=10, max_length=1000)


class ProtocolContent(StrictModel):
    title: str = Field(min_length=5, max_length=200)
    intended_use: str = Field(min_length=20, max_length=2000)
    not_for: list[str] = Field(min_length=1, max_length=20)
    target_population: str = Field(min_length=10, max_length=1000)
    species: list[str] = Field(min_length=1, max_length=20)
    disease_classes: list[str] = Field(min_length=2, max_length=60)
    inclusion_criteria: list[str] = Field(min_length=1, max_length=30)
    exclusion_criteria: list[str] = Field(min_length=1, max_length=30)
    dataset_requirements: list[str] = Field(min_length=1, max_length=30)
    label_requirements: list[str] = Field(min_length=1, max_length=30)
    grouping: Grouping
    methodology: list[str] = Field(min_length=3, max_length=30)
    baselines: list[str] = Field(min_length=2, max_length=10)
    metrics: list[str] = Field(min_length=3, max_length=30)
    confidence_and_calibration: list[str] = Field(min_length=2, max_length=20)
    error_costs: ErrorCosts
    thresholds: list[Threshold] = Field(min_length=1, max_length=40)
    required_signoffs: list[Role] = Field(min_length=3, max_length=3)
    prohibited_claims: list[str] = Field(min_length=3, max_length=40)
    limitations: list[str] = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def _complete(self) -> ProtocolContent:
        if set(self.required_signoffs) != set(REQUIRED_ROLES):
            raise ValueError(f"required_signoffs must be exactly {', '.join(REQUIRED_ROLES)}")
        if not any(c.strip().lower() in {"other", "unknown", "other/unknown"} for c in self.disease_classes):
            raise ValueError(
                "disease_classes must include an 'other' or 'unknown' class: users will photograph things outside the list"
            )
        if not any("majority" in b.lower() for b in self.baselines):
            raise ValueError("baselines must include the majority-class baseline")
        ids = [t.id for t in self.thresholds]
        if len(set(ids)) != len(ids):
            raise ValueError("threshold ids must be unique")
        return self


def content_sha256(content: dict) -> str:
    return hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def template() -> dict:
    """P-DIS-1 as proposed in docs/EVALUATION_PROTOCOL.md. A starting point to copy, not an approved protocol."""
    return {
        "title": "P-DIS-1: photo-based leaf-disease triage assistant (proposal)",
        "intended_use": (
            "Decision support: from photographs of one plant part taken with a smartphone, suggest up to three candidate "
            "conditions with calibrated confidence, or abstain. A person decides; a suggestion becomes an issue only when accepted."
        ),
        "not_for": [
            "diagnosis",
            "treatment or dose recommendations",
            "pesticide decisions",
            "regulatory or certification decisions",
            "species, regions or conditions outside this protocol",
        ],  # fmt: skip
        "target_population": "Growers and field staff using ordinary phones outdoors in daylight; not laboratory imaging.",
        "species": ["potato (initial candidate, to be confirmed by the domain approver)"],
        "disease_classes": ["healthy", "early blight", "late blight", "other/unknown"],
        "inclusion_criteria": [
            "RGB photograph of one plant part of one in-scope species, taken outdoors",
            "effective resolution of at least 224 px on the short side after cropping",
            "recorded source, licence, collection site and date",
        ],
        "exclusion_criteria": [
            "laboratory or plain-background images (training only, never a field claim)",
            "several species in frame, or not a plant",
            "corrupt files, and exact or near duplicates of any training image",
            "images whose origin or licence is not established, or without a recorded site",
            "anything from a dataset that is not approved in the catalog",
        ],
        "dataset_requirements": [
            "approved datasets only (CC0 or CC BY with verified evidence, image origin publisher_created or third_party_licensed)",
            "the data-quality report has no error-level issue",
        ],
        "label_requirements": [
            "every test image labelled by two independent reviewers, disagreements adjudicated by a third",
            "at least 95% of labels reviewed",
            "reviewer qualification verified (the application cannot do this yet)",
            "Cohen's kappa between the two reviewers reported on the test set",
            "classes with too few test images are excluded from claims",
        ],
        "grouping": {
            "hierarchy": ["farm or site", "plot", "plant", "collection date"],
            "test_split_unit": "whole farms or sites never seen in training (validation split by plot)",
            "claim_downgrade_if_no_site": (
                "If the source data record no site, the claim is limited to photographs like those in the dataset and must "
                "not say the model works on new farms."
            ),
        },
        "methodology": [
            "the protocol, metrics, thresholds and split version are fixed before training",
            "training set fits the model; validation set selects the model, sets the abstention threshold and fits calibration",
            "the held-out test set is frozen and checksummed and each model version is evaluated on it once; re-use makes the result exploratory",
            "external validation on an independent dataset from different sites and cameras, evaluated once, is required for any field claim",
            "several seeds are trained and the spread is reported",
        ],
        "baselines": [
            "always predict the majority class",
            "simple non-deep model (colour and texture features with logistic regression)",
            "standard pretrained image classifier fine-tuned with ordinary settings",
        ],
        "metrics": [
            "confusion matrix",
            "per-class precision, recall and F1",
            "macro-F1",
            "accuracy shown beside the majority baseline",
            "abstention rate and selective accuracy (risk-coverage)",
            "top-3 hit rate",
        ],  # fmt: skip
        "confidence_and_calibration": [
            "Wilson 95% intervals for proportions",
            "cluster bootstrap over whole groups (at least 1,000 resamples) for overall and macro metrics (not implemented yet)",
            "reliability diagram, expected calibration error (10 bins) and Brier score; calibration fitted on validation only",
        ],
        "error_costs": {
            "false_negative": "A missed disease delays treatment and allows spread; likely the costlier error for fast-spreading diseases.",
            "false_positive": "A false alarm causes unnecessary treatment, cost and pesticide use, and erodes trust.",
            "operating_point": "Chosen on the validation set to meet a recall target for disease classes; the false-positive rate at that point is reported with its interval. Relative costs and the recall target are pending domain approval.",
        },
        "thresholds": [
            {
                "id": "test_images_per_class",
                "metric": "test images per class",
                "scope": "every class included in a claim",
                "comparator": "ge",
                "value": 139,
                "basis": "statistical_derivation",
                "requires_domain_expertise": False,
                "status": "proposed",
                "justification": "n = z^2 p(1-p)/h^2 with z = 1.96, p = 0.9 and half-width h = 0.05 gives 138.3, rounded up; 385 if p = 0.5.",
            },
            {
                "id": "distinct_test_sites",
                "metric": "distinct farms or sites in the test set",
                "scope": "test set",
                "comparator": "ge",
                "value": 3,
                "basis": "engineering_judgement",
                "requires_domain_expertise": True,
                "status": "pending_domain_approval",
                "justification": "Fewer sites cannot show generalisation to a new farm; the exact number needs a domain approver.",
            },
            {
                "id": "labels_reviewed_fraction",
                "metric": "fraction of labels reviewed",
                "scope": "dataset",
                "comparator": "ge",
                "value": 0.95,
                "basis": "existing_gate",
                "requires_domain_expertise": False,
                "status": "proposed",
                "justification": "The same gate the dataset claim-readiness check already enforces.",
            },
            {
                "id": "inter_reviewer_kappa",
                "metric": "Cohen's kappa between the two reviewers",
                "scope": "test set",
                "comparator": "ge",
                "value": 0.6,
                "basis": "convention",
                "requires_domain_expertise": True,
                "status": "pending_domain_approval",
                "justification": "0.60 is the lower edge of the band commonly called substantial; a pathologist may require more for look-alike diseases.",
            },
            {
                "id": "beats_baselines",
                "metric": "lower 95% bound of (model minus baseline) macro-F1",
                "scope": "each required baseline",
                "comparator": "gt",
                "value": 0.0,
                "basis": "statistical_design",
                "requires_domain_expertise": False,
                "status": "proposed",
                "justification": "A model that cannot be separated from a trivial baseline by its interval has shown nothing.",
            },
            {
                "id": "recall_lower_bound",
                "metric": "lower 95% bound of recall",
                "scope": "each disease class",
                "comparator": "ge",
                "value": None,
                "basis": "pending_domain_input",
                "requires_domain_expertise": True,
                "status": "pending_domain_approval",
                "justification": "Depends on the cost of a missed disease, which only a domain approver can judge; no value is proposed.",
            },
            {
                "id": "false_positive_rate",
                "metric": "false-positive rate at the operating point",
                "scope": "each disease class",
                "comparator": "le",
                "value": None,
                "basis": "pending_domain_input",
                "requires_domain_expertise": True,
                "status": "pending_domain_approval",
                "justification": "Depends on the cost of unnecessary treatment; no value is proposed.",
            },
            {
                "id": "expected_calibration_error",
                "metric": "expected calibration error",
                "scope": "held-out test set",
                "comparator": "le",
                "value": None,
                "basis": "pending_domain_input",
                "requires_domain_expertise": True,
                "status": "pending_domain_approval",
                "justification": "Depends on how confidence is shown to users; no value is proposed.",
            },
            {
                "id": "external_validation_drop",
                "metric": "drop in macro-F1 from internal test to external validation",
                "scope": "external dataset",
                "comparator": "le",
                "value": None,
                "basis": "pending_domain_input",
                "requires_domain_expertise": True,
                "status": "pending_domain_approval",
                "justification": "Depends on how different the sites and cameras are; no value is proposed.",
            },
        ],  # fmt: skip
        "required_signoffs": ["plant_pathologist", "data_owner", "independent_evaluator"],
        "prohibited_claims": [
            "any claim when the dataset is not approved or its approval was withdrawn",
            "any claim from unreviewed labels, unverified reviewers, or kappa below the protocol minimum",
            "any claim from synthetic, laboratory-background or unknown-origin data",
            "any claim when the split leaks, the test set was used for tuning or evaluated more than once",
            "any claim for a class with too few test images, or beyond the species, regions, seasons and cameras tested",
            "a 'works in the field' claim without external validation",
            "a diagnosis, a treatment recommendation, or an accuracy figure without its interval and scope",
        ],
        "limitations": [
            "cluster bootstrap and risk-coverage curves are not implemented yet",
            "the claim gate's size thresholds are weaker than the protocol's sample-size rule",
            "the application cannot verify anyone's qualification",
            "public datasets may lack site metadata, which would downgrade the claim",
        ],
    }

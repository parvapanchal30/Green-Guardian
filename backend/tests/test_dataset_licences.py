"""Licence policy and approval blockers. Pure; the policy is the owner's decision of 2026-10-18."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from app.modules.datasets import licences
from app.modules.datasets.licences import DatasetFacts, Evidence, Verdict, approval_blockers, classify

NOW = datetime(2026, 10, 18, tzinfo=UTC)


@pytest.mark.parametrize("spdx", ["CC0-1.0", "CC-BY-4.0", "cc-by-4.0", " CC-BY-3.0 ", "CC-BY-2.0"])
def test_cc0_and_cc_by_are_eligible(spdx):
    assert classify(spdx).verdict is Verdict.ELIGIBLE


@pytest.mark.parametrize(
    "spdx", ["CC-BY-SA-4.0", "CC-BY-SA-3.0", "CC-BY-NC-4.0", "CC-BY-ND-4.0", "CC-BY-NC-SA-4.0", "CC-BY-NC-ND-4.0"]
)
def test_share_alike_non_commercial_and_no_derivatives_are_excluded(spdx):
    assert classify(spdx).verdict is Verdict.EXCLUDED
    assert (
        "share-alike, non-commercial and no-derivatives" in classify(spdx).reason
    )  # the user is told the right reason


@pytest.mark.parametrize("spdx", ["", "   ", None, "unknown", "Unclear", "other", "custom", "NOASSERTION"])
def test_missing_or_unclear_licences_are_excluded(spdx):
    assert classify(spdx).verdict is Verdict.EXCLUDED


@pytest.mark.parametrize("spdx", ["MIT", "Apache-2.0", "ODbL-1.0", "Kaggle-default-terms"])
def test_other_licences_cannot_be_approved_by_the_application(spdx):
    assert classify(spdx).verdict is Verdict.NEEDS_REVIEW


def test_an_unrecognised_creative_commons_variant_is_excluded_not_trusted():
    assert classify("CC-BY-9.9").verdict is Verdict.EXCLUDED
    assert classify("CC-PDDC").verdict is Verdict.EXCLUDED


GOOD = DatasetFacts(
    name="Example",
    version="1",
    kind="real",
    source_url="https://data.example.org/ds",
    accessed_at=NOW,
    licence_spdx="CC-BY-4.0",
    images_licence_spdx="CC-BY-4.0",
    annotations_licence_spdx="CC-BY-4.0",
    has_annotations=True,
    attribution_required=True,
    attribution_text="Doe et al. 2024",
    commercial_use="yes",
    redistribution="yes",
    intended_use="Research baseline for leaf-condition classification",
    image_origin="publisher_created",
)


def ev(**over) -> Evidence:
    base = dict(
        url="https://data.example.org/licence",
        kind="licence_page",
        scope="both",
        licence_spdx="CC-BY-4.0",
        excerpt="This dataset is released under CC BY 4.0",
        official=True,
        accessed_at=NOW,
    )
    base.update(over)
    return Evidence(**base)  # type: ignore[arg-type]


def test_a_fully_evidenced_cc_by_dataset_has_no_blockers():
    assert approval_blockers(GOOD, [ev()]) == []


def test_a_cc0_dataset_without_attribution_needs_no_attribution_text():
    cc0 = replace(GOOD, licence_spdx="CC0-1.0", images_licence_spdx="CC0-1.0", annotations_licence_spdx="CC0-1.0",
                  attribution_required=False, attribution_text=None)  # fmt: skip
    assert approval_blockers(cc0, [ev(licence_spdx="CC0-1.0")]) == []


def test_no_evidence_blocks_approval():
    assert any("no licence evidence" in b for b in approval_blockers(GOOD, []))


def test_evidence_from_a_secondary_source_is_not_enough():
    blockers = approval_blockers(GOOD, [ev(official=False)])
    assert any("official-source evidence" in b and "images" in b for b in blockers)
    assert any("official-source evidence" in b and "annotations" in b for b in blockers)


def test_evidence_must_quote_the_licence_statement():
    assert any("quoted licence statement" in b for b in approval_blockers(GOOD, [ev(excerpt="   ")]))


def test_annotations_need_their_own_evidence_when_present():
    only_images = [ev(scope="images")]
    blockers = approval_blockers(GOOD, only_images)
    assert any("covers the annotations" in b for b in blockers)
    assert not any("covers the images" in b for b in blockers)
    no_annotations = replace(GOOD, has_annotations=False, annotations_licence_spdx=None)
    assert approval_blockers(no_annotations, only_images) == []


def test_conflicting_evidence_blocks_approval_even_if_one_source_agrees():
    """The PlantVillage situation: one source says CC0, another says CC BY-SA."""
    cc0 = replace(GOOD, licence_spdx="CC0-1.0", images_licence_spdx="CC0-1.0", annotations_licence_spdx="CC0-1.0",
                  attribution_required=False)  # fmt: skip
    blockers = approval_blockers(
        cc0, [ev(licence_spdx="CC0-1.0"), ev(licence_spdx="CC-BY-SA-3.0", url="https://other.example.org/p")]
    )
    assert any("contradicts" in b and "CC-BY-SA-3.0" in b for b in blockers)


def test_an_excluded_image_licence_blocks_even_when_the_annotation_licence_is_fine():
    mixed = replace(GOOD, images_licence_spdx="CC-BY-NC-4.0")
    blockers = approval_blockers(mixed, [ev(licence_spdx="CC-BY-NC-4.0", scope="images"), ev(scope="annotations")])
    assert any(b.startswith("images licence") for b in blockers)


@pytest.mark.parametrize(
    ("field", "value", "fragment"),
    [
        ("source_url", "http://data.example.org/ds", "https"),
        ("source_url", "", "https"),
        ("accessed_at", None, "access date"),
        ("intended_use", "  ", "intended use"),
        ("commercial_use", "unknown", "commercial use"),
        ("commercial_use", "no", "commercial use"),
        ("redistribution", "unknown", "redistribution"),
        ("attribution_required", None, "whether attribution is required"),
        ("attribution_text", "", "attribution text"),
    ],
)
def test_each_missing_fact_is_named(field, value, fragment):
    blockers = approval_blockers(replace(GOOD, **{field: value}), [ev()])
    assert any(fragment in b for b in blockers), blockers


@pytest.mark.parametrize("origin", ["third_party_scraped", "unknown"])
def test_scraped_or_unknown_image_origin_blocks_approval_whatever_the_declared_licence(origin):
    """The PlantDoc situation: the repository says CC BY 4.0 but the images were scraped from search engines."""
    blockers = approval_blockers(replace(GOOD, image_origin=origin), [ev()])
    assert any("image origin" in b and origin in b for b in blockers), blockers


def test_third_party_images_are_acceptable_only_when_the_publisher_documents_their_licences():
    assert approval_blockers(replace(GOOD, image_origin="third_party_licensed"), [ev()]) == []


def test_evidence_needs_an_https_url_and_an_access_date():
    blockers = approval_blockers(GOOD, [ev(url="http://insecure.example.org/l"), ev(accessed_at=None)])
    assert any("not an https URL" in b for b in blockers) and any("no access date" in b for b in blockers)


def test_synthetic_fixtures_need_no_licence_and_are_never_biological():
    synthetic = replace(
        GOOD,
        kind="synthetic",
        licence_spdx="SYNTHETIC",
        images_licence_spdx="SYNTHETIC",
        source_url="synthetic://generated",
    )
    assert approval_blockers(synthetic, []) == []


def test_policy_has_no_override_hook():
    assert not any("override" in n.lower() or "force" in n.lower() for n in dir(licences) if not n.startswith("_"))

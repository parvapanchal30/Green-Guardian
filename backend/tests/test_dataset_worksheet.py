"""The candidate-dataset worksheet in docs/datasets/candidates.json must stay valid input for the API and must stay
honest: every candidate is blocked from approval until the missing evidence is recorded."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.modules.datasets import licences
from app.modules.datasets.schemas import DatasetCreate, EvidenceCreate

WORKSHEET = Path(__file__).resolve().parents[2] / "docs" / "datasets" / "candidates.json"
ENTRIES = json.loads(WORKSHEET.read_text(encoding="utf8"))["entries"]


def blockers_of(entry: dict) -> list[str]:
    c = DatasetCreate(**entry["catalog"])
    facts = licences.DatasetFacts(
        c.name, c.version, c.kind, c.source_url, c.accessed_at, c.licence_spdx, c.images_licence_spdx or c.licence_spdx,
        c.annotations_licence_spdx, c.has_annotations, c.attribution_required, c.attribution_text, c.commercial_use,
        c.redistribution, c.intended_use, c.image_origin,
    )  # fmt: skip
    ev = [EvidenceCreate(**e) for e in entry["evidence"]]
    return licences.approval_blockers(
        facts,
        [licences.Evidence(e.url, e.kind, e.scope, e.licence_spdx, e.excerpt, e.official, e.accessed_at) for e in ev],
    )


def test_the_worksheet_is_valid_api_input():
    assert len(ENTRIES) >= 4
    for entry in ENTRIES:
        DatasetCreate(**entry["catalog"])
        for e in entry["evidence"]:
            EvidenceCreate(**e)


@pytest.mark.parametrize("entry", ENTRIES, ids=lambda e: e["catalog"]["name"])
def test_no_candidate_is_approvable_as_it_stands(entry):
    assert blockers_of(entry), (
        f"{entry['catalog']['name']} would be approvable: check the evidence before relying on it"
    )


def test_only_pages_actually_read_carry_evidence():
    for entry in ENTRIES:
        if not entry["read_directly"]:
            assert entry["evidence"] == [], "evidence must not be recorded for a page that was not read"


def test_plantdoc_is_blocked_for_its_image_rights_and_unconfirmed_commercial_use():
    plantdoc = next(e for e in ENTRIES if e["catalog"]["name"] == "PlantDoc")
    blockers = blockers_of(plantdoc)
    assert any("image origin" in b and "third_party_scraped" in b for b in blockers)
    assert any("commercial use" in b for b in blockers)
    assert (
        plantdoc["evidence"][0]["official"] is True
    )  # the licence statement itself WAS read at the official repository


def test_unresolved_licences_are_excluded_by_policy():
    for entry in ENTRIES:
        if entry["catalog"]["licence_spdx"] == "unknown":
            assert licences.classify(entry["catalog"]["licence_spdx"]).verdict is licences.Verdict.EXCLUDED

"""The candidate worksheet (docs/datasets/candidates.json) must stay valid API input and must stay honest: no candidate is
approvable until the missing questions are answered, and the importer loads it through the real service code."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from app.modules.datasets import licences
from app.modules.datasets.models import Dataset, DatasetEvidence
from app.modules.datasets.schemas import DatasetCreate
from app.tools import dataset_worksheet as ws_tool

WORKSHEET = Path(__file__).resolve().parents[2] / "docs" / "datasets" / "candidates.json"
ENTRIES = json.loads(WORKSHEET.read_text(encoding="utf8"))["entries"]
HOW = {"read_in_full_text", "page_reader_tool_quote", "api_json_field"}


def by_id(entry_id: str) -> dict:
    return next(e for e in ENTRIES if e["id"] == entry_id)


def blockers_of(entry: dict) -> list[str]:
    return ws_tool.blockers(DatasetCreate(**entry["catalog"]), [ws_tool.evidence_payload(e) for e in entry["evidence"]])


def test_the_worksheet_is_valid_api_input():
    assert len(ENTRIES) >= 6 and len({e["id"] for e in ENTRIES}) == len(ENTRIES)
    for entry in ENTRIES:
        DatasetCreate(**entry["catalog"])
        for e in entry["evidence"]:
            ws_tool.evidence_payload(e)


@pytest.mark.parametrize("entry", ENTRIES, ids=lambda e: e["id"])
def test_no_candidate_is_approvable_as_it_stands(entry):
    assert blockers_of(entry), f"{entry['id']} would be approvable: confirm the evidence before relying on it"


@pytest.mark.parametrize("entry", ENTRIES, ids=lambda e: e["id"])
def test_every_evidence_record_says_how_it_was_verified_and_every_entry_lists_open_questions(entry):
    assert all(e["verified_how"] in HOW for e in entry["evidence"])
    assert entry["unresolved"], "an entry with no open question should be re-checked before it is trusted"


def test_the_two_excluded_candidates_stay_excluded():
    pv = by_id("plantvillage")
    assert licences.classify(pv["catalog"]["licence_spdx"]).verdict is licences.Verdict.EXCLUDED
    assert any("share-alike" in blk or "licence" in blk for blk in blockers_of(pv))
    assert by_id("plantdoc")["catalog"]["image_origin"] == "third_party_scraped"
    assert any("image origin" in blk for blk in blockers_of(by_id("plantdoc")))


def test_licence_verified_candidates_are_blocked_only_by_image_origin_not_by_the_licence():
    for entry_id in ("cassava-mendeley", "irish-potato-tanzania"):
        blk = blockers_of(by_id(entry_id))
        assert len(blk) == 1 and "image origin" in blk[0], (entry_id, blk)


def test_conflicting_licence_statements_are_recorded_and_block_the_tomato_set():
    blk = blockers_of(by_id("tomato-greenhouse-mendeley"))
    assert any("contradicts" in b and "CC-BY-NC-4.0" in b for b in blk)


def test_plantnet_images_licences_are_unknown_so_it_is_excluded_by_policy():
    blk = blockers_of(by_id("plantnet-300k"))
    assert any(b.startswith("images licence") for b in blk)


# ------------------------------------------------------------------------------------------------ the importer
def test_the_importer_loads_candidates_as_proposed_with_evidence_and_is_idempotent(team, world):
    ws = uuid.UUID(team.ws)
    entries = ws_tool.load(WORKSHEET)
    with world.db() as db:
        dry = ws_tool.run(db, ws, team.manager.email, entries, apply=False)
        assert {r["action"] for r in dry} == {"would create (dry run)"}
        assert db.scalar(select(Dataset)) is None  # a dry run writes nothing
        done = ws_tool.run(db, ws, team.manager.email, entries, apply=True)
        assert {r["action"] for r in done} == {"created as proposed"}
        assert {d.status for d in db.scalars(select(Dataset))} == {"proposed"}  # nothing is approved
        again = ws_tool.run(db, ws, team.manager.email, entries, apply=True)
        assert {r["action"] for r in again} == {"skipped: already in the catalog"}
        rows = list(db.scalars(select(DatasetEvidence)))
        assert len(rows) == sum(len(e["evidence"]) for e in entries)
        assert all(r.recorded_by == team.manager.id and "[verified: " in r.excerpt for r in rows)


def test_the_loaded_catalog_reports_the_same_blockers_through_the_api(team, world, api_for):
    with world.db() as db:
        ws_tool.run(db, uuid.UUID(team.ws), team.manager.email, ws_tool.load(WORKSHEET), apply=True)
    items = {d["name"]: d for d in api_for(team.viewer).get("/datasets", params={"limit": 50}).json()["items"]}
    cassava = items["Cassava Leaf Disease Dataset (Mendeley)"]
    assert cassava["status"] == "proposed" and cassava["download_allowed"] is False
    assert len(cassava["blockers"]) == 1 and "image origin" in cassava["blockers"][0]
    assert items["PlantVillage"]["licence_verdict"] == "excluded" and items["PlantDoc"]["download_allowed"] is False


def test_the_importer_refuses_users_without_the_manager_role_and_unknown_inputs(team, world):
    with world.db() as db:
        for who in (team.viewer, team.worker, team.outsider):
            with pytest.raises(ws_tool.WorksheetError):
                ws_tool.run(db, uuid.UUID(team.ws), who.email, [], apply=True)
        with pytest.raises(ws_tool.WorksheetError):
            ws_tool.run(db, uuid.uuid4(), team.manager.email, [], apply=True)
        with pytest.raises(ws_tool.WorksheetError):
            ws_tool.run(db, uuid.UUID(team.ws), "nobody@example.com", [], apply=True)

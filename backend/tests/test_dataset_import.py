"""CSV import of dataset samples: parsing, validation, atomicity, retry, authorization, tenancy, audit, and the guarantee that
imports never create validated labels and never touch review history or split versions. Synthetic data only."""

from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import func, select

from app.modules.audit.models import AuditEvent
from app.modules.datasets import importer
from app.modules.datasets.models import DatasetSample, LabelReview
from tests.test_datasets_api import approved_real, real, sample_ids, synthetic

HEADER = "external_id,group_key,label,content_sha256,phash,file_status,width,height,source"


def sha(i: int) -> str:
    return hashlib.sha256(f"imp-{i}".encode()).hexdigest()


def line(i: int, **over) -> str:
    cells = {
        "external_id": f"img-{i:04d}", "group_key": f"plant-{i % 6}", "label": ("blight", "rust")[i % 2], "content_sha256": sha(i),
        "phash": f"{i:016x}", "file_status": "ok", "width": "128", "height": "128", "source": "synthetic generator",
    }  # fmt: skip
    cells.update(over)
    return ",".join(str(cells[c]) for c in HEADER.split(","))


def make_csv(n: int = 12, **over) -> str:
    return "\n".join([HEADER, *(line(i, **over) for i in range(n))]) + "\n"


def codes(parsed) -> set[str]:
    return {e["code"] for e in parsed.file_errors} | {e["code"] for r in parsed.rows for e in r.errors}


# ------------------------------------------------------------------------------------------------ the parser
def test_a_valid_file_parses_into_unreviewed_metadata_rows():
    p = importer.parse(make_csv(5))
    assert p.file_errors == [] and len(p.rows) == 5 and all(not r.errors for r in p.rows)
    row = p.rows[0].data
    assert (
        row["external_id"] == "img-0000"
        and row["width"] == 128
        and row["provenance"] == {"source": "synthetic generator", "imported_from": "csv"}
    )
    assert "label_status" not in row  # review state is never part of an imported row


def test_a_byte_order_mark_blank_lines_and_header_case_are_tolerated():
    text = "﻿" + HEADER.upper() + "\n\n" + line(1) + "\n\n"
    p = importer.parse(text)
    assert p.file_errors == [] and len(p.rows) == 1


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("", "empty_file"),
        ("\n\n  \n", "empty_file"),
        ("a,b\n1,2\x00\n", "binary_content"),
        ('external_id,source\n"unterminated,x\n', "malformed_csv"),
        ("group_key,source\nx,y\n", "missing_column"),
        ("external_id,group_key\nimg-1,g\n", "missing_column"),  # no source column for a real dataset
        ("external_id,source,source\nimg-1,a,b\n", "duplicate_columns"),
        ("external_id,source,colour\nimg-1,a,red\n", "unknown_columns"),
    ],
)
def test_file_level_problems_are_reported_and_nothing_is_parsed(text, code):
    p = importer.parse(text)
    assert code in codes(p) and p.rows == []


@pytest.mark.parametrize(
    "column", ["label_status", "reviewed", "validated", "reviewer", "status", "verified", "expert", "is_synthetic"]
)
def test_review_state_can_never_be_imported(column):
    p = importer.parse(f"external_id,source,{column}\nimg-1,a,accepted\n")
    assert "review_state_not_importable" in codes(p) and p.rows == []
    assert "unreviewed" in next(e for e in p.file_errors if e["code"] == "review_state_not_importable")["message"]


def test_oversized_files_and_row_counts_are_refused(monkeypatch):
    monkeypatch.setattr(importer, "MAX_ROWS", 3)
    assert "too_many_rows" in codes(importer.parse(make_csv(4)))
    monkeypatch.setattr(importer, "MAX_BYTES", 50)
    assert "file_too_large" in codes(importer.parse(make_csv(5)))


def test_row_errors_name_the_row_the_column_and_the_problem():
    text = "\n".join([
        HEADER,
        line(1, content_sha256="not-a-hash"),  # row 1
        line(2, phash="zz"),  # row 2
        line(3, file_status="maybe"),  # row 3
        line(4, width="-5"),  # row 4
        line(5, height="12.5"),  # row 5
        line(6, source=""),  # row 6
        line(7, external_id=""),  # row 7
        line(8, label="x" * 121),  # row 8
        "img-9,only,three",  # row 9
        line(10, label="bad\x07control"),  # row 10
    ])  # fmt: skip
    p = importer.parse(text)
    found = {(r.number, e["code"], e.get("column")) for r in p.rows for e in r.errors}
    assert found >= {
        (1, "invalid_value", "content_sha256"), (2, "invalid_value", "phash"), (3, "invalid_value", "file_status"),
        (4, "invalid_value", "width"), (5, "invalid_value", "height"), (6, "missing_provenance", "source"),
        (7, "missing_value", "external_id"), (8, "too_long", "label"), (9, "wrong_field_count", None), (10, "control_characters", "label"),
    }  # fmt: skip


def test_duplicate_identifiers_inside_the_file_point_at_the_first_occurrence():
    p = importer.parse("\n".join([HEADER, line(1), line(2), line(1, label="other")]))
    err = [e for r in p.rows for e in r.errors if e["code"] == "duplicate_in_file"]
    assert len(err) == 1 and "row 1" in err[0]["message"]


def test_provenance_is_optional_only_for_synthetic_datasets():
    text = "external_id,group_key,label\nimg-1,g,a\n"
    assert "missing_column" in codes(importer.parse(text, require_source=True))
    ok = importer.parse(text, require_source=False)
    assert ok.file_errors == [] and ok.rows[0].data["provenance"] == {"imported_from": "csv"}


def test_warnings_are_aggregated_not_errors():
    text = "\n".join(
        [
            HEADER,
            line(1, group_key=""),
            line(2, group_key=""),
            line(3, label=""),
            line(4, label="=SUM(A1)"),
            line(5, content_sha256=sha(1)),
        ]
    )
    p = importer.parse(text)
    w = {x["code"]: x for x in p.warnings}
    assert (
        w["missing_group"]["count"] == 2 and w["missing_label"]["count"] == 1 and w["formula_like_cell"]["count"] == 1
    )
    assert w["identical_files_in_file"]["count"] == 2
    assert not p.file_errors and all(not r.errors for r in p.rows)


def test_uppercase_hashes_are_normalised_and_the_template_is_valid():
    p = importer.parse(make_csv(1, content_sha256=sha(1).upper()))
    assert p.rows[0].data["content_sha256"] == sha(1)
    header_only = importer.parse(importer.TEMPLATE)
    assert header_only.file_errors == [] and header_only.rows == []


# ------------------------------------------------------------------------------------------------ the endpoint
def imp(api, ds_id, csv_text, commit=False):
    return api.post(f"/datasets/{ds_id}/samples/import", {"csv_text": csv_text, "commit": commit})


def count(world, ds_id=None) -> int:
    with world.db() as db:
        return db.scalar(select(func.count()).select_from(DatasetSample)) or 0


def synth(api, name="Fixtures"):
    return api.post("/datasets", synthetic(name=name)).json()


def test_a_preview_validates_and_writes_nothing(api_for, team, world):
    manager = api_for(team.manager)
    ds = synth(manager)
    r = imp(manager, ds["id"], make_csv(8))
    assert r.status_code == 200
    out = r.json()
    assert out["status"] == "preview" and out["ok"] is True and out["to_create"] == 8 and out["unchanged"] == 0
    assert out["label_status_after_import"] == "unreviewed" and len(out["csv_sha256"]) == 64
    assert count(world) == 0


def test_a_commit_registers_every_row_as_unreviewed_with_provenance_and_audits_it(api_for, team, world):
    manager = api_for(team.manager)
    ds = synth(manager)
    r = imp(manager, ds["id"], make_csv(12), commit=True)
    assert r.status_code == 200 and r.json()["status"] == "imported" and r.json()["to_create"] == 12
    items = manager.get(f"/datasets/{ds['id']}/samples", params={"limit": 200}).json()["items"]
    assert len(items) == 12 and {s["label_status"] for s in items} == {"unreviewed"}
    assert all(s["is_synthetic"] and s["provenance"]["imported_from"] == "csv" for s in items)
    assert (
        manager.get(f"/datasets/{ds['id']}/review-summary").json()["reviewed_fraction"] == 0.0
    )  # nothing counts as validated
    with world.db() as db:
        ev = db.scalar(select(AuditEvent).where(AuditEvent.action == "dataset.samples.import"))
        assert ev is not None and ev.actor_id == team.manager.id and ev.workspace_id.hex == team.ws.replace("-", "")
        assert ev.details["created"] == 12 and ev.details["csv_sha256"] == r.json()["csv_sha256"]


def test_one_bad_row_means_nothing_is_imported(api_for, team, world):
    manager = api_for(team.manager)
    ds = synth(manager)
    text = make_csv(10) + line(99, content_sha256="bad") + "\n"
    r = imp(manager, ds["id"], text, commit=True)
    assert r.status_code == 422 and r.json()["code"] == "import_invalid"
    report = r.json()["report"]
    assert report["ok"] is False and report["to_create"] == 0 and report["error_count"] == 1
    assert (
        report["errors"][0]["row"] == 11
        and report["errors"][0]["column"] == "content_sha256"
        and report["errors"][0]["external_id"] == "img-0099"
    )
    assert count(world) == 0  # the ten good rows were not imported either
    with world.db() as db:
        assert db.scalar(select(AuditEvent).where(AuditEvent.action == "dataset.samples.import")) is None


def test_retrying_the_same_file_is_safe_and_changes_nothing(api_for, team, world):
    manager = api_for(team.manager)
    ds = synth(manager)
    text = make_csv(7)
    assert imp(manager, ds["id"], text, commit=True).json()["status"] == "imported"
    again = imp(manager, ds["id"], text, commit=True)
    assert again.status_code == 200 and again.json()["status"] == "already_imported" and again.json()["unchanged"] == 7
    assert count(world) == 7
    preview = imp(manager, ds["id"], text).json()
    assert preview["to_create"] == 0 and preview["unchanged"] == 7 and preview["ok"] is True


def test_an_extended_file_adds_only_the_new_rows(api_for, team, world):
    manager = api_for(team.manager)
    ds = synth(manager)
    imp(manager, ds["id"], make_csv(5), commit=True)
    r = imp(manager, ds["id"], make_csv(8), commit=True).json()
    assert r["status"] == "imported" and r["unchanged"] == 5 and r["to_create"] == 3 and count(world) == 8


def test_a_row_that_exists_with_different_values_is_an_error_and_blocks_the_whole_file(api_for, team, world):
    manager = api_for(team.manager)
    ds = synth(manager)
    imp(manager, ds["id"], make_csv(4), commit=True)
    changed = "\n".join([HEADER, line(0, label="different"), line(50), line(51)]) + "\n"
    r = imp(manager, ds["id"], changed, commit=True)
    assert r.status_code == 422
    err = r.json()["report"]["errors"][0]
    assert err["code"] == "exists_with_different_values" and "label" in err["message"] and err["row"] == 1
    assert count(world) == 4  # the two new rows were not added either


def test_import_never_overwrites_a_reviewed_label_and_review_history_is_untouched(api_for, team, world):
    manager = api_for(team.manager)
    ds = synth(manager)
    imp(manager, ds["id"], make_csv(6), commit=True)
    sid = sample_ids(manager, ds["id"])[0]
    url = f"/datasets/{ds['id']}/samples/{sid}/reviews"
    manager.post(url, {"to_status": "under_review"})
    manager.post(url, {"to_status": "corrected", "to_label": "mildew", "evidence": "checked against the source record"})
    with world.db() as db:
        before = db.scalar(select(func.count()).select_from(LabelReview))
    r = imp(manager, ds["id"], make_csv(6), commit=True)  # the file still says the old label
    assert r.status_code == 422 and r.json()["report"]["errors"][0]["code"] == "exists_with_different_values"
    row = next(s for s in manager.get(f"/datasets/{ds['id']}/samples").json()["items"] if s["id"] == sid)
    assert row["label"] == "mildew" and row["label_status"] == "corrected"  # the review stands
    with world.db() as db:
        assert db.scalar(select(func.count()).select_from(LabelReview)) == before


def test_importing_never_changes_existing_split_versions(api_for, team):
    manager = api_for(team.manager)
    ds = synth(manager)
    imp(manager, ds["id"], make_csv(60), commit=True)
    first = manager.post(f"/datasets/{ds['id']}/splits", {"include_unreviewed": True, "seed": 1}).json()
    imp(manager, ds["id"], make_csv(90), commit=True)
    after = manager.get(f"/datasets/{ds['id']}/splits/1").json()
    assert after["manifest_sha256"] == first["manifest_sha256"] and after["manifest"] == first["manifest"]
    assert [s["version"] for s in manager.get(f"/datasets/{ds['id']}/splits").json()] == [
        1
    ]  # no split was created or replaced


def test_forbidden_review_columns_are_refused_by_the_server(api_for, team, world):
    manager = api_for(team.manager)
    ds = synth(manager)
    text = "external_id,source,label_status\nimg-1,synthetic generator,accepted\n"
    r = imp(manager, ds["id"], text)
    assert (
        r.status_code == 200
        and r.json()["ok"] is False
        and r.json()["errors"][0]["code"] == "review_state_not_importable"
    )
    assert imp(manager, ds["id"], text, commit=True).status_code == 422 and count(world) == 0


def test_malformed_files_return_a_report_not_a_server_error(api_for, team):
    manager = api_for(team.manager)
    ds = synth(manager)
    for text in ('external_id,source\n"broken,x\n', "external_id,source\nimg-1,a,extra\n", "a\x00b"):
        r = imp(manager, ds["id"], text)
        assert r.status_code == 200 and r.json()["ok"] is False, text
    url = f"/datasets/{ds['id']}/samples/import"
    assert manager.post(url, {"csv_text": ""}).status_code == 422  # schema: not empty
    assert manager.post(url, {"csv_text": "   \n"}).status_code == 422  # blank after trimming
    assert manager.post(f"/datasets/{ds['id']}/samples/import", {"csv_text": "x", "approved": True}).status_code == 422


def test_a_real_dataset_must_be_approved_and_needs_provenance(api_for, team):
    manager, owner = api_for(team.manager), api_for(team.owner)
    candidate = manager.post("/datasets", real(name="Candidate")).json()
    r = imp(manager, candidate["id"], make_csv(3), commit=True)
    assert r.status_code == 409 and r.json()["code"] == "dataset_not_approved"
    ok = approved_real(manager, owner, name="Approved real")
    no_source = "external_id,group_key,label\nimg-1,g,a\n"
    assert imp(manager, ok["id"], no_source).json()["errors"][0]["code"] == "missing_column"
    assert imp(manager, ok["id"], make_csv(3), commit=True).json()["status"] == "imported"


def test_only_managers_can_import_or_preview(api_for, team, world):
    manager = api_for(team.manager)
    ds = synth(manager)
    for member in (team.worker, team.viewer):
        for commit in (False, True):
            assert imp(api_for(member), ds["id"], make_csv(2), commit=commit).status_code == 403
    assert count(world) == 0


def test_another_workspace_cannot_import_into_or_probe_a_dataset(api_for, team, world):
    manager = api_for(team.manager)
    ds = synth(manager)
    theirs = api_for(team.other_owner, team.other_ws)
    for commit in (False, True):
        r = imp(theirs, ds["id"], make_csv(2), commit=commit)
        assert r.status_code == 404 and r.json()["code"] == "dataset_not_found"
    assert count(world) == 0
    own = theirs.post("/datasets", synthetic()).json()  # the same names are independent per tenant
    assert imp(theirs, own["id"], make_csv(2), commit=True).json()["status"] == "imported"
    assert manager.get(f"/datasets/{ds['id']}/samples").json()["total"] == 0


def test_error_reports_are_capped_but_counted(api_for, team):
    manager = api_for(team.manager)
    ds = synth(manager)
    out = imp(manager, ds["id"], make_csv(260, content_sha256="bad")).json()
    assert (
        out["error_count"] == 260
        and len(out["errors"]) == 200
        and out["errors_truncated"] is True
        and out["to_create"] == 0
    )


def test_imported_samples_flow_into_quality_checks_and_are_flagged_there(api_for, team):
    manager = api_for(team.manager)
    ds = synth(manager)
    imp(manager, ds["id"], make_csv(30, label=""), commit=True)
    q = manager.get(f"/datasets/{ds['id']}/quality").json()
    assert {"missing_labels", "no_reviewed_labels"} <= {i["code"] for i in q["issues"]} and q[
        "reviewed_fraction"
    ] == 0.0

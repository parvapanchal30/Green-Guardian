"""Dataset catalog, licence approval, label review, quality, splits, claim readiness. SYNTHETIC data only: samples here
are rows with made-up names; nothing in this file is, or stands for, real plant imagery."""

from __future__ import annotations

import hashlib
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.modules.audit import denied
from app.modules.datasets.models import DatasetSample, DatasetSplit
from tests.conftest import requires_pg_mode
from tests.helpers import ago


@pytest.fixture(autouse=True)
def _fresh_denial_dedupe():
    """Denied-access events are de-duplicated per process; start each test with an empty window."""
    denied.reset_dedupe()
    yield
    denied.reset_dedupe()


def real(**over) -> dict:
    base = {
        "name": "Example leaf set", "version": "1", "kind": "real", "source_url": "https://data.example.org/leaves",
        "accessed_at": ago(days=1), "licence_spdx": "CC-BY-4.0", "has_annotations": False, "image_origin": "publisher_created", "attribution_required": True,
        "attribution_text": "Doe et al. 2024", "commercial_use": "yes", "redistribution": "yes",
        "intended_use": "Research baseline for leaf-condition classification",
    }  # fmt: skip
    base.update(over)
    return base


def evidence(**over) -> dict:
    base = {
        "url": "https://data.example.org/leaves/LICENSE", "kind": "licence_page", "scope": "images",
        "licence_spdx": "CC-BY-4.0", "excerpt": "Released under the Creative Commons Attribution 4.0 licence",
        "official": True, "accessed_at": ago(hours=2),
    }  # fmt: skip
    base.update(over)
    return base


def synthetic(**over) -> dict:
    base = {
        "name": "Synthetic fixtures",
        "version": "1",
        "kind": "synthetic",
        "source_url": "synthetic://generated",
        "licence_spdx": "n/a",
    }
    base.update(over)
    return base


def sha(i: int) -> str:
    return hashlib.sha256(f"synthetic-{i}".encode()).hexdigest()


def sample(i: int, group: str | None = None, label: str | None = "x", **over) -> dict:
    return {
        "external_id": f"s{i:04d}", "group_key": group or f"g{i % 12}", "label": label, "content_sha256": sha(i),
        "file_status": "ok", "width": 128, "height": 128, "provenance": {"source": "synthetic generator"}, **over,
    }  # fmt: skip


def approved_real(manager, owner, **over) -> dict:
    ds = manager.post("/datasets", real(**over)).json()
    assert manager.post(f"/datasets/{ds['id']}/evidence", evidence()).status_code == 201
    assert manager.post(f"/datasets/{ds['id']}/transitions", {"to_status": "under_review"}).status_code == 200
    r = owner.post(f"/datasets/{ds['id']}/transitions", {"to_status": "approved"})
    assert r.status_code == 200, r.text
    return r.json()


def synthetic_set(manager, n: int = 36, labels=("a", "b", "c")) -> dict:
    ds = manager.post("/datasets", synthetic()).json()
    rows = [sample(i, label=labels[i % len(labels)]) for i in range(n)]
    assert manager.post(f"/datasets/{ds['id']}/samples", {"samples": rows}).status_code == 201
    return ds


def sample_ids(api, ds_id: str, **params) -> list[str]:
    items = api.get(f"/datasets/{ds_id}/samples", params={"limit": 200, **params}).json()["items"]
    return [s["id"] for s in items]


def accept_all(manager, ds_id: str) -> None:
    for sid in sample_ids(manager, ds_id):
        assert (
            manager.post(f"/datasets/{ds_id}/samples/{sid}/reviews", {"to_status": "under_review"}).status_code == 201
        )
        r = manager.post(
            f"/datasets/{ds_id}/samples/{sid}/reviews",
            {"to_status": "accepted", "evidence": "Checked against the source image"},
        )
        assert r.status_code == 201, r.text


# ------------------------------------------------------------------------------------------------ catalog
def test_the_policy_endpoint_states_the_rules_and_that_there_is_no_override(api_for, team):
    policy = api_for(team.viewer).get("/datasets/licence-policy").json()
    assert "CC0-1.0" in policy["eligible"] and "CC-BY-4.0" in policy["eligible"]
    assert any("CC BY-SA" in x for x in policy["excluded"]) and "none" in policy["override"]
    assert "approved" in policy["download_rule"]


def test_only_managers_can_propose_a_dataset_and_everyone_can_read(api_for, team):
    manager = api_for(team.manager)
    r = manager.post("/datasets", real())
    assert r.status_code == 201, r.text
    ds = r.json()
    assert ds["status"] == "proposed" and ds["licence_verdict"] == "eligible" and ds["download_allowed"] is False
    assert ds["created_by"] == str(team.manager.id) and ds["history"][0]["to_status"] == "proposed"
    assert any("no licence evidence" in b for b in ds["blockers"])
    for member in (team.worker, team.viewer):
        assert api_for(member).post("/datasets", real(name="Other")).status_code == 403
    assert api_for(team.viewer).get(f"/datasets/{ds['id']}").status_code == 200
    assert api_for(team.viewer).get("/datasets").json()["total"] == 1


def test_a_name_and_version_is_unique_and_a_new_version_is_a_new_record(api_for, team):
    manager = api_for(team.manager)
    manager.post("/datasets", real())
    dup = manager.post("/datasets", real())
    assert dup.status_code == 409 and dup.json()["code"] == "dataset_exists"
    assert manager.post("/datasets", real(version="2")).status_code == 201


def test_unknown_fields_are_rejected(api_for, team):
    assert api_for(team.manager).post("/datasets", real(approved=True)).status_code == 422


@pytest.mark.parametrize("spdx", ["CC-BY-SA-4.0", "CC-BY-NC-4.0", "CC-BY-ND-4.0", "unclear", "Kaggle-default-terms"])
def test_a_dataset_with_an_excluded_or_unapproved_licence_can_never_be_approved(api_for, team, spdx):
    manager, owner = api_for(team.manager), api_for(team.owner)
    ds = manager.post("/datasets", real(licence_spdx=spdx)).json()
    manager.post(f"/datasets/{ds['id']}/evidence", evidence(licence_spdx=spdx))
    manager.post(f"/datasets/{ds['id']}/transitions", {"to_status": "under_review"})
    r = owner.post(f"/datasets/{ds['id']}/transitions", {"to_status": "approved"})
    assert r.status_code == 422 and r.json()["code"] == "dataset_not_approvable"
    assert any("licence" in b for b in r.json()["blockers"])
    assert owner.get(f"/datasets/{ds['id']}").json()["status"] == "under_review"
    assert owner.get(f"/datasets/{ds['id']}").json()["download_allowed"] is False


@pytest.mark.parametrize("origin", ["third_party_scraped", "unknown"])
def test_images_scraped_from_third_parties_cannot_be_approved_even_with_perfect_licence_evidence(api_for, team, origin):
    manager, owner = api_for(team.manager), api_for(team.owner)
    ds = manager.post("/datasets", real(image_origin=origin)).json()
    manager.post(f"/datasets/{ds['id']}/evidence", evidence())
    manager.post(f"/datasets/{ds['id']}/transitions", {"to_status": "under_review"})
    r = owner.post(f"/datasets/{ds['id']}/transitions", {"to_status": "approved"})
    assert r.status_code == 422 and any("image origin" in b for b in r.json()["blockers"])
    assert owner.get(f"/datasets/{ds['id']}").json()["image_origin"] == origin


def test_conflicting_evidence_blocks_approval(api_for, team):
    manager, owner = api_for(team.manager), api_for(team.owner)
    ds = manager.post(
        "/datasets", real(licence_spdx="CC0-1.0", attribution_required=False, attribution_text=None)
    ).json()
    manager.post(f"/datasets/{ds['id']}/evidence", evidence(licence_spdx="CC0-1.0"))
    manager.post(
        f"/datasets/{ds['id']}/evidence",
        evidence(licence_spdx="CC-BY-SA-3.0", url="https://paper.example.org/p", kind="paper"),
    )
    manager.post(f"/datasets/{ds['id']}/transitions", {"to_status": "under_review"})
    r = owner.post(f"/datasets/{ds['id']}/transitions", {"to_status": "approved"})
    assert r.status_code == 422 and any("contradicts" in b for b in r.json()["blockers"])


def test_evidence_must_be_https_and_quote_something(api_for, team):
    manager = api_for(team.manager)
    ds = manager.post("/datasets", real()).json()
    assert (
        manager.post(f"/datasets/{ds['id']}/evidence", evidence(url="http://insecure.example.org/l")).status_code == 422
    )
    assert manager.post(f"/datasets/{ds['id']}/evidence", evidence(excerpt="short")).status_code == 422


def test_the_full_approval_workflow_records_who_and_when_and_locks_the_evidence(api_for, team):
    manager, owner = api_for(team.manager), api_for(team.owner)
    ds = manager.post("/datasets", real()).json()
    manager.post(f"/datasets/{ds['id']}/evidence", evidence())
    manager.post(f"/datasets/{ds['id']}/transitions", {"to_status": "under_review", "note": "licence page read"})
    denied = manager.post(f"/datasets/{ds['id']}/transitions", {"to_status": "approved"})
    assert denied.status_code == 403  # a licensing decision belongs to an owner or admin
    approved = owner.post(
        f"/datasets/{ds['id']}/transitions", {"to_status": "approved", "note": "verified at source"}
    ).json()
    assert (
        approved["status"] == "approved" and approved["approved_by"] == str(team.owner.id) and approved["approved_at"]
    )
    assert approved["download_allowed"] is True and approved["blockers"] == []
    assert [(h["from_status"], h["to_status"]) for h in approved["history"]] == [
        (None, "proposed"),
        ("proposed", "under_review"),
        ("under_review", "approved"),
    ]
    assert approved["evidence"][0]["official"] is True and approved["evidence"][0]["recorded_by"] == str(
        team.manager.id
    )

    locked = manager.post(f"/datasets/{ds['id']}/evidence", evidence(url="https://data.example.org/other"))
    assert locked.status_code == 409 and locked.json()["code"] == "dataset_locked"
    reopened = manager.post(f"/datasets/{ds['id']}/transitions", {"to_status": "under_review"}).json()
    assert reopened["approved_by"] is None and reopened["download_allowed"] is False
    assert (
        owner.post(f"/datasets/{ds['id']}/transitions", {"to_status": "rejected", "note": "superseded"}).status_code
        == 200
    )
    final = owner.post(f"/datasets/{ds['id']}/transitions", {"to_status": "under_review"})
    assert final.status_code == 409 and final.json()["code"] == "invalid_dataset_transition"  # rejected is terminal


def test_a_dataset_cannot_skip_review(api_for, team):
    manager, owner = api_for(team.manager), api_for(team.owner)
    ds = manager.post("/datasets", real()).json()
    r = owner.post(f"/datasets/{ds['id']}/transitions", {"to_status": "approved"})
    assert r.status_code == 409 and r.json()["allowed"] == ["rejected", "under_review"]


def test_the_denied_approval_is_recorded_in_the_audit_trail(api_for, team):
    manager, owner = api_for(team.manager), api_for(team.owner)
    ds = manager.post("/datasets", real()).json()
    manager.post(f"/datasets/{ds['id']}/transitions", {"to_status": "under_review"})
    manager.post(f"/datasets/{ds['id']}/transitions", {"to_status": "approved"})
    actions = {(e["action"], e["outcome"]) for e in owner.get("/audit", params={"limit": 100}).json()["items"]}
    assert ("dataset.create", "success") in actions and ("dataset.status", "success") in actions
    assert ("access.denied", "denied") in actions


# ------------------------------------------------------------------------------------------------ samples
def test_samples_of_a_real_dataset_cannot_be_registered_until_it_is_approved(api_for, team):
    manager, owner = api_for(team.manager), api_for(team.owner)
    ds = manager.post("/datasets", real()).json()
    r = manager.post(f"/datasets/{ds['id']}/samples", {"samples": [sample(1)]})
    assert r.status_code == 409 and r.json()["code"] == "dataset_not_approved"
    ok = approved_real(manager, owner, name="Approved set")
    assert manager.post(f"/datasets/{ok['id']}/samples", {"samples": [sample(1)]}).status_code == 201


def test_sample_registration_validates_and_rejects_duplicates(api_for, team):
    manager = api_for(team.manager)
    ds = manager.post("/datasets", synthetic()).json()
    url = f"/datasets/{ds['id']}/samples"
    assert manager.post(url, {"samples": [sample(1, content_sha256="nothex")]}).status_code == 422
    assert manager.post(url, {"samples": [sample(1), sample(1)]}).json()["code"] == "duplicate_external_id"
    assert manager.post(url, {"samples": [sample(1)]}).status_code == 201
    again = manager.post(url, {"samples": [sample(1), sample(2)]})
    assert again.status_code == 409 and again.json()["code"] == "sample_exists"
    assert api_for(team.worker).post(url, {"samples": [sample(5)]}).status_code == 403


def test_synthetic_samples_are_flagged_and_the_dataset_is_not_biological(api_for, team):
    manager = api_for(team.manager)
    ds = synthetic_set(manager, 6)
    detail = manager.get(f"/datasets/{ds['id']}").json()
    assert detail["is_biological_data"] is False and detail["download_allowed"] is False and detail["sample_count"] == 6
    page = manager.get(f"/datasets/{ds['id']}/samples").json()
    assert all(s["is_synthetic"] and s["label_status"] == "unreviewed" for s in page["items"])
    assert manager.get(f"/datasets/{ds['id']}/samples", params={"label_status": "accepted"}).json()["total"] == 0


# ------------------------------------------------------------------------------------------------ review
def test_review_workflow_tracks_status_reviewer_time_label_changes_and_evidence(api_for, team):
    manager = api_for(team.manager)
    ds = synthetic_set(manager, 6)
    sid = sample_ids(manager, ds["id"])[0]
    current = next(x for x in manager.get(f"/datasets/{ds['id']}/samples").json()["items"] if x["id"] == sid)["label"]
    url = f"/datasets/{ds['id']}/samples/{sid}/reviews"
    assert (
        manager.post(url, {"to_status": "accepted", "evidence": "looked at it carefully"}).status_code == 409
    )  # must be claimed first
    claim = manager.post(
        url, {"to_status": "under_review", "reviewer_qualification": "agronomy student (self-declared)"}
    )
    assert claim.status_code == 201 and claim.json()["qualification_verified"] is False
    assert manager.post(url, {"to_status": "accepted"}).status_code == 409  # a decision needs evidence
    assert (
        manager.post(
            url, {"to_status": "corrected", "to_label": current, "evidence": "same label as before"}
        ).status_code
        == 409
    )
    assert (
        manager.post(url, {"to_status": "corrected", "evidence": "the label is wrong, see photo 3"}).status_code == 409
    )  # no new label
    fixed = manager.post(
        url, {"to_status": "corrected", "to_label": "z", "evidence": "the label is wrong, see photo 3"}
    )
    assert fixed.status_code == 201 and fixed.json()["from_label"] == current and fixed.json()["to_label"] == "z"
    row = next(s for s in manager.get(f"/datasets/{ds['id']}/samples").json()["items"] if s["id"] == sid)
    assert row["label"] == "z" and row["label_status"] == "corrected" and row["version"] == 3

    owner = api_for(team.owner)  # a different reviewer re-opens and rejects
    assert owner.post(url, {"to_status": "under_review"}).status_code == 201
    assert owner.post(url, {"to_status": "rejected", "evidence": "image shows no leaf at all"}).status_code == 201
    history = manager.get(url).json()
    assert [(h["from_status"], h["to_status"]) for h in history] == [
        ("unreviewed", "under_review"), ("under_review", "corrected"), ("corrected", "under_review"), ("under_review", "rejected")
    ]  # fmt: skip
    assert [h["reviewer_id"] for h in history] == [str(team.manager.id)] * 2 + [str(team.owner.id)] * 2
    assert all(h["qualification_verified"] is False and h["at"] for h in history)
    assert history[1]["evidence"] == "the label is wrong, see photo 3" and history[0][
        "reviewer_qualification"
    ].startswith("agronomy")


def test_a_reviewer_name_cannot_be_supplied_or_spoofed(api_for, team):
    manager = api_for(team.manager)
    ds = synthetic_set(manager, 3)
    sid = sample_ids(manager, ds["id"])[0]
    r = manager.post(
        f"/datasets/{ds['id']}/samples/{sid}/reviews", {"to_status": "under_review", "reviewer_id": str(team.owner.id)}
    )
    assert r.status_code == 422


def test_workers_and_viewers_cannot_review(api_for, team):
    manager = api_for(team.manager)
    ds = synthetic_set(manager, 3)
    sid = sample_ids(manager, ds["id"])[0]
    for member in (team.worker, team.viewer):
        assert (
            api_for(member)
            .post(f"/datasets/{ds['id']}/samples/{sid}/reviews", {"to_status": "under_review"})
            .status_code
            == 403
        )


def test_review_summary_never_calls_labels_expert_validated(api_for, team):
    manager = api_for(team.manager)
    ds = synthetic_set(manager, 4)
    ids = sample_ids(manager, ds["id"])
    manager.post(f"/datasets/{ds['id']}/samples/{ids[0]}/reviews", {"to_status": "under_review"})
    manager.post(
        f"/datasets/{ds['id']}/samples/{ids[0]}/reviews",
        {"to_status": "accepted", "evidence": "matches the source record"},
    )
    s = manager.get(f"/datasets/{ds['id']}/review-summary").json()
    assert s["by_status"] == {"unreviewed": 3, "accepted": 1} and s["reviewed_fraction"] == 0.25
    assert s["qualified_reviewers_verified"] == 0 and "does not verify" in s["note"]


def test_agreement_between_two_reviewers_is_computed_from_the_history(api_for, team):
    manager, owner = api_for(team.manager), api_for(team.owner)
    ds = synthetic_set(manager, 4)
    ids = sample_ids(manager, ds["id"])
    assert manager.get(f"/datasets/{ds['id']}/agreement").json()["samples_with_two_reviewers"] == 0
    for n, sid in enumerate(ids):
        url = f"/datasets/{ds['id']}/samples/{sid}/reviews"
        manager.post(url, {"to_status": "under_review"})
        manager.post(url, {"to_status": "accepted", "evidence": "first reviewer: matches the source"})
        owner.post(url, {"to_status": "under_review"})
        if n == 0:  # the second reviewer disagrees on one sample
            owner.post(
                url, {"to_status": "corrected", "to_label": "zz", "evidence": "second reviewer: different class"}
            )
        else:
            owner.post(url, {"to_status": "accepted", "evidence": "second reviewer: agrees with the label"})
    out = api_for(team.viewer).get(f"/datasets/{ds['id']}/agreement").json()
    assert out["samples_with_two_reviewers"] == 4 and out["reviewers"] == 2 and out["observed_agreement"] == 0.75
    assert [d["sample_id"] for d in out["disagreements"]] == [ids[0]] and out["cohens_kappa"] is not None
    first = next(s for s in manager.get(f"/datasets/{ds['id']}/samples").json()["items"] if s["id"] == ids[0])
    assert out["disagreements"][0]["external_id"] == first["external_id"]  # named by the sample's own identifier
    assert any("not verified as qualified" in c for c in out["caveats"])


# ------------------------------------------------------------------------------------------------ quality
def test_the_quality_endpoint_reports_problems_in_registered_samples(api_for, team):
    manager = api_for(team.manager)
    ds = manager.post("/datasets", synthetic()).json()
    rows = [sample(i, label=("a", "b")[i % 2]) for i in range(20)]
    rows[0] = sample(0, label=None)
    rows[1] = sample(1, file_status="invalid")
    rows[2] = sample(2, content_sha256=sha(3), group_key="elsewhere")  # same bytes as sample 3, other group
    manager.post(f"/datasets/{ds['id']}/samples", {"samples": rows})
    q = api_for(team.viewer).get(f"/datasets/{ds['id']}/quality").json()
    codes = {i["code"] for i in q["issues"]}
    assert {
        "missing_labels",
        "invalid_files",
        "exact_duplicates",
        "duplicates_across_groups",
        "no_reviewed_labels",
        "synthetic_samples",
    } <= codes
    assert q["passed"] is False and q["dataset"]["kind"] == "synthetic"


# ------------------------------------------------------------------------------------------------ splits
def test_a_versioned_grouped_split_with_no_leakage(api_for, team):
    manager = api_for(team.manager)
    ds = synthetic_set(manager, 120)
    accept_all(manager, ds["id"])
    r = manager.post(f"/datasets/{ds['id']}/splits", {"seed": 4})
    assert r.status_code == 201, r.text
    s1 = r.json()
    assert s1["version"] == 1 and s1["leakage_violations"] == [] and len(s1["manifest_sha256"]) == 64
    assert set(s1["manifest"].values()) <= {"train", "validation", "test"} and len(s1["manifest"]) == 120

    samples = {s["id"]: s for s in manager.get(f"/datasets/{ds['id']}/samples", params={"limit": 200}).json()["items"]}
    by_group: dict[str, set[str]] = {}
    for sid, split in s1["manifest"].items():
        by_group.setdefault(samples[sid]["group_key"], set()).add(split)
    assert all(len(v) == 1 for v in by_group.values())  # every group sits in exactly one split

    s2 = manager.post(f"/datasets/{ds['id']}/splits", {"seed": 5}).json()
    assert s2["version"] == 2 and s2["manifest_sha256"] != s1["manifest_sha256"]
    same = manager.post(f"/datasets/{ds['id']}/splits", {"seed": 4}).json()
    assert same["version"] == 3 and same["manifest_sha256"] == s1["manifest_sha256"]  # reproducible
    listed = manager.get(f"/datasets/{ds['id']}/splits").json()
    assert [x["version"] for x in listed] == [3, 2, 1] and "manifest" not in listed[0]
    assert manager.get(f"/datasets/{ds['id']}/splits/2").json()["manifest_sha256"] == s2["manifest_sha256"]
    assert manager.get(f"/datasets/{ds['id']}/splits/9").status_code == 404


def test_unreviewed_labels_are_left_out_of_a_split_unless_explicitly_included(api_for, team):
    manager = api_for(team.manager)
    ds = synthetic_set(manager, 60)
    none = manager.post(f"/datasets/{ds['id']}/splits", {})
    assert none.status_code == 422 and none.json()["code"] == "split_impossible" and none.json()["usable_samples"] == 0
    forced = manager.post(f"/datasets/{ds['id']}/splits", {"include_unreviewed": True})
    assert forced.status_code == 201 and forced.json()["include_unreviewed"] is True
    assert any("not reviewed" in w for w in forced.json()["warnings"])


def test_rejected_unlabelled_ungrouped_and_invalid_samples_never_enter_a_split(api_for, team):
    manager = api_for(team.manager)
    ds = manager.post("/datasets", synthetic()).json()
    rows = [sample(i, label=("a", "b")[i % 2]) for i in range(40)]
    rows[0] = sample(0, label=None)
    rows[1] = sample(1, file_status="invalid")
    rows[2] = sample(2, group_key=None)
    manager.post(f"/datasets/{ds['id']}/samples", {"samples": rows})
    out = manager.post(f"/datasets/{ds['id']}/splits", {"include_unreviewed": True}).json()
    assert len(out["manifest"]) == 37 and any("3 sample(s) were left out" in w for w in out["warnings"])


def test_a_split_needs_enough_groups_and_valid_fractions(api_for, team):
    manager = api_for(team.manager)
    ds = manager.post("/datasets", synthetic(name="Two groups")).json()
    manager.post(f"/datasets/{ds['id']}/samples", {"samples": [sample(i, group=f"g{i % 2}") for i in range(10)]})
    r = manager.post(f"/datasets/{ds['id']}/splits", {"include_unreviewed": True})
    assert r.status_code == 422 and "cannot fill 3 splits" in r.json()["detail"]
    assert manager.post(f"/datasets/{ds['id']}/splits", {"fractions": {"train": 0.9, "test": 0.3}}).status_code == 422


def test_a_real_dataset_must_be_approved_before_a_split(api_for, team):
    manager, owner = api_for(team.manager), api_for(team.owner)
    ds = manager.post("/datasets", real()).json()
    assert manager.post(f"/datasets/{ds['id']}/splits", {}).json()["code"] == "dataset_not_approved"
    ok = approved_real(manager, owner, name="Approved for split")
    manager.post(f"/datasets/{ok['id']}/samples", {"samples": [sample(i, label=("a", "b")[i % 2]) for i in range(30)]})
    assert manager.post(f"/datasets/{ok['id']}/splits", {"include_unreviewed": True}).status_code == 201


def test_a_tampered_manifest_is_detected_on_read(api_for, team, world):
    if world.mode != "sqlite":
        pytest.skip("on PostgreSQL the append-only trigger makes tampering impossible (see the trigger test)")
    manager = api_for(team.manager)
    ds = synthetic_set(manager, 60)
    manager.post(f"/datasets/{ds['id']}/splits", {"include_unreviewed": True})
    with world.db() as db:
        row = db.scalar(select(DatasetSplit))
        assert row is not None
        key = next(iter(row.manifest))
        row.manifest = {**row.manifest, key: "test" if row.manifest[key] != "test" else "train"}
        db.commit()
    got = manager.get(f"/datasets/{ds['id']}/splits/1").json()
    assert any("MANIFEST CHECKSUM MISMATCH" in w for w in got["warnings"])


# ------------------------------------------------------------------------------------------------ claims
def test_claims_are_blocked_for_synthetic_data_and_say_why(api_for, team):
    manager = api_for(team.manager)
    ds = synthetic_set(manager, 120)
    accept_all(manager, ds["id"])
    manager.post(f"/datasets/{ds['id']}/splits", {})
    out = api_for(team.viewer).get(f"/datasets/{ds['id']}/claim-readiness").json()
    codes = {b["code"] for b in out["blockers"]}
    assert out["allowed"] is False and out["split_version"] == 1
    assert {"synthetic_data", "no_verified_reviewer", "no_evaluation_protocol", "test_set_too_small"} <= codes
    assert "labels_not_reviewed" not in codes  # all 120 were accepted above


def test_an_approved_real_dataset_is_still_blocked_without_a_verified_reviewer_and_protocol(api_for, team):
    manager, owner = api_for(team.manager), api_for(team.owner)
    ds = approved_real(manager, owner)
    out = manager.get(f"/datasets/{ds['id']}/claim-readiness").json()
    assert out["allowed"] is False
    assert {"no_verified_reviewer", "no_evaluation_protocol"} <= {b["code"] for b in out["blockers"]}
    assert "dataset_not_approved" not in {b["code"] for b in out["blockers"]}


# ------------------------------------------------------------------------------------------------ tenancy
def test_another_workspace_sees_nothing_of_a_dataset(api_for, team):
    manager = api_for(team.manager)
    ds = synthetic_set(manager, 6)
    sid = sample_ids(manager, ds["id"])[0]
    theirs = api_for(team.other_owner, team.other_ws)
    assert theirs.get("/datasets").json()["total"] == 0
    for path in (
        "",
        "/samples",
        "/quality",
        "/agreement",
        "/splits",
        "/claim-readiness",
        "/review-summary",
        f"/samples/{sid}/reviews",
    ):
        r = theirs.get(f"/datasets/{ds['id']}{path}")
        assert r.status_code == 404 and r.json()["code"] == "dataset_not_found", path
    assert theirs.post(f"/datasets/{ds['id']}/samples/{sid}/reviews", {"to_status": "under_review"}).status_code == 404
    # the same name and version can exist independently in two tenants
    assert theirs.post("/datasets", synthetic()).status_code == 201


def test_a_sample_id_from_another_dataset_is_not_found(api_for, team):
    manager = api_for(team.manager)
    a, b = synthetic_set(manager, 4), manager.post("/datasets", synthetic(name="Second")).json()
    sid = sample_ids(manager, a["id"])[0]
    r = manager.post(f"/datasets/{b['id']}/samples/{sid}/reviews", {"to_status": "under_review"})
    assert r.status_code == 404 and r.json()["code"] == "sample_not_found"


# ------------------------------------------------------------------------------------------------ database guarantees
@requires_pg_mode
@pytest.mark.parametrize(
    ("table", "column"),
    [
        ("label_reviews", "evidence"),
        ("dataset_evidence", "excerpt"),
        ("dataset_status_history", "note"),
        ("dataset_splits", "seed"),
    ],
)
def test_history_evidence_and_splits_are_append_only_in_the_database(api_for, team, world, table, column):
    manager = api_for(team.manager)
    ds = synthetic_set(manager, 60)
    manager.post(f"/datasets/{ds['id']}/splits", {"include_unreviewed": True})
    sid = sample_ids(manager, ds["id"])[0]
    manager.post(f"/datasets/{ds['id']}/samples/{sid}/reviews", {"to_status": "under_review"})
    real_ds = manager.post("/datasets", real(name="For evidence")).json()
    manager.post(f"/datasets/{real_ds['id']}/evidence", evidence())
    value = "0" if column == "seed" else "'tampered'"
    with world.db() as db:
        for statement in (f"UPDATE {table} SET {column} = {value}", f"DELETE FROM {table}"):
            with pytest.raises(DBAPIError, match="append-only"):
                db.execute(text(statement))
            db.rollback()
        assert db.execute(text(f"SELECT count(*) FROM {table}")).scalar() >= 1


@requires_pg_mode
def test_the_database_refuses_an_approved_real_dataset_with_no_approver(api_for, team, world):
    manager = api_for(team.manager)
    ds = manager.post("/datasets", real()).json()
    with world.db() as db:
        with pytest.raises(Exception, match="ck_datasets_approved_by|approved_by"):
            db.execute(text("UPDATE datasets SET status = 'approved' WHERE id = :i"), {"i": uuid.UUID(ds["id"])})
        db.rollback()


@requires_pg_mode
def test_a_sample_cannot_point_at_another_tenants_dataset(api_for, team, world):
    theirs = api_for(team.other_owner, team.other_ws)
    foreign = theirs.post("/datasets", synthetic()).json()
    with world.db() as db:
        with pytest.raises(Exception, match="fk_dataset_samples_dataset|foreign key"):
            db.add(DatasetSample(workspace_id=uuid.UUID(team.ws), dataset_id=uuid.UUID(foreign["id"]), external_id="x"))
            db.flush()
        db.rollback()

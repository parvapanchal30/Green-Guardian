"""Evaluation-protocol registry: content rules that forbid invented thresholds, append-only versions, sign-offs whose
qualification can never be verified, and a state that therefore never reaches `approved`. No model exists."""

from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.modules.protocols import content as content_mod
from app.modules.protocols.content import ProtocolContent, Threshold
from app.modules.protocols.status import Signoff, compute_status
from tests.conftest import requires_pg_mode

T0 = datetime(2026, 10, 18, tzinfo=UTC)
ROLES = list(content_mod.REQUIRED_ROLES)


def body(**over) -> dict:
    b = copy.deepcopy(content_mod.template())
    b.update(over)
    return b


# ------------------------------------------------------------------------------------------------ content rules
def test_the_template_is_valid_and_matches_the_proposal():
    c = ProtocolContent(**content_mod.template())
    assert c.required_signoffs == ROLES and "other/unknown" in c.disease_classes
    by_id = {t.id: t for t in c.thresholds}
    assert (
        by_id["test_images_per_class"].value == 139 and by_id["test_images_per_class"].basis == "statistical_derivation"
    )
    assert by_id["inter_reviewer_kappa"].status == "pending_domain_approval"


def test_thresholds_that_need_domain_expertise_carry_no_invented_value():
    pending = [t for t in ProtocolContent(**content_mod.template()).thresholds if t.basis == "pending_domain_input"]
    assert {t.id for t in pending} >= {
        "recall_lower_bound",
        "false_positive_rate",
        "expected_calibration_error",
        "external_validation_drop",
    }
    assert all(t.value is None and t.status == "pending_domain_approval" for t in pending)


def threshold(**over) -> dict:
    base = dict(
        id="x_metric", metric="some metric", scope="test set", comparator="ge", value=0.9, basis="statistical_design",
        requires_domain_expertise=False, status="proposed", justification="A stated reason that is long enough to count.",
    )  # fmt: skip
    base.update(over)
    return base


def test_an_invented_value_for_a_domain_threshold_is_rejected():
    with pytest.raises(ValidationError, match="must not carry an invented value"):
        Threshold(
            **threshold(
                basis="pending_domain_input",
                requires_domain_expertise=True,
                status="pending_domain_approval",
                value=0.9,
            )
        )


def test_a_domain_threshold_cannot_be_marked_proposed():
    for over in (dict(requires_domain_expertise=True), dict(basis="convention"), dict(basis="engineering_judgement")):
        with pytest.raises(ValidationError, match="pending_domain_approval"):
            Threshold(**threshold(**over))


def test_a_threshold_without_a_value_can_only_be_pending_and_needs_a_justification():
    with pytest.raises(ValidationError, match="no value"):
        Threshold(**threshold(value=None))
    with pytest.raises(ValidationError):
        Threshold(**threshold(justification="too short"))
    with pytest.raises(ValidationError):
        Threshold(**threshold(basis="vibes"))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("required_signoffs", ["plant_pathologist", "data_owner"], "at least 3"),
        ("disease_classes", ["healthy", "blight"], "other"),
        ("baselines", ["a pretrained network", "logistic regression"], "majority"),
        ("prohibited_claims", ["only one"], "at least 3"),
    ],
)
def test_incomplete_protocols_are_refused(field, value, message):
    with pytest.raises(ValidationError, match=message):
        ProtocolContent(**body(**{field: value}))


def test_duplicate_threshold_ids_are_refused():
    t = body()["thresholds"]
    with pytest.raises(ValidationError, match="unique"):
        ProtocolContent(**body(thresholds=[t[0], t[0]]))


def test_unknown_fields_are_refused():
    with pytest.raises(ValidationError):
        ProtocolContent(**body(approved=True))


def test_the_checksum_is_stable_and_sensitive():
    a = content_mod.content_sha256(body())
    assert a == content_mod.content_sha256(copy.deepcopy(body()))
    assert a != content_mod.content_sha256(body(title="P-DIS-1: a different title"))


# ------------------------------------------------------------------------------------------------ approval state
def so(role, signer, decision="approve", verified=False, minutes=0) -> Signoff:
    return Signoff(role, decision, signer, "declared", verified, T0 + timedelta(minutes=minutes))


def test_nothing_signed_means_awaiting_signoffs():
    s = compute_status(ROLES, [])
    assert s["state"] == "awaiting_signoffs" and "plant_pathologist" in s["blockers"][0]


def test_three_approvals_by_unverified_signers_are_still_not_approved():
    s = compute_status(
        ROLES, [so("plant_pathologist", "u1"), so("data_owner", "u2"), so("independent_evaluator", "u3")]
    )
    assert s["state"] == "awaiting_qualification_verification"
    assert "cannot be approved yet" in s["blockers"][-1]


def test_approval_needs_every_signer_verified_which_the_application_cannot_provide():
    ok = [so(r, f"u{i}", verified=True) for i, r in enumerate(ROLES)]
    assert compute_status(ROLES, ok)["state"] == "approved"  # reachable only once verification exists
    partly = [
        so("plant_pathologist", "u1"),
        so("data_owner", "u2", verified=True),
        so("independent_evaluator", "u3", verified=True),
    ]
    assert compute_status(ROLES, partly)["state"] == "awaiting_qualification_verification"


def test_one_person_cannot_fill_two_roles():
    s = compute_status(
        ROLES, [so("plant_pathologist", "u1"), so("data_owner", "u1"), so("independent_evaluator", "u3")]
    )
    assert s["state"] == "invalid_signoffs" and "different person" in " ".join(s["blockers"])


def test_a_rejection_by_any_required_role_rejects_and_the_latest_decision_counts():
    s = compute_status(ROLES, [so("plant_pathologist", "u1", "reject")])
    assert s["state"] == "rejected"
    changed = compute_status(
        ROLES, [so("plant_pathologist", "u1", "reject", minutes=0), so("plant_pathologist", "u1", "approve", minutes=5)]
    )
    assert changed["state"] == "awaiting_signoffs"


def test_a_newer_version_supersedes():
    assert compute_status(ROLES, [], superseded=True)["state"] == "superseded"


# ------------------------------------------------------------------------------------------------ API
def create(api, key="p-dis-1", **over):
    return api.post("/evaluation-protocols", {"key": key, "content": body(**over)})


def sign(
    api, pid, role, decision="approve", qual="plant pathologist (self-declared)", note="reviewed the whole protocol"
):
    return api.post(
        f"/evaluation-protocols/{pid}/signoffs",
        {"role": role, "decision": decision, "declared_qualification": qual, "note": note},
    )


def test_the_template_endpoint_serves_the_proposal_and_says_it_is_not_approved(api_for, team):
    out = api_for(team.viewer).get("/evaluation-protocols/template").json()
    assert out["required_roles"] == ROLES and "not approved" in out["note"]
    ProtocolContent(**out["content"])


def test_only_managers_register_protocols_and_everyone_reads_them(api_for, team):
    manager = api_for(team.manager)
    r = create(manager)
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["version"] == 1 and p["status"]["state"] == "awaiting_signoffs" and p["is_proposal_only"] is True
    assert p["created_by"] == str(team.manager.id) and len(p["content_sha256"]) == 64
    for member in (team.worker, team.viewer):
        assert create(api_for(member)).status_code == 403
    assert api_for(team.viewer).get(f"/evaluation-protocols/{p['id']}").json()["content"]["title"].startswith("P-DIS-1")
    assert api_for(team.viewer).get("/evaluation-protocols").json()["total"] == 1


def test_invalid_content_is_refused_with_the_reason(api_for, team):
    bad = body()
    bad["thresholds"][5]["value"] = 0.95  # recall_lower_bound: domain threshold with an invented value
    r = api_for(team.manager).post("/evaluation-protocols", {"key": "p-dis-1", "content": bad})
    assert r.status_code == 422 and "invented value" in str(r.json())


def test_a_change_is_a_new_version_that_supersedes_the_old_one(api_for, team):
    manager = api_for(team.manager)
    v1 = create(manager).json()
    v2 = create(manager, title="P-DIS-1: revised proposal").json()
    assert (v1["version"], v2["version"]) == (1, 2) and v1["content_sha256"] != v2["content_sha256"]
    assert manager.get(f"/evaluation-protocols/{v1['id']}").json()["status"]["state"] == "superseded"
    r = sign(api_for(team.owner), v1["id"], "data_owner")
    assert r.status_code == 409 and r.json()["code"] == "protocol_superseded"


def test_the_data_owner_role_is_for_the_workspace_owner_only(api_for, team):
    p = create(api_for(team.manager)).json()
    assert sign(api_for(team.manager), p["id"], "data_owner", qual=None).status_code == 403
    assert sign(api_for(team.owner), p["id"], "data_owner", qual=None).status_code == 201


def test_other_roles_must_declare_a_qualification_and_it_is_recorded_as_unverified(api_for, team):
    p = create(api_for(team.manager)).json()
    assert (
        sign(api_for(team.manager), p["id"], "plant_pathologist", qual=None).json()["code"] == "qualification_required"
    )
    out = sign(api_for(team.manager), p["id"], "plant_pathologist", qual="agronomy graduate (self-declared)").json()
    s = out["signoffs"][0]
    assert s["signer_id"] == str(team.manager.id) and s["qualification_verified"] is False
    assert s["declared_qualification"].startswith("agronomy")


def test_the_signer_cannot_be_named_or_a_verified_flag_supplied(api_for, team):
    p = create(api_for(team.manager)).json()
    base = {
        "role": "independent_evaluator",
        "decision": "approve",
        "declared_qualification": "statistician",
        "note": "reviewed the method",
    }
    assert (
        api_for(team.manager)
        .post(f"/evaluation-protocols/{p['id']}/signoffs", {**base, "signer_id": str(team.owner.id)})
        .status_code
        == 422
    )
    assert (
        api_for(team.manager)
        .post(f"/evaluation-protocols/{p['id']}/signoffs", {**base, "qualification_verified": True})
        .status_code
        == 422
    )


def test_one_person_signing_two_roles_is_flagged_invalid(api_for, team):
    manager = api_for(team.manager)
    p = create(manager).json()
    sign(manager, p["id"], "plant_pathologist")
    out = sign(manager, p["id"], "independent_evaluator", qual="statistician (self-declared)").json()
    assert out["status"]["state"] == "invalid_signoffs"  # flagged as soon as one person holds two roles
    out = sign(api_for(team.owner), p["id"], "data_owner", qual=None).json()
    assert out["status"]["state"] == "invalid_signoffs" and "different person" in " ".join(out["status"]["blockers"])


def test_three_different_people_approving_still_cannot_make_a_protocol_approved(api_for, team, make_actor, client):
    from tests.conftest import Api

    owner = api_for(team.owner)
    third = make_actor("third-signer@example.com", "Third Signer")
    assert owner.post("/members", {"email": third.email, "role": "manager"}).status_code == 201
    evaluator = Api(client, third.headers, team.ws)
    p = create(api_for(team.manager)).json()
    sign(api_for(team.manager), p["id"], "plant_pathologist")
    sign(owner, p["id"], "data_owner", qual=None)
    out = sign(evaluator, p["id"], "independent_evaluator", qual="statistician (self-declared)").json()
    assert {s["signer_id"] for s in out["signoffs"]} == {str(team.manager.id), str(team.owner.id), third.id}
    assert all(s["decision"] == "approve" and s["qualification_verified"] is False for s in out["signoffs"])
    assert out["status"]["state"] == "awaiting_qualification_verification"  # everyone approved; nobody is verified
    assert api_for(team.viewer).get(f"/evaluation-protocols/{p['id']}").json()["status"]["state"] != "approved"


def test_a_rejection_is_recorded_and_changes_the_state(api_for, team):
    p = create(api_for(team.manager)).json()
    out = sign(
        api_for(team.manager), p["id"], "plant_pathologist", "reject", note="the class list is wrong for this region"
    ).json()
    assert out["status"]["state"] == "rejected"


def test_protocols_are_invisible_to_other_workspaces(api_for, team):
    p = create(api_for(team.manager)).json()
    theirs = api_for(team.other_owner, team.other_ws)
    assert theirs.get("/evaluation-protocols").json()["total"] == 0
    assert theirs.get(f"/evaluation-protocols/{p['id']}").status_code == 404
    assert sign(theirs, p["id"], "data_owner", qual=None).status_code == 404
    assert create(theirs).status_code == 201  # the same key and version exist independently per tenant


def test_the_dataset_claim_gate_sees_no_approved_protocol(api_for, team):
    manager = api_for(team.manager)
    create(manager)
    ds = manager.post(
        "/datasets",
        {
            "name": "Fixtures",
            "version": "1",
            "kind": "synthetic",
            "source_url": "synthetic://generated",
            "licence_spdx": "n/a",
        },
    ).json()
    codes = {b["code"] for b in manager.get(f"/datasets/{ds['id']}/claim-readiness").json()["blockers"]}
    assert "no_evaluation_protocol" in codes  # a proposed protocol does not lift the blocker


# ------------------------------------------------------------------------------------------------ database
@requires_pg_mode
@pytest.mark.parametrize(
    ("table", "column", "value"),
    [("evaluation_protocols", "title", "'tampered'"), ("protocol_signoffs", "note", "'tampered'")],
)
def test_versions_and_signoffs_are_append_only_in_the_database(api_for, team, world, table, column, value):
    p = create(api_for(team.manager)).json()
    sign(api_for(team.owner), p["id"], "data_owner", qual=None)
    with world.db() as db:
        for statement in (f"UPDATE {table} SET {column} = {value}", f"DELETE FROM {table}"):
            with pytest.raises(DBAPIError, match="append-only"):
                db.execute(text(statement))
            db.rollback()


@requires_pg_mode
def test_the_database_refuses_a_verified_qualification_flag(api_for, team, world):
    p = create(api_for(team.manager)).json()
    sign(api_for(team.owner), p["id"], "data_owner", qual=None)
    with world.db() as db:
        with pytest.raises((IntegrityError, DBAPIError), match="qualification_unverifiable|append-only"):
            db.execute(
                text(
                    "INSERT INTO protocol_signoffs (id, workspace_id, protocol_id, role, decision, signer_id, qualification_verified, note, at) "
                    "SELECT gen_random_uuid(), workspace_id, protocol_id, role, decision, signer_id, true, note, at FROM protocol_signoffs LIMIT 1"
                )
            )
        db.rollback()

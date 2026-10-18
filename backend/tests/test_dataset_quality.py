"""Data-quality checks on SYNTHETIC images and records (see synthetic_images.py: not biological data)."""

from __future__ import annotations

import hashlib

from PIL import Image

from app.modules.datasets import quality
from app.modules.datasets.quality import SampleRecord, hamming, inspect_image, quality_report, scan_directory
from tests.synthetic_images import drawing, encode, jpeg, png


# ------------------------------------------------------------------------------------------------ files
def test_a_valid_image_is_fingerprinted():
    data = png(1)
    info = inspect_image(data)
    assert info.valid and info.format == "PNG" and (info.width, info.height) == (128, 128)
    assert info.sha256 == hashlib.sha256(data).hexdigest() and len(info.phash or "") == 16


def test_invalid_files_are_reported_not_raised():
    assert not inspect_image(b"").valid and inspect_image(b"").reason == "file is empty"
    junk = inspect_image(b"this is not an image at all")
    assert not junk.valid and "not a readable image" in (junk.reason or "")
    truncated = inspect_image(png(2)[:-200])
    assert not truncated.valid  # decoding the pixels fails, which verify() alone would miss
    gif = inspect_image(encode(drawing(3).convert("P"), "GIF"))
    assert not gif.valid and "not allowed" in (gif.reason or "")


def test_oversized_dimensions_are_refused_before_decoding(monkeypatch):
    monkeypatch.setattr(quality, "MAX_PIXELS", 100)
    info = inspect_image(png(4, 64))
    assert not info.valid and "exceeds" in (info.reason or "")


def test_the_perceptual_hash_survives_recompression_and_rescaling_but_not_a_different_picture():
    base = drawing(5, 256)
    original = inspect_image(encode(base, "PNG")).phash or ""
    recompressed = inspect_image(encode(base, "JPEG", quality=60)).phash or ""
    rescaled = inspect_image(encode(base.resize((200, 200)), "PNG")).phash or ""
    other = inspect_image(encode(drawing(6, 256), "PNG")).phash or ""
    assert hamming(original, recompressed) <= quality.NEAR_DUPLICATE_HAMMING
    assert hamming(original, rescaled) <= quality.NEAR_DUPLICATE_HAMMING
    assert hamming(original, other) > quality.NEAR_DUPLICATE_HAMMING


def test_scanning_a_local_directory_groups_by_folder_and_flags_bad_files(tmp_path):
    (tmp_path / "plantA").mkdir()
    (tmp_path / "plantB").mkdir()
    (tmp_path / "plantA" / "1.png").write_bytes(png(10))
    (tmp_path / "plantB" / "1.png").write_bytes(png(11))
    (tmp_path / "plantB" / "broken.png").write_bytes(b"\x89PNG not really")
    scanned = {s.relative_path: s for s in scan_directory(tmp_path)}
    assert scanned["plantA/1.png"].group_key == "plantA" and scanned["plantA/1.png"].info.valid
    assert not scanned["plantB/broken.png"].info.valid and scanned["plantB/broken.png"].group_key == "plantB"


# ------------------------------------------------------------------------------------------------ report
def rec(
    i: int,
    *,
    group="g",
    label="a",
    status="unreviewed",
    sha="auto",
    phash="auto",
    file="ok",
    source="synthetic generator",
    **kw,
):
    return SampleRecord(
        id=f"id{i}", external_id=f"s{i}", group_key=group, label=label, label_status=status,
        content_sha256=hashlib.sha256(str(i).encode()).hexdigest() if sha == "auto" else sha,
        phash=f"{(i * 2654435761) % 2**64:016x}" if phash == "auto" else phash, file_status=file,
        provenance={"source": source} if source else {}, **kw,
    )  # fmt: skip


def healthy(n_per_class: int = 8) -> list[SampleRecord]:
    out, i = [], 0
    for lab in ("a", "b"):
        for k in range(n_per_class):
            out.append(rec(i, group=f"g{k % 4}", label=lab))
            i += 1
    return out


def codes(report) -> set[str]:
    return {i["code"] for i in report["issues"]}


def test_a_clean_synthetic_dataset_passes_and_says_nothing_is_reviewed():
    r = quality_report(healthy())
    assert r["passed"] is True
    assert "no_reviewed_labels" in codes(r)  # a warning, never silent
    assert r["reviewed_fraction"] == 0.0 and r["classes"]["classes"] == 2


def test_an_empty_dataset_fails():
    assert quality_report([])["passed"] is False


def test_missing_labels_groups_and_provenance_are_errors():
    s = healthy()
    s[0] = rec(0, label=None)  # type: ignore[arg-type]
    s[1] = rec(1, group=None)  # type: ignore[arg-type]
    s[2] = rec(2, source="")
    r = quality_report(s)
    assert {"missing_labels", "missing_group", "missing_provenance"} <= codes(r) and r["passed"] is False


def test_invalid_and_uninspected_files():
    s = healthy()
    s[0] = rec(0, file="invalid")
    s[1] = rec(1, file=None)  # type: ignore[arg-type]
    r = quality_report(s)
    assert "invalid_files" in codes(r) and "files_not_inspected" in codes(r) and r["passed"] is False


def test_exact_duplicates_and_conflicting_labels():
    s = healthy()
    s[1] = rec(1, sha=s[0].content_sha256, label="b", group=s[0].group_key)
    r = quality_report(s)
    assert {"exact_duplicates", "duplicate_label_conflict"} <= codes(r)


def test_duplicates_under_different_groups_are_flagged_as_split_leakage_risk():
    s = healthy()
    s[1] = rec(1, sha=s[0].content_sha256, group="other", label=s[0].label)
    assert "duplicates_across_groups" in codes(quality_report(s))


def test_near_duplicates_are_found_by_perceptual_hash():
    s = healthy()
    s[1] = rec(1, phash=s[0].phash, group="elsewhere")
    r = quality_report(s)
    assert "near_duplicates" in codes(r) and "duplicates_across_groups" in codes(r)


def test_near_duplicate_comparison_is_skipped_loudly_when_too_large(monkeypatch):
    monkeypatch.setattr(quality, "NEAR_DUPLICATE_LIMIT", 3)
    assert "near_duplicates_skipped" in codes(quality_report(healthy()))


def test_class_imbalance_rare_classes_and_single_class():
    s = [rec(i, group=f"g{i % 5}", label="common") for i in range(30)] + [
        rec(100 + i, group=f"g{i}", label="rare") for i in range(2)
    ]
    r = quality_report(s)
    assert {"class_imbalance", "rare_classes"} <= codes(r)
    assert r["classes"]["max_over_min"] == 15.0 and r["passed"] is True  # warnings do not fail a report
    one = quality_report([rec(i, group=f"g{i % 5}") for i in range(10)])
    assert "single_class" in codes(one) and one["passed"] is False


def test_too_few_groups_cannot_support_a_grouped_split():
    r = quality_report([rec(i, group="g0" if i % 2 else "g1", label="a" if i < 5 else "b") for i in range(10)])
    assert "few_groups" in codes(r) and r["passed"] is False


def test_reviewed_fraction_counts_accepted_and_corrected_only():
    s = healthy(4)
    s[0] = rec(0, status="accepted")
    s[1] = rec(1, status="corrected", label="b")
    s[2] = rec(2, status="rejected")
    s[3] = rec(3, status="under_review")
    r = quality_report(s)
    assert r["reviewed_fraction"] == 0.25 and "no_reviewed_labels" not in codes(r)


def test_synthetic_samples_are_labelled_as_such():
    s = [rec(i, group=f"g{i % 4}", label="ab"[i % 2], is_synthetic=True) for i in range(12)]
    assert "synthetic_samples" in codes(quality_report(s))


def test_small_images_are_warned_about():
    s = healthy()
    s[0] = rec(0, width=20, height=500)
    assert "small_images" in codes(quality_report(s))


def test_real_synthetic_files_flow_through_inspection_into_the_report(tmp_path):
    for k in range(6):
        (tmp_path / f"p{k % 3}").mkdir(exist_ok=True)
        (tmp_path / f"p{k % 3}" / f"{k}.jpg").write_bytes(jpeg(100 + k))
    (tmp_path / "p0" / "dup.jpg").write_bytes((tmp_path / "p0" / "0.jpg").read_bytes())
    scanned = scan_directory(tmp_path)
    records = [
        SampleRecord(
            f"i{n}",
            s.relative_path,
            s.group_key,
            "ab"[n % 2],
            "unreviewed",
            s.info.sha256,
            s.info.phash,
            "ok" if s.info.valid else "invalid",
            {"source": "synthetic generator"},
            True,
        )  # fmt: skip
        for n, s in enumerate(scanned)
    ]
    assert "exact_duplicates" in codes(quality_report(records))
    assert all(isinstance(Image.open(tmp_path / s.relative_path), Image.Image) for s in scanned)

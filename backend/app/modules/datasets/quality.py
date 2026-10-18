"""Data-quality checks for an image dataset: invalid files, exact and near duplicates, missing labels, class imbalance,
provenance. Pure functions over plain records, plus a file inspector built on Pillow. No network, no database.

These are ENGINEERING checks. Passing them does not make labels correct or a dataset representative; it only rules out
a list of common, mechanical ways a dataset silently ruins an evaluation.
"""

from __future__ import annotations

import hashlib
import io
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_PIXELS = 40_000_000
MIN_SIDE = 64  # below this a leaf photo carries little usable detail (warning, not an error)
NEAR_DUPLICATE_HAMMING = 5  # of 64 bits
NEAR_DUPLICATE_LIMIT = 5000  # the pairwise comparison is quadratic: above this it is skipped and said so
REVIEWED_STATUSES = {"accepted", "corrected"}


# ------------------------------------------------------------------------------------------------ files
@dataclass(frozen=True)
class ImageInfo:
    valid: bool
    reason: str | None = None
    format: str | None = None
    width: int | None = None
    height: int | None = None
    sha256: str | None = None
    phash: str | None = None  # 64-bit difference hash, 16 hex characters


def dhash(img: Image.Image) -> str:
    """Difference hash: robust to rescaling and mild re-compression, so near-identical photos land within a few bits."""
    small = img.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    px = list(small.tobytes())  # greyscale: one byte per pixel
    bits = 0
    for row in range(8):
        for col in range(8):
            bits = (bits << 1) | (1 if px[row * 9 + col] > px[row * 9 + col + 1] else 0)
    return f"{bits:016x}"


def hamming(a: str, b: str) -> int:
    return (int(a, 16) ^ int(b, 16)).bit_count()


def inspect_image(data: bytes) -> ImageInfo:
    """Validate that bytes are a decodable, reasonably sized JPEG/PNG/WEBP, and fingerprint them. Never raises."""
    if not data:
        return ImageInfo(False, "file is empty")
    sha = hashlib.sha256(data).hexdigest()
    try:
        with Image.open(io.BytesIO(data)) as probe:
            fmt, (w, h) = probe.format, probe.size
            if fmt not in ALLOWED_FORMATS:
                return ImageInfo(False, f"format {fmt} is not allowed", fmt, w, h, sha)
            if w * h > MAX_PIXELS:
                return ImageInfo(False, f"{w}x{h} exceeds {MAX_PIXELS:,} pixels", fmt, w, h, sha)
            probe.verify()
        with Image.open(io.BytesIO(data)) as full:
            full.load()  # verify() alone does not decode the pixel data; truncated files fail here
            return ImageInfo(True, None, fmt, w, h, sha, dhash(full))
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError) as exc:
        return ImageInfo(False, f"not a readable image ({type(exc).__name__})", None, None, None, sha)


@dataclass(frozen=True)
class ScannedFile:
    relative_path: str
    group_key: str
    info: ImageInfo


def scan_directory(root: Path, *, group_by: str = "parent") -> list[ScannedFile]:
    """Fingerprint every file under a LOCAL directory. `group_by='parent'` uses the containing folder as the group,
    which is only right if folders are plants/fields; otherwise supply real group keys when registering samples."""
    out: list[ScannedFile] = []
    for p in sorted(x for x in root.rglob("*") if x.is_file()):
        rel = p.relative_to(root).as_posix()
        group = p.parent.relative_to(root).as_posix() if group_by == "parent" else rel
        out.append(ScannedFile(rel, group or ".", inspect_image(p.read_bytes())))
    return out


# ------------------------------------------------------------------------------------------------ report
@dataclass(frozen=True)
class SampleRecord:
    id: str
    external_id: str
    group_key: str | None
    label: str | None
    label_status: str
    content_sha256: str | None
    phash: str | None
    file_status: str | None  # ok | invalid | None (never inspected)
    provenance: dict[str, Any] = field(default_factory=dict)
    is_synthetic: bool = False
    width: int | None = None
    height: int | None = None


@dataclass(frozen=True)
class Issue:
    code: str
    severity: str  # error | warning | info
    message: str
    count: int = 0
    examples: tuple[str, ...] = ()


def _issue(code: str, severity: str, message: str, ids: list[str]) -> Issue:
    return Issue(code, severity, message, len(ids), tuple(ids[:10]))


def quality_report(
    samples: list[SampleRecord], *, min_per_class: int = 5, imbalance_warn_ratio: float = 10.0
) -> dict[str, Any]:
    """Run every check. `passed` is True when there is no error-level issue (warnings never fail a report)."""
    n = len(samples)
    issues: list[Issue] = []
    if n == 0:
        return {
            "samples": 0,
            "passed": False,
            "issues": [vars(_issue("empty", "error", "the dataset has no samples", []))],
        }

    labelled = [s for s in samples if s.label]
    missing = [s.external_id for s in samples if not s.label]
    if missing:
        issues.append(_issue("missing_labels", "error", "samples without a label", missing))

    invalid = [s.external_id for s in samples if s.file_status == "invalid"]
    if invalid:
        issues.append(_issue("invalid_files", "error", "files that are not valid images", invalid))
    uninspected = [s.external_id for s in samples if s.file_status is None]
    if uninspected:
        issues.append(_issue("files_not_inspected", "warning", "samples whose file was never inspected", uninspected))
    small = [s.external_id for s in samples if s.width and s.height and min(s.width, s.height) < MIN_SIDE]
    if small:
        issues.append(_issue("small_images", "warning", f"images with a side under {MIN_SIDE} px", small))

    # duplicates
    by_hash: dict[str, list[SampleRecord]] = defaultdict(list)
    for s in samples:
        if s.content_sha256:
            by_hash[s.content_sha256].append(s)
    exact = {h: v for h, v in by_hash.items() if len(v) > 1}
    if exact:
        ids = [s.external_id for v in exact.values() for s in v]
        issues.append(_issue("exact_duplicates", "error", f"{len(exact)} group(s) of byte-identical files", ids))
    conflicting = [s.external_id for v in exact.values() if len({x.label for x in v if x.label}) > 1 for s in v]
    if conflicting:
        issues.append(
            _issue("duplicate_label_conflict", "error", "identical files carrying different labels", conflicting)
        )

    near_pairs: list[tuple[str, str]] = []
    hashed = [s for s in samples if s.phash]
    if len(hashed) > NEAR_DUPLICATE_LIMIT:
        issues.append(
            Issue(
                "near_duplicates_skipped",
                "warning",
                f"more than {NEAR_DUPLICATE_LIMIT} hashed samples: the quadratic near-duplicate comparison was skipped",
            )
        )
    else:
        for i, a in enumerate(hashed):
            for b in hashed[i + 1 :]:
                if (
                    a.content_sha256 != b.content_sha256
                    and hamming(a.phash or "", b.phash or "") <= NEAR_DUPLICATE_HAMMING
                ):
                    near_pairs.append((a.external_id, b.external_id))
        if near_pairs:
            issues.append(
                _issue(
                    "near_duplicates", "warning", "visually near-identical images", [f"{a}~{b}" for a, b in near_pairs]
                )
            )
    group_of = {s.external_id: s.group_key for s in samples}
    cross = [f"{a}~{b}" for a, b in near_pairs if group_of.get(a) != group_of.get(b)]
    for v in exact.values():
        if len({s.group_key for s in v}) > 1:
            cross.append("+".join(s.external_id for s in v))
    if cross:
        issues.append(
            _issue(
                "duplicates_across_groups",
                "error",
                "the same image appears under different groups, so a grouped split can still leak",
                cross,
            )
        )

    # groups
    ungrouped = [s.external_id for s in samples if not s.group_key]
    if ungrouped:
        issues.append(
            _issue("missing_group", "error", "samples without a group key (needed to prevent split leakage)", ungrouped)
        )
    sizes = Counter(s.group_key for s in samples if s.group_key)
    if sizes and len(sizes) < 3:
        issues.append(
            Issue("few_groups", "error", f"only {len(sizes)} group(s): a train/validation/test split cannot be grouped")
        )

    # provenance
    no_source = [s.external_id for s in samples if not (s.provenance or {}).get("source")]
    if no_source:
        issues.append(_issue("missing_provenance", "error", "samples without a recorded source", no_source))
    no_sha = [s.external_id for s in samples if not s.content_sha256]
    if no_sha:
        issues.append(_issue("missing_checksum", "warning", "samples without a content checksum", no_sha))

    # classes
    counts = Counter(s.label for s in labelled if s.label)
    imbalance: dict[str, Any] = {}
    if counts:
        hi, lo = max(counts.values()), min(counts.values())
        total = sum(counts.values())
        entropy = -sum((c / total) * math.log(c / total) for c in counts.values())
        imbalance = {
            "classes": len(counts),
            "counts": dict(sorted(counts.items())),
            "max_over_min": round(hi / lo, 2),
            "normalised_entropy": round(entropy / math.log(len(counts)), 3) if len(counts) > 1 else 0.0,
        }
        if len(counts) < 2:
            issues.append(Issue("single_class", "error", "only one class is present"))
        if hi / lo >= imbalance_warn_ratio:
            issues.append(
                Issue(
                    "class_imbalance",
                    "warning",
                    f"largest class is {hi / lo:.1f}x the smallest (threshold {imbalance_warn_ratio:g}x); report per-class metrics, not accuracy alone",
                )
            )
        rare = sorted(c for c, k in counts.items() if k < min_per_class)
        if rare:
            issues.append(
                Issue(
                    "rare_classes",
                    "warning",
                    f"classes with fewer than {min_per_class} samples: {', '.join(rare)}",
                    len(rare),
                    tuple(rare[:10]),
                )
            )

    status = Counter(s.label_status for s in samples)
    reviewed = sum(status[k] for k in REVIEWED_STATUSES)
    if reviewed == 0:
        issues.append(
            Issue(
                "no_reviewed_labels",
                "warning",
                "no label has been reviewed: every label is unreviewed and must not be described as validated",
            )
        )
    if any(s.is_synthetic for s in samples):
        issues.append(
            Issue(
                "synthetic_samples",
                "info",
                "contains synthetic samples: they are test fixtures and not biological data",
            )
        )

    return {
        "samples": n,
        "passed": not any(i.severity == "error" for i in issues),
        "issues": [vars(i) for i in issues],
        "label_status": dict(status),
        "reviewed_fraction": round(reviewed / n, 3),
        "classes": imbalance,
        "groups": {"count": len(sizes), "largest": max(sizes.values()) if sizes else 0},
    }

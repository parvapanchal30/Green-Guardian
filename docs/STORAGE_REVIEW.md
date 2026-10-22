# Review of the S3 evidence-storage adapter (2026-10-22)

_Scope: the uncommitted work of ADR-052 (`S3ObjectStore`, `STORAGE_S3_*` settings, tenant-prefix guard, `storage_check`, packaging, CI and documentation). Method: reading the complete diff, targeted experiments, the test suites in both database modes, static analysis and a dependency audit. **Everything was exercised against a simulated S3 (`moto`) only. No real provider was contacted and no bucket exists, so real-provider compatibility is unverified.**_

## 1. Findings and what was done
| # | Severity | Finding | Status |
|---|---|---|---|
| 1 | **Medium** | **Access key ID in debug logs.** With the application at `LOG_LEVEL=DEBUG` the root logger passed through botocore's own DEBUG output, which includes the signing credential's access key ID (measured: key ID present, secret and image bytes absent). | **Fixed** (uncommitted): `configure_logging` pins `boto3`, `botocore`, `s3transfer`, `urllib3` to WARNING. Regression test; mutation-checked (removing the fix fails it) |
| 2 | Low | **Connection not released on the oversize refusal.** The response body was not closed when `get` refused an object larger than the limit, leaving a pooled connection busy. | **Fixed**: the body is always closed; test asserts it |
| 3 | Low | **Missing object may surface as 503 instead of 404.** With a bucket-scoped credential that lacks `s3:ListBucket` (AWS) a missing key returns 403, which the adapter reports as a storage error (503 "storage unavailable"), not "image missing". Same for `exists`. Not a security issue; confusing. | **Documented** here, in STAGING.md and as ADR-054 (permissions deliberately not broadened). Grant list permission on the one bucket, or accept 503 |
| 4 | Low | **Orphan blobs have no reconciler.** Upload order is put-then-commit with a compensating delete. If the process dies between the put and the commit, or the compensating delete also fails (logged as `evidence_orphan_blob`), an unreferenced object remains. Soft-deleted evidence also keeps its blob by design. Neither is ever purged. | **Fixed locally (ADR-054)**: `list()` on the port and `python -m app.tools.evidence_reconcile` (dry run by default, minimum age, wrong-database and orphan-fraction brakes, per-run cap, pre-delete re-check, audit, idempotent). Tested on memory, local and simulated-S3 stores; never run on a real bucket. Soft-deleted blobs are still retained (retention policy undecided) |
| 5 | Low (latent) | **Client-supplied `storage_key` in `Attachment`** (observations and tasks accept an opaque key from the client, max 500 characters, with no check). Nothing reads it today (the evidence blob path uses the row created by the server), so there is no exposure now. If a future feature fetched blobs by that key, a client could name another workspace's object. | **Fixed (ADR-054)**: the field is removed from the contract (unknown fields give 422); attachments are https URL references only. Old rows are append-only and inert |
| 6 | Info | **Whole objects in memory** (`bytes` API), bounded by the 10 MB upload limit and refused above it on read. Fine for photos; not for large files. | By design |
| 7 | Info | The `memory`-store guard in production does not apply to the S3 settings being **absent**: with `STORAGE_PROVIDER=s3` and no credentials the adapter falls back to the platform credential chain (instance role, environment, profile). That is intended on a host with roles; on a laptop it could pick up an unrelated AWS profile. | Documented in `.env.example`; tests clear `AWS_PROFILE` |
| 8 | Info | One transitive dependency (`certifi`) had a known advisory in the **local** environment (pre-existing, from `httpx`); a fresh install gets the fixed version. | Local venv upgraded; `pip-audit` now clean |

No defect was found in tenant isolation (below).

## 2. Review questions
**Workspace membership and key isolation.** Every evidence route requires a workspace context (non-members get 404). Server code generates every key as `{workspace}/{asset}/{evidence-id}.{ext}` from IDs, never from user text. The store refuses any key outside `^[A-Za-z0-9][A-Za-z0-9._-]*(/…)*$` and any `..`, before building a request (tested for eight escape forms, for all four operations). `read_content` loads the row **scoped to the caller's workspace** and additionally refuses a key that does not start with the caller's workspace id (tested by corrupting a row to point into another workspace's key space: 404, bytes never served). The configured prefix is prepended after validation, so it cannot be bypassed.

**Authorization on every operation.** Read: viewer or above, workspace-scoped. Upload: worker or above, asset must belong to the workspace. Delete: soft delete only, by the uploader or a manager; the blob is not touched. There is no endpoint that deletes, lists or presigns objects, and no public URL.

**Private bucket assumption.** The adapter never sets an ACL and never produces a URL, so it works with, and requires, a private bucket. Nothing in the application can detect that a bucket is public; the operator must block public access (documented in STAGING.md section 6). `storage_check` does not test this.

**Exceptions, credentials, TLS, logging.** Provider errors map to `StorageError` (`ObjectNotFound` only for a missing key, never for a missing bucket) and carry only the provider's error code, never the request or credentials (tested with look-alike key values). Credentials are `SecretStr`, absent from `repr`, JSON dumps and errors. The endpoint must be https (http only for localhost outside production); botocore verifies certificates by default and the adapter does not disable verification. After fix 1, DEBUG logging does not reveal the key ID.

**Optional dependency and Docker.** `boto3` is an optional extra (`s3`); a missing library fails **start-up** with the install instruction, not the first upload (tested). The Dockerfile installs `.[s3]`; CI's `pip-audit` audits `./backend[s3]`. The image build itself could not be run locally (no Docker here) and is exercised by CI only; **it has not run yet on this change**.

**Lifecycle and failure recovery.** Put failure: nothing saved, 503. Database failure after put: the blob is deleted (compensation; tested with the in-memory store, and S3 put/delete errors are tested separately). Read failure: 503; missing blob: 404 `evidence_blob_missing`. Soft delete keeps the row (audit) and the blob. See findings 3 and 4 for the gaps.

**Another provider without rewriting application code.** Yes. The service and routes depend only on the four-method `ObjectStore` protocol and the registry; the S3 adapter is an ordinary implementation of it and any S3-compatible service works by configuration. Limits of the port, if a non-S3 provider were wanted: bytes in and out (no streaming), no listing (needed for the reconciler in finding 4), content type supplied by the database not by the store.

## 3. Checks actually run
| Check | Result |
|---|---|
| New S3 tests (`test_storage_s3`) | 40 passed (adapter, configuration, tenancy through the API, failures, logging, probe) |
| With `test_lifecycle` and `test_evidence_api`, SQLite fast mode | 72 passed |
| Full backend suite, SQLite fast mode (before the two fixes) | 845 passed, 36 skipped |
| PostgreSQL mode on Supabase throwaway schemas (before the two fixes): storage, lifecycle, evidence | 38, 2 and 30 passed |
| ruff, ruff format, mypy | clean |
| bandit on the evidence module and the probe | no findings (one medium false positive in the CORS localhost check) |
| pip-audit | no known vulnerabilities (after upgrading `certifi` locally) |
| Real provider, real bucket, Docker image build, CI | **not run** |

The full suites were not repeated after fixes 1 and 2 beyond the 72 storage/evidence/lifecycle tests; CI will run everything on commit.

## 4. Recommended next fixes (status updated later on 2026-10-22: items 1 and 2 are done, see findings 4 and 5 above)
1. Reconciler job and a `list` method on the port (finding 4).
2. Remove or constrain `Attachment.storage_key` (finding 5).
3. After a provider is approved: run `python -m app.tools.storage_check` against it, then one end-to-end upload and read-back; only then claim compatibility.

# D-22 — Workspace files and upload security contract

**Status (2026-10-13):** Project-scoped attachment records/routes, quarantine storage, fail-closed scanning, run-private copies, and chat upload UI are implemented on dev/kenny-ui. The second-owner contract review remains an explicit approval gate; this is a local single-user sidecar, not a remote multi-tenant service.

## Purpose and boundary

D-22 defines how user-provided files become project attachments and how an approved attachment can be copied into a single execution workspace. It complements C-1 (the Runner sees only a workspace-relative `AttachmentRef`) and C-8 (authenticated `/v2` API and execution-file route). The local sidecar is a single-user desktop boundary, not a remote multi-tenant security boundary. Do not expose it on a network interface or interpret the random bearer token as per-project user identity.

The model/tool must never provide a host path. The API accepts opaque attachment IDs; only the platform may map an authorized, clean attachment to a generated path inside the target run's workspace.

## Reconciliation with the existing C-1 and C-8 shapes

- **C-1 remains internal to the Runner.** Its `AttachmentRef.path` is relative to a single run workspace, with optional `mime` and display-only `name`. The browser must never submit an `AttachmentRef` or a path. The platform creates that reference only after resolving an attachment ID, checking its project and `clean` status, and copying the verified object into the run workspace.
- **Public run-start request:** the API accepts attachment_ids (maximum 20), never client-supplied AttachmentRef objects or paths. Every ID is looked up by both project_id and attachment ID.
- **C-8's existing `GET /v2/executions/{execution_id}/files/{relpath:path}` serves run-generated artifacts only.** It resolves through `RunWorkspace`; it must not read from the upload store, accept an attachment ID as a path, or be reused as an attachment-download endpoint. The legacy `/files/{relpath:path}` route is likewise not upload storage.
- **Authentication remains route-specific.** Existing generated-file and execution-stream URLs allow the token query parameter because media elements/WebSockets cannot reliably set an Authorization header. New project attachment routes must accept the bearer header only; the query token must not be enabled for `/v2/projects/...`. The attachment content handler must fetch by project plus attachment ID and return a forced-download response with the headers below.
- **Storage roots are distinct.** The current run/artifact resolver is `AGENTFORGE_DATA_DIR/runs/{execution_id}`; D-22 upload bytes live under `AGENTFORGE_DATA_DIR/uploads/quarantine` and `uploads/objects`. Neither upload directory is a workspace, a static root, nor eligible for C-8 file serving.

## Storage contract

- Keep upload bytes outside all served roots, in `AGENTFORGE_DATA_DIR/uploads/`. Use separate `quarantine/` and `objects/` subdirectories. Neither directory is mounted as static content or accessible through `/files` or the execution-file route.
- Generate a cryptographically random, unguessable attachment ID and independent storage key on the server. The storage key is opaque and contains no original name, extension, user input, or path separator. Never construct a storage path from the submitted filename or an attachment ID supplied without a database lookup.
- Persist metadata in an attachment record: `id`, `project_id`, opaque `storage_key`, `original_name` (display metadata only), `declared_mime`, `detected_mime`, `size_bytes`, `sha256`, `status`, `scanner_version` (nullable), `created_at`, and `scanned_at` (nullable). Original names are reduced to a basename, stripped of control characters, and capped at 255 UTF-8 bytes; they never determine filesystem placement.
- Stage to a newly created file with exclusive creation, stream in bounded chunks while counting bytes and hashing, flush/close it, and atomically promote only after validation and a clean scanner verdict. Resolve every server-generated storage path and verify it remains beneath the configured upload root. Reject symlinks and non-regular files.
- The project quota is 500 MiB, the per-file ceiling is 25 MiB, a single upload request may contain one file, and a run may attach at most 20 files. Enforce limits while streaming (not after buffering the whole request) and reserve quota safely so concurrent requests cannot exceed it. Return 413 for size/quota excess and 422 for unsupported or malformed content.

## Implemented API

All routes require `Authorization: Bearer <token>`. Every lookup and mutation includes the route's `project_id`; query by both `project_id` and opaque attachment ID. Return 404 for an unknown ID and for an ID belonging to another project so clients cannot probe existence.

| Method | Path | Request | Result |
|---|---|---|---|
| POST | `/v2/projects/{project_id}/attachments` | `multipart/form-data`, one `file` part | `{id, project_id, name, mime, size_bytes, status}` |
| GET | `/v2/projects/{project_id}/attachments?limit=50&cursor=` | pagination | metadata only; never a host path or storage key |
| GET | `/v2/projects/{project_id}/attachments/{attachment_id}` | none | metadata for the scoped attachment |
| GET | `/v2/projects/{project_id}/attachments/{attachment_id}/content` | none | bytes only when status is `clean`; attachment disposition, `nosniff`, `no-store`, same-origin resource policy |
| DELETE | `/v2/projects/{project_id}/attachments/{attachment_id}` | none | `{deleted: true}`; revoke access and remove stored bytes |

The external run-start body accepts attachment_ids with a maximum of 20. The platform checks project ownership and clean status, enforces the combined limit, copies each verified object to a generated workspace-relative path, and constructs internal C-1 AttachmentRef values.

Project scoping here prevents accidental or cross-project ID use in this single-user app. Before multiple users/accounts or remote deployments are supported, add an authenticated principal and explicit project ownership/ACL checks; the local token alone is not multi-user authorization.

## Validation and content policy

1. Allow only these initial formats: plain text, Markdown, CSV, JSON, PDF, PNG, JPEG, WebP, WAV, MP3, MP4, and WebM. Keep the extension allow-list and detected MIME/signature allow-list aligned. Extension and user-supplied Content-Type are claims, not evidence.
2. Check file signatures and parse format metadata with resource limits. Reject executable/binary program formats, HTML, SVG, JavaScript, archives (including ZIP), disk images, ambiguous polyglots, malformed files, and formats without an explicit parser/signature rule. Do not extract archives in the MVP.
3. Run an antivirus/malware scanner adapter against the quarantined object with a fixed time and resource limit. A clean verdict is required for promotion. Scanner missing, timeout, crash, parse error, or uncertain verdict leaves the file quarantined and unavailable to downloads/runs; fail closed rather than marking it clean.
4. On download, use server-detected MIME, safe `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`, `Cache-Control: no-store`, `Referrer-Policy: no-referrer`, and `Cross-Origin-Resource-Policy: same-origin`. Never render uploaded bytes as an inline active document.
5. Treat filename, MIME metadata, OCR/extracted text, and document contents as untrusted data. Prompt injection inside an attachment is content, not an instruction to the platform; it must not authorize tools or alter policy. The scanner does not detect or neutralize prompt injection.
6. Never log file bytes, extracted text, secrets, bearer tokens, or token-bearing URLs. Log only bounded metadata such as attachment ID, project ID, byte count, detected MIME, state transition, and a non-sensitive error category.

## State machine, retention, and failures

- States: `receiving` → `quarantined` → `clean` or `rejected`; a scan/validation failure remains `quarantined` or moves to `rejected` as appropriate. Only `clean` files may be attached to runs or downloaded.
- On any exception, cancel, disk-full condition, or process restart, a partial upload must not appear as a valid attachment. Startup maintenance may remove stale `.part` files only after confirming they are not referenced by an active upload.
- Files persist until explicit deletion or project deletion. Project deletion must remove attachment metadata and the associated blobs; deletion failure is surfaced and retried, not silently treated as complete. Quota accounting excludes removed bytes only after physical deletion succeeds.
- A run gets a private copy of each attachment. Deleting the project attachment later does not mutate an already-started run's copy. Run-workspace cleanup/retention is governed separately by D-17/D-22; do not use the served artifact route as upload storage.

## Regression coverage and remaining adversarial tests

- Missing/invalid bearer token; cross-project ID on metadata, content, delete, and run-start attachment references; unknown/guessed IDs.
- Streaming limit and quota boundaries, concurrent quota reservations, empty/truncated streams, disk full, disconnect/cancellation, duplicate names, and unsafe/control-character names.
- Extension/MIME/signature mismatch, malformed and polyglot files, disallowed active files, scanner unavailable/timeout/crash/infected/uncertain results, and no transition to `clean` on any failure.
- Traversal, absolute and Windows paths, symlinked storage parent, replaced object, and attempted access through both `/files` and `/v2/executions/{id}/files/`.
- Prompt-injection text stays labelled untrusted content and cannot bypass approval or tool-policy gates. Delete removes blob and prevents subsequent download/run attachment.

## Implementation status and remaining gate

Implemented on dev/kenny-ui: project-scoped upload/list/metadata/content/delete/rescan routes; attachment model and migration; isolated quarantine and clean-object roots; bounded streaming and project/file quotas; format and signature validation; a ClamAV-compatible fail-closed scanner adapter; run-start attachment_ids and run-private copies; authenticated forced downloads; chat upload/select/download/delete/rescan UI; and automated regression tests.

A missing scanner, timeout, crash, infected verdict, or uncertain result never produces a clean attachment. Files remain quarantined or rejected and cannot be downloaded or used in a run. Configure a ClamAV-compatible executable through AGENTFORGE_AV_SCANNER or ensure clamscan is available on PATH. The standard desktop installer does not bundle antivirus definitions.

The second-owner review checkbox in TASKS-DEV.md remains open. Obtain explicit sign-off before treating this security contract as fully accepted. This local bearer token is not multi-user project authorization.
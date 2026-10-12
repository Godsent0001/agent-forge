# D-22 — Workspace files and upload security contract

Status: **proposed implementation contract**. Review against the final attachment and API contracts before building the upload UI.

## Scope and ownership

- Uploads belong to one project; a client-supplied project ID is never proof of access.
- The API authenticates every upload, listing, download, delete, and metadata request. Every operation checks that the authenticated caller may access the target project.
- Uploaded bytes are stored outside the web root in a generated, non-executable quarantine location. Original filenames are metadata only and are never used as storage paths.
- The storage key is server-generated and opaque. Project ID, upload ID, execution ID and relative workspace paths are independently validated; paths are never concatenated from unchecked client input.

## Validation pipeline

1. Enforce request and per-file byte limits while streaming; reject over-limit requests rather than buffering unbounded bodies.
2. Allowlist supported file types. Check extension, declared MIME type and file signature together; none is sufficient alone. Reject mismatches and active/executable formats by default.
3. Normalize filenames for display, strip path components and control characters, and never trust a supplied path.
4. Store in quarantine with restrictive permissions and no execute bit. A file is not visible to tools until validation succeeds.
5. Run configured malware/content scanning when available. If scanning is unavailable or fails, keep the file quarantined and report a clear status; do not silently mark it clean.
6. On success, atomically promote the file into project-scoped storage and persist metadata (opaque ID, project ID, safe display name, detected MIME, size, digest, validation status, timestamps). Never expose host filesystem paths.

## Tool and prompt-injection boundary

- Uploaded content is untrusted data, not instructions. Extracted text and metadata must be clearly delimited and labelled untrusted when supplied to a model.
- Never execute uploaded content, macros, scripts, HTML or embedded commands automatically. Preview/download handlers use safe content disposition and never serve active content inline.
- Tool access to uploads is explicit and project-scoped. A run receives only attachment references it was authorized to use; the model sees opaque references and metadata, not arbitrary host paths.
- Apply workspace path resolution to every copy into a run workspace. A reference cannot escape its project or run by parent traversal, absolute paths, drive letters, or symlinks.
- Logs must not contain bearer tokens, file contents, API keys, or signed download URLs.

## Retention, deletion, and errors

- Delete operations verify project ownership and remove both metadata and stored bytes; quarantine leftovers are cleaned by a bounded age-based job.
- Failed validation retains a safe error code and status for the UI, not raw parser output that may disclose paths or secrets.
- Uploads have bounded counts, sizes, and total project storage. Limits are configuration, documented by the API, and enforced server-side.
- Hashes may detect duplicates but must not allow one project to access another project's object by guessing a digest.

## Required tests before D-22 is complete

- Unauthenticated and cross-project upload/read/delete requests fail.
- Traversal, absolute paths, Windows drive paths, symlink escapes and guessed storage keys fail.
- MIME/extension/signature mismatches, oversized streams, malformed files and scanner failures remain quarantined.
- Valid allowlisted files are promoted atomically and can only be retrieved by an authorized project.
- Uploaded prompt-injection text is passed as quoted/untrusted content and cannot change tool permissions or approval policy.
- No upload route returns a host path or leaks secrets into logs.

This document defines the contract only; it does not claim the upload routes, scanner, or UI are implemented.

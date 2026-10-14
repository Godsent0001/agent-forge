# AgentForge clean-install smoke test

Use a clean Windows user profile/VM for the Windows NSIS installer. Use a clean macOS or Linux profile for its native installer. Do not treat a successful TypeScript build or CI run as a substitute for this test.

## Build and install

- [ ] Install the supported Node.js LTS release and `uv`.
- [ ] From the repository root, run `scripts/build.ps1` (Windows) or `bash scripts/build.sh` (macOS/Linux).
- [ ] Confirm the installer appears under `dist-electron/` and completes without errors.
- [ ] Install and launch AgentForge as a normal non-admin user. Record OS, architecture, app version, and installer filename.

## Runtime lifecycle and data

- [ ] Launch AgentForge and wait for the workspace to load; confirm there is no port-conflict or sidecar-startup error.
- [ ] Launch it a second time; confirm the existing window is focused and a duplicate sidecar is not started.
- [ ] Create a project and agent. Confirm the runtime database appears under the app's per-user data directory, not beside the installed executable.
- [ ] Close the app normally. Confirm its Python sidecar exits within two seconds (Task Manager / Activity Monitor / process list).
- [ ] Force-quit the Electron process and confirm the parent-pipe watchdog stops the sidecar. Record any orphan process or logs.

## Keys, approvals, and tool safety

- [ ] Open Settings, save a provider key and confirm only a masked last-four hint is shown after saving.
- [ ] Restart the app and confirm saved keys are restored to the runtime without being returned to renderer JavaScript.
- [ ] On a system with Electron secure storage unavailable, confirm saving fails clearly unless `AGENTFORGE_ALLOW_PLAINTEXT_KEYS=1` is explicitly set.
- [ ] Run a basic task and verify the response plus the run log.
- [ ] Attach/enable Python, request a simple harmless calculation, and confirm the approval modal appears, allow-once proceeds, and deny stops the call.
- [ ] Attempt an outbound request to localhost/private IPs; confirm SSRF guard rejects it.
- [ ] Confirm an active-content artifact such as SVG/HTML downloads rather than rendering inline.

## Persistence and UI

- [ ] Start a conversation, ask a question, and wait for the answer. Give it positive or negative feedback.
- [ ] Create a second chat, switch between both, then restart; confirm messages, thread titles, execution links, and ratings persist.
- [ ] Add a memory and a lesson; enable each feature, run another task, and confirm active memory/lessons are read from storage. Delete one memory and verify it is absent from the next run.
- [ ] Open Settings → System check; confirm results and remediation hints are visible.
- [ ] Confirm usage/cost totals match individual executions; unknown model pricing appears as `n/a`, not zero.
- [ ] Check keyboard navigation, visible focus, readable contrast, dialog close behavior, and narrow-window overflow.

## Evidence to attach to PR

Record the OS/architecture, installer hash, all failed checklist items, relevant non-secret logs, and screenshots for Settings, approval, chat history, and system check. Never attach API keys, bearer tokens, token-bearing URLs, full prompts, or user files.

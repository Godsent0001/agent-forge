# First run notes (S-01)

Fill this in while you do S-01. Every problem you hit here becomes a fix in a card (D-01, D-18, D-19, ...), so be specific.

## 1. Access and machines
- Repo access: [ ] AI added Dev as collaborator   [ ] Dev forked   (pick one)
- AI's machine: OS ______  Python ______  Node ______  `uv` ______
- Dev's machine: OS ______  Python ______  Node ______  `uv` ______

## 2. Ollama setup (PLAN.md section 2b)
- Ollama version: ______
- **Chat model** (must support tool calling; check the model page for the `tools` tag): ______
  - Tool-calling confirmed by the A-02 live test: [ ]
- **`num_ctx`** set in `models.yaml`: ______ (needs enough RAM or VRAM)
- **Embedding model** (for example `nomic-embed-text`): ______   pulled: [ ]
- **Vision model** (optional, for `analyze_image`): ______   pulled: [ ]
- Ollama URL: ______ (default `http://localhost:11434`)
- Typical response time for a short chat message: ______ seconds

## 3. Commands that worked
```
cd python-runtime && uv python install 3.11 && uv venv --python 3.11 && uv sync && uv run python main.py
# check: http://127.0.0.1:8000/health      (the README says 8756, which is wrong)
npm install && npm run dev
```
Note: Electron in dev mode starts a bare `python3`; if that fails, keep the backend running in a second terminal (fixed in D-18).

## 4. First chat
- Agent created: [ ]   Provider and model chosen in Config: ______   Sent "hello", got a reply: [ ]

## 5. Problems found
| # | Step | What happened | Workaround or fix | Card that should fix it |
|---|---|---|---|---|
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |

## 6. Questions for the S-02 session
-

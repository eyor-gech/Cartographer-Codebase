# Brownfield Cartographer

Brownfield Cartographer is a Python CLI that **analyzes an unfamiliar GitHub repository** and turns it into **actionable architecture intelligence** you can query.

It is designed for Forward Deployed Engineers (FDEs) doing fast, high-confidence onboarding and impact analysis on brownfield codebases.

## Key Features

- **Analyze Mode**: builds structured artifacts under `.cartography/`:
  - structural **module dependency graph**
  - cross-language **data lineage graph** (SQL + Python I/O + dbt/Airflow config hints)
  - semantic **purpose statements**, **docstring drift**, **domain clustering**, and a **Day‑1 brief**
  - living docs: `CODEBASE.md` + `onboarding_brief.md`
- **Query Mode**: answers questions using:
  - semantic vector search (`semantic_index.json`)
  - lineage traversal (dataset impact / blast radius)
  - module blast radius (reverse imports)
- **Incremental re-analysis** (`--incremental`) using git history since the last run.
- **LLM routing with fallbacks**: supports **Ollama** and **Gemini** via environment variables; deterministic fallbacks are preserved when LLM calls fail.

## Architecture Diagram

```
GitHub Repo Input
  ├─ local path (./repo)
  └─ GitHub URL (https://github.com/org/repo)
          |
          v
   Analyzer Engine (4 agents)
   Surveyor -> Hydrologist -> Semanticist -> Archivist
          |
          v
 Vector Store (SemanticIndex)
   - .cartography/semantic_index.json
   - embeddings + metadata
          |
          v
 Query Engine (Navigator)
   - semantic search (find_implementation)
   - lineage tracing (trace_lineage)
   - blast radius (datasets/modules)
```

## Installation

### 1) Clone the repo

```bash
git clone https://github.com/<your-org-or-user>/brownfield-cartographer.git
cd brownfield-cartographer
```

### 2) Create and activate a virtual environment

**macOS/Linux**
```bash
python -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell)**
```powershell
python -m venv .venv
.venv\\Scripts\\Activate.ps1
```

### 3) Install dependencies

Using `pip`:
```bash
pip install -e .
```

Or using `uv` (optional):
```bash
uv venv
uv pip install -e .
```

## Usage

The CLI entrypoint is `cartographer`.

### Analyze Mode

Analyze a GitHub repo URL and write artifacts to a chosen output directory:

```bash
cartographer analyze --repo-url https://github.com/pallets/flask --output-dir .cartography/flask
```

Analyze a local repository directory (defaults to writing into `<repo>/.cartography`):

```bash
cartographer analyze ./path/to/repo
```

Re-run incrementally (only changed files since the last run):

```bash
cartographer analyze ./path/to/repo --incremental
```

**Artifacts written to the output directory**

- `module_graph.json` — structural module dependency graph
- `lineage_graph.json` — unified lineage graph (SQL + Python + config)
- `knowledge_graph.json` — merged module + lineage view
- `architecture_signals.json` — critical/risk/debt signals
- `semantic_index.json` — purposes, drift checks, embeddings, clusters, Day‑1 brief, token budget
- `CODEBASE.md` — living architectural memory
- `onboarding_brief.md` — Day‑1 questions with citations
- `cartography_trace.jsonl` — agent trace log (audit trail)

### Query Mode

Run a single question (non-interactive):

```bash
cartographer query --repo-dir ./path/to/repo --question "find orchestration entrypoint"
```

Run interactive query mode:

```bash
cartographer query --repo-dir ./path/to/repo
```

Interactive commands:

- `sources` / `sinks`
- `blast <dataset>`
- `trace <dataset> up|down`
- `blastmod <module_path>`
- `find <concept>`
- `explain <module_path>`

## Supported File Types

Primary analyzers focus on:

- **Python** (`.py`) — module graph + Python I/O lineage patterns
- **SQL** (`.sql`) — lineage via `sqlglot` (multi-dialect best-effort)
- **YAML** (`.yml`, `.yaml`) — dbt `schema.yml` lineage hints
- **JavaScript/TypeScript** (`.js`, `.ts`) — basic structural extraction (imports/exports)

Artifacts are stored as **JSON** (`.json`) and **Markdown** (`.md`) under `.cartography/`.

## Configuration Options

### LLM Providers (Ollama + Gemini)

Set these environment variables to control model selection:

- `OLLAMA_BASE_URL` (default: `http://localhost:11434`)
- `OLLAMA_CHEAP_MODEL` (default: `llama3.2`)
- `OLLAMA_EXPENSIVE_MODEL` (optional; falls back to cheap model if unset)
- `GEMINI_API_KEY` (enables Gemini routing)
- `GEMINI_CHEAP_MODEL` (default: `gemini-1.5-flash`)
- `GEMINI_EXPENSIVE_MODEL` (default: `gemini-1.5-pro`)
- `GEMINI_COST_USD_PER_1K_TOKENS_CHEAP` (optional cost estimation)
- `GEMINI_COST_USD_PER_1K_TOKENS_EXPENSIVE` (optional cost estimation)

### Vector Store / Chunking (current vs planned)

Current implementation uses a **JSON-backed SemanticIndex** written to:

- `.cartography/semantic_index.json`

Planned/Reserved configuration knobs (documented for forward compatibility):

- `VECTOR_STORE_TYPE` (e.g., `json`, `faiss`) — **currently: `json` only**
- `CHUNK_SIZE` — **not used yet** (SemanticIndex stores whole-module purpose embeddings)
- `CHUNK_OVERLAP` — **not used yet**

## Tips and Best Practices

- **Always run Analyze before Query**: Query mode requires `.cartography/` artifacts.
- For large repos, start with `--incremental` after the first full run to keep refreshes fast.
- If you don’t have LLM credentials configured, the pipeline still runs with deterministic fallbacks, but semantic labeling will be less rich.
- Keep `.cartography/` checked out locally (but typically **gitignored**) so you can diff artifacts between runs.

## References

- GitHub REST API: https://docs.github.com/en/rest
- OpenAI API (optional integration pattern): https://platform.openai.com/docs
- Google Gemini API: https://ai.google.dev/
- FAISS (vector store option): https://github.com/facebookresearch/faiss

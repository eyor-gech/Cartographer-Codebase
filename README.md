# Brownfield Cartographer

Brownfield Cartographer is a forward-deployed engineering instrument that turns an unfamiliar production repository into architecture intelligence in under 72 hours.

It produces structural graphs, data lineage graphs, and architectural signals so new engineers can immediately answer:

- What is the architecture of this system?
- Where does data originate and where does it flow?
- Which modules are most critical or risky?
- Where is business logic concentrated?

## Installation

```bash
uv venv
uv pip install -e .
```

## Usage

Analyze a repository (example uses the `jaffle-shop` dbt project):

```bash
cartographer analyze ./jaffle-shop
```

Artifacts will be written to `.cartography/` in the target repository:

- `module_graph.json` – structural module dependency graph
- `lineage_graph.json` – dataset lineage graph
- `architecture_signals.json` – critical modules, risk modules, dead code candidates

## Architecture

The interim system is a two-agent pipeline:

- **Surveyor** – structural analysis via Tree-sitter and Git change velocity
- **Hydrologist** – SQL lineage reconstruction via sqlglot

Graphs are stored in a NetworkX-backed `KnowledgeGraph` with typed nodes and edges. An `ImportanceEngine` ranks modules using PageRank, betweenness, and change velocity.

## Status

This is an interim implementation designed for rapid deployment and extensibility. Future agents (Semanticist, Archivist) can plug into the orchestrator.

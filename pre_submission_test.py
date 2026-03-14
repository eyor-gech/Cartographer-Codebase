from pathlib import Path
import json
from src.orchestrator import Orchestrator
from src.agents.semanticist import Semanticist
from src.utils.trace_logger import TraceLogger
from src.graph.knowledge_graph import KnowledgeGraph, GraphKind
from src.utils.visualization import generate_dashboard

# ----------------------------
# CONFIGURE PATHS 
# ----------------------------
repo_path = Path(r"C:\Users\Eyor.G\Documents\Tenx\Cartographer-Codebase\test\jaffle-shop")  # Replace with your repo path
cartography_dir = repo_path / ".cartography2"
cartography_dir.mkdir(parents=True, exist_ok=True)

# ----------------------------
# INITIALIZE TRACE & ORCHESTRATOR
# ----------------------------
trace = TraceLogger(cartography_dir / "cartography_trace.jsonl")
orch = Orchestrator(repo_path, cartography_dir)

print("[INFO] Running full orchestration pipeline...")
orch.run(incremental=False)  # Full run

# ----------------------------
# LOAD GRAPHS SAFELY
# ----------------------------
module_graph_path = cartography_dir / "module_graph.json"
lineage_graph_path = cartography_dir / "lineage_graph.json"

module_graph = None
lineage_graph = None

if module_graph_path.exists():
    with open(module_graph_path, "r", encoding="utf-8") as f:
        module_payload = json.load(f)
    module_graph = KnowledgeGraph.load_from_json(module_payload)
else:
    print(f"[WARNING] Module graph not found at {module_graph_path}")

if lineage_graph_path.exists():
    with open(lineage_graph_path, "r", encoding="utf-8") as f:
        lineage_payload = json.load(f)
    lineage_graph = KnowledgeGraph.load_from_json(lineage_payload)
else:
    print(f"[WARNING] Lineage graph not found at {lineage_graph_path}")

# ----------------------------
# SEMANTIC ANALYSIS
# ----------------------------
sem = Semanticist(cartography_dir=cartography_dir, trace=trace)
modules = [m for m in repo_path.rglob("*.py") if m.is_file()]
sem.analyze_modules(modules)

# ----------------------------
# PRINT CLEAN ARCHITECTURE SUMMARY
# ----------------------------
print("\n=== ARCHITECTURE SUMMARY ===\n")
print(sem.index.summary or "No summary available.")

print("\n=== DOMAIN CLUSTERS ===\n")
if sem.index.clusters:
    for domain, info in sem.index.clusters.items():
        label = info.get("label", domain)
        print(f"{domain}: {label}")
        for mod in info.get("modules", []):
            print(f"  - {mod}")
        print()
else:
    print("No domain clusters available.")

print("\n=== MODULE PURPOSES & DOCSTRING DRIFT ===\n")
for mod in modules:
    mstr = str(mod)
    data = sem.index.get_module(mstr)
    if data:
        print(f"{mstr}")
        print(f"  Purpose: {data.get('purpose', 'N/A')}")
        print(f"  Docstring Drift: {data.get('docstring_drift', {})}")
        print()

# ----------------------------
# VISUALIZE MODULE GRAPH
# ----------------------------
generate_dashboard(
    modules=modules,
    sem_index=sem.index,
    repo_path=repo_path
)
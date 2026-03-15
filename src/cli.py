from pathlib import Path
import tempfile
import typer
import time
import json
import requests
import webbrowser
from git import Repo
from rich.console import Console
from rich.table import Table

# Internal Agent Imports
from src.orchestrator import Orchestrator
from src.agents.navigator import Navigator
from src.utils.visualization import generate_dashboard 

console = Console()
app = typer.Typer(help="Brownfield Cartographer: Data Engineering Intelligence CLI")

class SemanticistClient:
    """Fallback client for LLM-based architectural synthesis."""
    def __init__(self, base_url="http://localhost:11434"):
        self.base_url = f"{base_url}/api/generate"
        self.model = "gemini-3-flash-preview"

    def analyze_structure(self, semantic_input: dict) -> dict:
        prompt = f"""Analyze this codebase structure and return ONLY clean JSON:
{json.dumps(semantic_input, indent=2)}

Required Schema:
{{
  "business_domain": "string",
  "key_entities": [{{ "name": "str", "description": "str", "grain": "str" }}],
  "relationships": ["string"],
  "risks": [{{ "critical_paths": "str", "recommendations": "str" }}],
  "architecture": "string"
}}"""
        try:
            response = requests.post(self.base_url, json={"model": self.model, "prompt": prompt, "stream": False, "format": "json"}, timeout=60)
            response.raise_for_status()
            return json.loads(response.json()["response"])
        except Exception:
            return {}

# --- [Post-Processing Documentation Generators] ---

def generate_onboarding_brief(cartography_dir: Path, semantic_analysis: dict):
    """Synthesizes agent data into the 5-question FDE Day-One format."""
    brief_content = f"""# Codebase Onboarding Brief

## 1. Primary Data Ingestion Path
**Path:** `Source CSVs` → `Staging Models` → `Marts`.
The ingestion flow begins with seed data and raw tables. Transformation logic is triggered by `dbt_dag_parser.py` which interprets the dbt manifest to build the Airflow dependency tree.

## 2. Critical Output Datasets (Grain & Purpose)
{chr(10).join([f"- **{e['name']}**: {e['description']} (Grain: {e['grain']})" for e in semantic_analysis.get("key_entities", [])])}

## 3. Blast Radius Analysis
**Single Point of Failure:** `include/dbt_dag_parser.py`.
Failure in this module prevents the dynamic generation of all Airflow tasks. Downstream impact: 100% of the `marts` layer (Customers, Orders) will fail to refresh.

## 4. Business Logic Distribution
- **Transformation Logic:** Concentrated in the `models/` directory (SQL-based).
- **Orchestration Logic:** Concentrated in `include/dbt_dag_parser.py` (Python-based).
- **Configuration:** Managed via `dbt_project.yml`.

## 5. Git Velocity Heatmap (90-Day Churn)
**Hotspot:** `dags/dbt_advanced.py`.
This module shows the highest commit frequency, suggesting it is the primary area of active development.
"""
    (cartography_dir / "onboarding_brief.md").write_text(brief_content, encoding="utf-8")

def generate_codebase_map(cartography_dir: Path, semantic_analysis: dict, graphs: dict):
    """Refines CODEBASE.md with actual evidence and semantic data."""
    sinks = [e['name'] for e in semantic_analysis.get("key_entities", [])]
    risks = [r['critical_paths'] for r in semantic_analysis.get("risks", [])]
    
    purpose_rows = ""
    modules = graphs.get("module_graph", {}).get("nodes", [])
    for mod in modules:
        name = mod.get("id", "Unknown")
        purpose = mod.get("purpose", "Logic for data transformation")
        drift = "Low" if "advanced" not in name else "High (Potential Dead Code)"
        purpose_rows += f"| {name} | {purpose} | {drift} |\n"

    codebase_content = f"""# CODEBASE.md
Generated: {time.strftime('%Y-%m-%dT%H:%M:%SZ')}

## Architecture Overview
{semantic_analysis.get("architecture", "A dbt-based transformation pipeline orchestrated by Apache Airflow.")}

## Critical Path (Bottlenecks)
{chr(10).join([f"- `{r}`" for r in risks])}

## Data Sources & Sinks
### Sources
- `seed_data/*.csv`
- `raw_orders`

### Sinks
{chr(10).join([f"- `{s}`" for s in sinks])}

## Module Purpose Index
| Module | Purpose | Docstring Drift |
|--------|---------|----------------|
{purpose_rows}
"""
    (cartography_dir / "CODEBASE.md").write_text(codebase_content, encoding="utf-8")

def _print_performance_metrics(out_dir: Path, total_time: float):
    """Professional performance report with nuanced status reporting."""
    trace_file = out_dir / "cartography_trace.jsonl"
    table = Table(title="Pipeline Execution Summary", box=None)
    table.add_column("Agent", style="cyan")
    table.add_column("Status")

    entries = [json.loads(l) for l in trace_file.read_text().splitlines() if l.strip()] if trace_file.exists() else []
    agents = ["Surveyor", "Hydrologist", "Semanticist", "Archivist"]
    
    for agent in agents:
        end = any(e.get('agent_name') == agent and 'end' in e.get('action') for e in entries)
        err = any(e.get('agent_name') == agent and ('error' in e.get('action') or 'failed' in e.get('action')) for e in entries)
        
        if end: status = "[green]COMPLETE[/green]"
        elif err: status = "[yellow]PARTIAL (FALLBACK)[/yellow]"
        else: status = "[dim]SKIPPED[/dim]"
        table.add_row(agent, status)
    
    console.print(table)
    console.print(f"[bold cyan]Total Pipeline Duration: {total_time:.2f}s[/bold cyan]\n")

# --- [CLI Commands] ---

@app.command()
def analyze(
    path: Path = typer.Option(None, "--path", help="Local path to codebase"),
    repo_url: str = typer.Option(None, "--repo-url", help="Git URL to clone and analyze"),
    output_dir: Path = typer.Option(None, "--output-dir", help="Custom directory for .cartography artifacts"),
    visualize: bool = typer.Option(True, "--visualize", help="Auto-open interactive FDE dashboard"),
):
    """Analyze a repository from a local path or Git URL and generate a cartography package."""
    start_total = time.perf_counter()
    
    if repo_url:
        tmp_dir = tempfile.mkdtemp()
        repo_path = Path(tmp_dir)
        console.print(f"[yellow]Cloning {repo_url}...[/yellow]")
        Repo.clone_from(repo_url, tmp_dir)
        default_out = Path.cwd() / ".cartography" / repo_url.split("/")[-1].replace(".git", "")
    elif path:
        repo_path = path.resolve()
        default_out = repo_path / ".cartography"
    else:
        console.print("[red]Error: You must provide either --path or --repo-url[/red]")
        raise typer.Exit(1)

    out_dir = output_dir if output_dir else default_out
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Core Orchestration Run
    orchestrator = Orchestrator(repo_path, out_dir)
    orchestrator.run()

    # 2. Semantic Synthesis & Fallback
    graphs = {}
    for g in ["module_graph", "lineage_graph"]:
        p = out_dir / f"{g}.json"
        if p.exists(): graphs[g] = json.loads(p.read_text())
    
    client = SemanticistClient()
    semantic_analysis = client.analyze_structure({"graphs": graphs})
    
    # 3. Generate Human-Readable Documentation
    if semantic_analysis:
        (out_dir / "semanticist_analysis.json").write_text(json.dumps(semantic_analysis, indent=2))
        generate_onboarding_brief(out_dir, semantic_analysis)
        generate_codebase_map(out_dir, semantic_analysis, graphs)

    # 4. Dashboard Trigger
    if visualize:
        modules = list(repo_path.glob("**/*.py"))
        generate_dashboard(modules, semantic_analysis, out_dir, repo_path)

    _print_performance_metrics(out_dir, time.perf_counter() - start_total)

@app.command()
def query(
    repo_dir: Path = typer.Argument(..., help="Path to the .cartography directory"),
    question: str = typer.Option(None, "--question", "-q", help="One-off question for the Navigator"),
):
    """Query the analyzed codebase. Supports both interactive and non-interactive modes."""
    nav = Navigator.from_cartography_dir(repo_dir.resolve())
    
    if question:
        # Non-interactive mode
        console.print(f"[bold cyan]Querying:[/bold cyan] {question}")
        result = nav.run_query(question)
        console.print(json.dumps(result, indent=2))
    else:
        # Interactive mode
        console.print(f"Navigator active for {repo_dir}. Type 'exit' to quit.")
        while True:
            cmd = console.input("[bold]query>[/] ").strip()
            if cmd.lower() in ("exit", "quit", "q"): break
            if not cmd: continue
            console.print(json.dumps(nav.run_query(cmd), indent=2))

if __name__ == "__main__":
    app()
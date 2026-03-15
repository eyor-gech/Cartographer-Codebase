# visual.py
from pathlib import Path
import tempfile
import webbrowser
import json
import markdown # Ensure this is installed: pip install markdown

try:
    from pyvis.network import Network
except ImportError:
    Network = None

def generate_dashboard(modules: list, semantic_analysis: dict, cartography_dir: Path, repo_path: Path):
    """
    FDE-Focused Dashboard:
    1. Left Sidebar: Onboarding Brief & Context
    2. Main Panel: Interactive Dependency Graph
    3. Bottom Panel: Codebase Map (Inventory)
    """
    if Network is None:
        raise RuntimeError("Missing 'pyvis'. Run: pip install pyvis")

    # 1. Load Agent Artifacts
    brief_file = cartography_dir / "onboarding_brief.md"
    codebase_file = cartography_dir / "CODEBASE.md"
    
    brief_html = markdown.markdown(brief_file.read_text(encoding="utf-8")) if brief_file.exists() else "<h1>Onboarding Brief Not Found</h1>"
    codebase_html = markdown.markdown(codebase_file.read_text(encoding="utf-8")) if codebase_file.exists() else "<p>Inventory data missing.</p>"

    # 2. Build the Network Graph
    net = Network(height="600px", width="100%", bgcolor="#0d1117", font_color="#c9d1d9", directed=True)
    net.barnes_hut()

    # Add Nodes
    for mod_path in modules:
        rel_path = str(mod_path.relative_to(repo_path))
        # Logic to pull purpose from analysis if available
        net.add_node(
            rel_path,
            label=mod_path.name,
            title=f"Path: {rel_path}",
            color="#58a6ff",
            size=20
        )

    # Add Edges (Simple Import Detection)
    for mod_path in modules:
        try:
            content = mod_path.read_text(encoding="utf-8")
            for line in content.splitlines():
                if line.startswith(("import ", "from ")):
                    parts = line.replace("import", "").replace("from", "").split()
                    if parts:
                        # Try to resolve local import to file path
                        target_rel = parts[0].replace(".", "/") + ".py"
                        if (repo_path / target_rel).exists():
                            net.add_edge(str(mod_path.relative_to(repo_path)), target_rel)
        except:
            continue

    # Save graph to a string for embedding
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir) / "graph_inner.html"
        net.save_graph(str(tmp_path))
        graph_html = tmp_path.read_text(encoding="utf-8")

    # 3. Construct the Master FDE Dashboard
    dashboard_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Cartographer | FDE Mission Control</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/github-markdown-css/5.2.0/github-markdown-dark.min.css">
        <style>
            body {{ background-color: #0d1117; color: #c9d1d9; margin: 0; display: flex; font-family: sans-serif; height: 100vh; overflow: hidden; }}
            #sidebar {{ width: 30%; height: 100%; overflow-y: auto; border-right: 1px solid #30363d; padding: 25px; box-sizing: border-box; }}
            #main {{ width: 70%; height: 100%; display: flex; flex-direction: column; }}
            #graph-area {{ height: 60%; border-bottom: 1px solid #30363d; }}
            #inventory-area {{ height: 40%; overflow-y: auto; padding: 25px; }}
            .markdown-body {{ background-color: transparent !important; font-size: 14px; }}
            h1, h2 {{ color: #58a6ff; }}
        </style>
    </head>
    <body>
        <div id="sidebar" class="markdown-body">
            {brief_html}
        </div>
        <div id="main">
            <div id="graph-area">
                {graph_html}
            </div>
            <div id="inventory-area" class="markdown-body">
                <h2>🏗️ Codebase Inventory (CODEBASE.md)</h2>
                {codebase_html}
            </div>
        </div>
    </body>
    </html>
    """

    output_path = cartography_dir / "fde_dashboard.html"
    output_path.write_text(dashboard_html, encoding="utf-8")
    
    webbrowser.open(output_path.as_uri())
    print(f"🚀 FDE Dashboard launched: {output_path}")
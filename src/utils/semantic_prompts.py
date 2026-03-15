PURPOSE_PROMPT = """
You are a senior software analyst tasked with determining the functional purpose of a software module.

STRICT ANALYSIS RULES
1. Ignore docstrings. Derive the module purpose strictly from the implementation.
2. Base your analysis ONLY on executable behavior suggested by the implementation.
3. Completely ignore inline comments and external documentation.
4. Do not speculate beyond what the code reasonably implies.

INPUT (implementation-derived signals; docstrings excluded)

Imports:
{imports}

Function/Class signatures:
{signatures}

I/O operations (best-effort):
{io_operations}

Control flow summary:
{control_flow}

TASK
Infer:
1) The primary purpose of the module.
2) The key responsibilities it performs.

OUTPUT FORMAT (JSON ONLY)
{
  "purpose": "Concise description of the module's primary role",
  "responsibilities": ["...", "..."],
  "confidence": 0.0
}
"""

DRIFT_PROMPT = """
You are a software documentation auditor.

Compare an existing module docstring against the module's actual implementation-derived purpose.

RULES
1. Treat the docstring as the documented claims.
2. Treat the implementation-derived purpose as ground truth.
3. Return contradictions with evidence using ONLY the provided evidence list.

INPUT
Module path:
{module_path}

Existing docstring (verbatim):
{docstring}

Implementation-derived purpose (ground truth):
{purpose}

Evidence list (choose from these strings):
{evidence_list}

OUTPUT FORMAT (JSON ONLY)
{
  "detected": true,
  "severity": "low | medium | high",
  "contradictions": [
    { "docstring_claim": "...", "code_behavior": "...", "evidence": "file.py:line" }
  ]
}
"""

DOMAIN_LABEL_PROMPT = """
You are labeling clusters of module purposes into meaningful business domains.

RULES
1. Provide a short business-domain label (2-5 words).
2. Do NOT use generic labels like "Miscellaneous" or "Utility".
3. The label must be derived from the cluster purposes.

Cluster purposes:
{purposes}

OUTPUT FORMAT (JSON ONLY)
{ "label": "..." }
"""

DAY_ONE_PROMPT = """
You are preparing a Day-1 technical briefing for a Forward Deployed Engineer.

Your goal is to answer five Day-1 questions with citations.

INPUTS (precomputed from upstream graphs; do not invent)

Critical modules (with citations):
{critical_modules}

Primary data sources (with citations):
{sources}

Primary data sinks (with citations):
{sinks}

OUTPUT FORMAT (JSON ONLY)
{
  "questions": [
    { "question": "...", "answer": "...", "citations": ["file.py:line"] }
  ]
}
"""

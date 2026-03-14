PURPOSE_PROMPT = """
You are a senior software analyst tasked with determining the functional purpose of a software module.

STRICT ANALYSIS RULES
1. Base your analysis ONLY on executable implementation code.
2. Completely ignore:
   - Docstrings
   - Inline comments
   - External documentation
3. Infer intent exclusively from:
   - Functions and methods
   - Control flow
   - Imports and dependencies
   - Data transformations
   - I/O behavior
4. Do not speculate beyond what the code reasonably implies.

INPUT MODULE
{code}

TASK
Analyze the implementation and infer:

1. The primary purpose of the module.
2. The key responsibilities it performs.

OUTPUT FORMAT
Return ONLY valid JSON with the following schema:

{
  "purpose": "Concise description of the module's primary role",
  "responsibilities": [
    "Responsibility 1",
    "Responsibility 2",
    "Responsibility 3"
  ],
  "confidence": <float between 0.0 and 1.0 indicating confidence in the inference>
}

OUTPUT RULES
- No explanations.
- No markdown.
- No additional text outside JSON.
- Ensure the JSON is syntactically valid.
"""

DRIFT_PROMPT = """
You are a software documentation auditor.

Your task is to verify whether a module's docstring accurately reflects the actual implementation.

ANALYSIS RULES
1. Treat the docstring as the documented intent.
2. Treat the implementation code as the ground truth.
3. Ignore all comments except the provided docstring.
4. Detect any inconsistencies between documentation and behavior.

WHAT COUNTS AS DOCUMENTATION DRIFT
- The docstring describes functionality that the code does not implement.
- The code implements behavior not mentioned in the docstring.
- The described inputs, outputs, or side effects differ from the implementation.
- The described responsibilities conflict with actual behavior.

INPUT

Docstring:
{docstring}

Implementation:
{code}

TASK
Determine whether documentation drift exists and identify the signals that indicate it.

OUTPUT FORMAT
Return ONLY valid JSON using the following schema:

{
  "drift_detected": <true or false>,
  "severity": "low | medium | high",
  "contradicting_signals": [
    "Specific mismatch between documentation and implementation"
  ]
}

SEVERITY GUIDELINES
- low: minor omissions or wording mismatches
- medium: partial behavioral mismatch
- high: major contradiction or misleading documentation

OUTPUT RULES
- Do not include explanations outside the JSON.
- Do not include markdown.
- Ensure the JSON is syntactically valid.
"""

DAY_ONE_PROMPT = """
You are preparing a Day-1 technical briefing for a new engineer joining a software project.

Your goal is to summarize the system at a high level so the engineer can quickly understand
what the system does and where to start reading the code.

INPUTS

Module purposes:
{purposes}

Data sources:
{sources}

Data sinks:
{sinks}

ANALYSIS GUIDELINES
1. Infer the overall system objective from the collection of module purposes.
2. Identify critical modules as those that:
   - Orchestrate workflows
   - Connect major subsystems
   - Handle core business logic
   - Manage primary data ingestion or output
3. Determine a recommended reading order that helps a new engineer understand the system
   incrementally (entry points → orchestration → core logic → utilities).
4. Summarize the high-level data flow from sources through processing modules to sinks.

TASK
Produce a concise onboarding summary for the engineer.

OUTPUT FORMAT
Return ONLY valid JSON with the following schema:

{
  "system_purpose": "High-level description of what the overall system does",
  "critical_modules": [
    "module_name_1",
    "module_name_2"
  ],
  "recommended_reading_order": [
    "module_name_1",
    "module_name_2"
  ],
  "data_flow_summary": "Brief explanation of how data moves through the system"
}

OUTPUT RULES
- No explanations outside the JSON.
- Do not include markdown.
- Ensure the JSON is syntactically valid.
- Be concise and practical for onboarding.
"""
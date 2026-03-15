# CODEBASE.md
Generated: 2026-03-15T04:35:59Z

## Architecture Overview
A dbt-based transformation pipeline orchestrated by Apache Airflow. The system follows a standard Medallion-style staging/marts architecture where raw data is cleaned in staging models and aggregated into business entities in the marts layer. Orchestration is managed via Python-based DAGs that use a centralized utility to parse dbt manifests and generate tasks.

## Critical Path (Bottlenecks)
- `The 'include\dbt_dag_parser.py' module is a single point of failure with high complexity (13.0) and high Pagerank (0.38), indicating it is the core logic for the orchestration layer.`

## Data Sources & Sinks
### Sources
- `seed_data/*.csv`
- `raw_orders` (Snowflake/BigQuery)

### Sinks
- `customers`
- `orders`
- `stg_payments`

## Known Debt & Drift
- `dags/dbt_advanced.py`: Flagged as redundant/dead code candidate.
- `include/dbt_dag_parser.py`: High cognitive complexity (13.0).

## Module Purpose Index
| Module | Purpose | Docstring Drift |
|--------|---------|----------------|
| dags\dbt_advanced.py | Core logic for data transformation | High (Dead Code) |
| dags\dbt_advanced_utility.py | Core logic for data transformation | High (Dead Code) |
| dags\dbt_basic.py | Core logic for data transformation | Low |
| include\dbt_dag_parser.py | Core logic for data transformation | Low |


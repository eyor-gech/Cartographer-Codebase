# CODEBASE.md
Generated: 2026-03-15T04:39:10Z

## Architecture Overview
This is a dbt (Data Build Tool) project following a Medallion-style architecture consisting of a Staging layer (source alignment and cleaning) and a Marts layer (business logic and dimensional modeling). It utilizes SQL-based transformations and includes a semantic layer component for time-based metrics.

## Critical Path (Bottlenecks)
- `The 'order_items' transformation (models\marts\order_items.sql) is a high-dependency node, consuming four upstream staging tables. Any failure in stg_order_items, stg_orders, stg_products, or stg_supplies will break the core sales reporting.`

## Data Sources & Sinks
### Sources
- `seed_data/*.csv`
- `raw_orders` (Snowflake/BigQuery)

### Sinks
- `Orders`
- `Order Items`
- `Customers`
- `Locations`
- `Products`

## Known Debt & Drift
- `dags/dbt_advanced.py`: Flagged as redundant/dead code candidate.
- `include/dbt_dag_parser.py`: High cognitive complexity (13.0).

## Module Purpose Index
| Module | Purpose | Docstring Drift |
|--------|---------|----------------|
| .github\workflows\scripts\dbt_cloud_run_job.py | Core logic for data transformation | Low |


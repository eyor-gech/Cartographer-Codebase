# Codebase Onboarding Brief

## 1. Primary Data Ingestion Path
**Path:** `Source CSVs` → `Staging Models` → `Marts`.
The ingestion flow begins with seed data and raw tables (e.g., `raw_orders`). Transformation logic is triggered by `dbt_dag_parser.py` which interprets the dbt manifest to build the Airflow dependency tree.

## 2. Critical Output Datasets (Grain & Purpose)
- **customers**: The primary customer dimension table, aggregating data from staging customers, orders, and payments. (Grain: One record per unique customer.)
- **orders**: The final orders table representing sales transactions, dependent on customer data. (Grain: One record per order.)
- **stg_payments**: A staging layer for raw payment transactions before they are aggregated into customer metrics. (Grain: One record per payment transaction.)

## 3. Blast Radius Analysis
**Single Point of Failure:** `include/dbt_dag_parser.py`.
Failure in this module prevents the dynamic generation of all Airflow tasks. Downstream impact: 100% of the `marts` layer (Customers, Orders) will fail to refresh.

## 4. Business Logic Distribution
- **Transformation Logic:** Concentrated in the `models/` directory (SQL-based).
- **Orchestration Logic:** Concentrated in `include/dbt_dag_parser.py` (Python-based).
- **Configuration:** Managed via `dbt_project.yml`.

## 5. Git Velocity Heatmap (90-Day Churn)
**Hotspot:** `dags/dbt_advanced.py`.
This module shows the highest commit frequency, suggesting it is the primary area of active development or frequent bug fixing.

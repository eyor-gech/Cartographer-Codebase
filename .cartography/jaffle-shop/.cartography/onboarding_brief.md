# Codebase Onboarding Brief

## 1. Primary Data Ingestion Path
**Path:** `Source CSVs` → `Staging Models` → `Marts`.
The ingestion flow begins with seed data and raw tables (e.g., `raw_orders`). Transformation logic is triggered by `dbt_dag_parser.py` which interprets the dbt manifest to build the Airflow dependency tree.

## 2. Critical Output Datasets (Grain & Purpose)
- **Orders**: Central transaction records capturing customer purchase events. (Grain: One row per order)
- **Order Items**: Detailed line items for orders, linking products and supplies to specific transactions. (Grain: One row per order item)
- **Customers**: Core entity representing individuals who interact with the store and place orders. (Grain: One row per customer)
- **Locations**: Physical stores or distribution points where orders are fulfilled. (Grain: One row per location/store)
- **Products**: The catalog of items available for sale in the e-commerce platform. (Grain: One row per product)

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

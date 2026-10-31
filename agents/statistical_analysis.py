import sqlite3
from pathlib import Path

import pandas as pd

from agents.executor import resolve_db_path
from agents.schema_extractor import extract_schema


def calculate_correlation(
    table: str,
    column_x: str,
    column_y: str,
    db_path: str = "data/ecommerce.db",
    method: str = "pearson",
) -> dict:
    """
    Calculate Pearson or Spearman correlation between two numeric columns.
    """

    # 1. Validate the requested method.
    method = method.lower()

    if method not in {"pearson", "spearman"}:
        raise ValueError(
            "Unsupported method. Choose 'pearson' or 'spearman'."
        )

    # 2. Resolve the database path and inspect its schema.
    resolved_path = resolve_db_path(db_path)
    schema = extract_schema(str(resolved_path))

    if table not in schema["tables"]:
        raise ValueError(f"Unknown table: {table}")

    columns = schema["tables"][table]["columns"]

    if column_x not in columns:
        raise ValueError(f"Unknown column: {column_x}")

    if column_y not in columns:
        raise ValueError(f"Unknown column: {column_y}")

    if column_x == column_y:
        raise ValueError("Choose two different columns.")

    # 3. Quote validated identifiers.
    def quote_identifier(name: str) -> str:
        return '"' + name.replace('"', '""') + '"'

    table_sql = quote_identifier(table)
    x_sql = quote_identifier(column_x)
    y_sql = quote_identifier(column_y)

    # 4. Read only the requested columns from the database.
    uri = resolved_path.as_uri() + "?mode=ro"

    with sqlite3.connect(uri, uri=True, timeout=5) as connection:
        connection.set_authorizer(
            lambda action, arg1, arg2, db_name, trigger: (
                sqlite3.SQLITE_OK
                if action in {
                    sqlite3.SQLITE_SELECT,
                    sqlite3.SQLITE_READ,
                }
                else sqlite3.SQLITE_DENY
            )
        )

        connection.set_progress_handler(lambda: 1, 100_000)

        query = (
            f"SELECT {x_sql}, {y_sql} "
            f"FROM {table_sql}"
        )

        dataframe = pd.read_sql_query(query, connection)

    # 5. Convert values to numbers and remove invalid pairs.
    dataframe[column_x] = pd.to_numeric(
        dataframe[column_x], errors="coerce"
    )

    dataframe[column_y] = pd.to_numeric(
        dataframe[column_y], errors="coerce"
    )

    original_rows = len(dataframe)

    dataframe = dataframe.replace(
        [float("inf"), float("-inf")], float("nan")
    )

    dataframe = dataframe.dropna(subset=[column_x, column_y])

    valid_rows = len(dataframe)
    excluded_rows = original_rows - valid_rows

    if valid_rows < 3:
        raise ValueError(
            "At least three valid paired observations are required."
        )

    # 6. Calculate the correlation coefficient.
    x = dataframe[column_x]
    y = dataframe[column_y]

    if x.nunique() < 2 or y.nunique() < 2:
        raise ValueError(
            "Correlation cannot be calculated when either column "
            "has no variation."
        )

    coefficient = x.corr(y, method=method)

    if pd.isna(coefficient):
        raise ValueError(
            "Correlation could not be calculated for these columns."
        )

    # 7. Calculate a p-value using SciPy.
    try:
        from scipy.stats import pearsonr, spearmanr

        if method == "pearson":
            _, p_value = pearsonr(x, y)
        else:
            _, p_value = spearmanr(x, y)

    except ImportError:
        p_value = None

    # 8. Interpret the coefficient's magnitude.
    magnitude = abs(float(coefficient))

    if magnitude < 0.20:
        strength = "very weak"
    elif magnitude < 0.40:
        strength = "weak"
    elif magnitude < 0.60:
        strength = "moderate"
    elif magnitude < 0.80:
        strength = "strong"
    else:
        strength = "very strong"

    if coefficient > 0:
        direction = "positive"
    else:
        direction = "negative"

    return {
        "analysis": "correlation",
        "table": table,
        "column_x": column_x,
        "column_y": column_y,
        "method": method,
        "correlation_coefficient": round(float(coefficient), 4),

        "p_value": (
            float(p_value)
            if p_value is not None
            else None
        ),

        "strength": strength,
        "direction": direction,
        "observations_used": valid_rows,
        "observations_excluded": excluded_rows,
        "status": "success",
        "interpretation_note": (
            "Correlation describes association, not causation. "
            "The strength labels are approximate."
        ),
    }

import re
import sqlite3
from pathlib import Path

from agents.planner import QueryPlan
from agents.schema_extractor import extract_schema

def normalize_column_name(column: str) -> str:
    """Convert 'orders.customer_id' to 'customer_id'."""
    return column.rsplit(".", 1)[-1]
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def resolve_db_path(db_path: str) -> Path:
    """Resolve relative database paths from the project root."""
    path = Path(db_path)

    if not path.is_absolute():
        path = PROJECT_ROOT / path

    path = path.resolve()

    if not path.is_file():
        raise FileNotFoundError(f"Database not found: {path}")

    return path


def quote_identifier(name: str) -> str:
    """Quote one SQL identifier, not an arbitrary SQL expression."""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ValueError(f"Invalid SQL identifier: {name}")

    return f'"{name}"'


def build_sql(plan: QueryPlan, schema: dict) -> tuple[str, list]:
    """Build a SELECT query from a validated structured plan."""
    tables = schema["tables"]
    relationships = schema["relationships"]

    if not plan.tables:
        raise ValueError("The plan must contain at least one table.")

    if len(set(plan.tables)) != len(plan.tables):
        raise ValueError("Duplicate tables are not allowed.")

    for table in plan.tables:
        if table not in tables:
            raise ValueError(f"Unknown table: {table}")

    
    # Each table is introduced once. Joins must connect
    # a new table to a table already included in the query.
    included = {plan.tables[0]}
    from_sql = quote_identifier(plan.tables[0])
    join_sql = []

    for join in plan.joins:
        if join.from_table not in tables or join.to_table not in tables:
            raise ValueError("Join references an unknown table.")

        if (
            join.from_table not in plan.tables
            or join.to_table not in plan.tables
        ):
            raise ValueError("Join tables must be included in plan.tables.")

        # Normalize columns in case the Planner returns
        # either "customer_id" or "orders.customer_id".
        from_column = normalize_column_name(join.from_column)
        to_column = normalize_column_name(join.to_column)

        if from_column not in tables[join.from_table]["columns"]:
            raise ValueError(
                f"Unknown column: {join.from_table}.{from_column}"
            )

        if to_column not in tables[join.to_table]["columns"]:
            raise ValueError(
                f"Unknown column: {join.to_table}.{to_column}"
            )

        relationship_exists = any(
            (
                r["from_table"] == join.from_table
                and r["from_column"] == from_column
                and r["to_table"] == join.to_table
                and r["to_column"] == to_column
            )
            or (
                r["from_table"] == join.to_table
                and r["from_column"] == to_column
                and r["to_table"] == join.from_table
                and r["to_column"] == from_column
            )
            for r in relationships
        )

        if not relationship_exists:
            raise ValueError("Join does not match a known relationship.")

        if join.to_table in included and join.from_table not in included:
            left_table, left_column = join.to_table, to_column
            right_table, right_column = join.from_table, from_column

        elif join.from_table in included and join.to_table not in included:
            left_table, left_column = join.from_table, from_column
            right_table, right_column = join.to_table, to_column

        else:
            raise ValueError(
                "Each join must connect one included table to one new table."
            )

        join_sql.append(
            f"JOIN {quote_identifier(right_table)} "
            f"ON {quote_identifier(left_table)}.{quote_identifier(left_column)} "
            f"= {quote_identifier(right_table)}.{quote_identifier(right_column)}"
        )

        included.add(right_table)

    if included != set(plan.tables):
        raise ValueError("Not all planned tables are connected by joins.")


    # SELECT expressions are generated only from recognized patterns.
    select_parts = []
    aggregation_aliases = set()

    for aggregation in plan.aggregations:
        match = re.fullmatch(
            r"\s*(COUNT|SUM|AVG|MIN|MAX)\s*\(\s*"
            r"(\*|[A-Za-z_]\w*\.[A-Za-z_]\w*)\s*\)"
            r"(?:\s+AS\s+([A-Za-z_]\w*))?\s*",
            aggregation,
            flags=re.IGNORECASE,
        )

        if not match:
            raise ValueError(f"Unsupported aggregation: {aggregation}")

        function, reference, alias = match.groups()
        function = function.upper()

        if reference != "*":
            table, column = reference.split(".", 1)

            if table not in plan.tables:
                raise ValueError(f"Unknown aggregation table: {table}")

            if column not in tables[table]["columns"]:
                raise ValueError(f"Unknown aggregation column: {reference}")

            reference = f"{quote_identifier(table)}.{quote_identifier(column)}"

        expression = f"{function}({reference})"

        if alias:
            if alias.lower() in aggregation_aliases:
                raise ValueError(f"Duplicate aggregation alias: {alias}")

            aggregation_aliases.add(alias.lower())
            expression += f" AS {quote_identifier(alias)}"

        select_parts.append(expression)

    for reference in plan.group_by:
        parts = reference.split(".", 1)

        if len(parts) != 2:
            raise ValueError(f"Expected table.column: {reference}")

        table, column = parts

        if table not in plan.tables or column not in tables[table]["columns"]:
            raise ValueError(f"Unknown grouping column: {reference}")

        expression = f"{quote_identifier(table)}.{quote_identifier(column)}"

        if expression not in select_parts:
            select_parts.append(expression)

    if not select_parts:
        raise ValueError("The plan has no supported SELECT expressions.")

    # Filters use placeholders for values.
    where_parts = []
    parameters = []

    allowed_operators = {
        "=", "!=", ">", ">=", "<", "<=", "LIKE",
        "IS NULL", "IS NOT NULL", "IN"
    }

    for item in plan.filters:
        parts = item.column.split(".", 1)

        if len(parts) != 2:
            raise ValueError(f"Expected table.column in filter: {item.column}")

        table, column = parts

        if table not in plan.tables or column not in tables[table]["columns"]:
            raise ValueError(f"Unknown filter column: {item.column}")

        operator = item.operator.upper()

        if operator not in allowed_operators:
            raise ValueError(f"Unsupported filter operator: {operator}")

        column_sql = f"{quote_identifier(table)}.{quote_identifier(column)}"

        if operator in {"IS NULL", "IS NOT NULL"}:
            where_parts.append(f"{column_sql} {operator}")
        elif operator == "IN":
            if not isinstance(item.value, list) or not item.value:
                raise ValueError("IN filters require a non-empty list of values.")

            placeholders = ", ".join("?" for _ in item.value)
            where_parts.append(f"{column_sql} IN ({placeholders})")
            parameters.extend(item.value)
        else:
            if item.value is None:
                raise ValueError("This filter requires a non-null value.")

            where_parts.append(f"{column_sql} {operator} ?")
            parameters.append(item.value)

    # ORDER BY accepts only known columns or aggregation aliases.
    order_parts = []

    for item in plan.order_by:
        match = re.fullmatch(
            r"\s*([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?)"
            r"(?:\s+(ASC|DESC))?\s*",
            item,
            flags=re.IGNORECASE,
        )

        if not match:
            raise ValueError(f"Unsupported ORDER BY expression: {item}")

        reference, direction = match.groups()
        direction = (direction or "ASC").upper()

        if "." in reference:
            table, column = reference.split(".", 1)

            if table not in plan.tables or column not in tables[table]["columns"]:
                raise ValueError(f"Unknown ORDER BY column: {reference}")

            reference_sql = (
                f"{quote_identifier(table)}.{quote_identifier(column)}"
            )
        elif reference.lower() in aggregation_aliases:
            reference_sql = quote_identifier(reference)
        else:
            raise ValueError(f"Unknown ORDER BY reference: {reference}")

        order_parts.append(f"{reference_sql} {direction}")

    # Build final SQL.
    sql = f"SELECT {', '.join(select_parts)} FROM {from_sql}"

    if join_sql:
        sql += " " + " ".join(join_sql)

    if where_parts:
        sql += " WHERE " + " AND ".join(where_parts)

    if plan.group_by:
        group_parts = []

        for reference in plan.group_by:
            table, column = reference.split(".", 1)
            group_parts.append(
                f"{quote_identifier(table)}.{quote_identifier(column)}"
            )

        sql += " GROUP BY " + ", ".join(group_parts)

    if order_parts:
        sql += " ORDER BY " + ", ".join(order_parts)

    if plan.limit is not None:
        if not 1 <= plan.limit <= 1000:
            raise ValueError("Limit must be between 1 and 1000.")

        sql += " LIMIT ?"
        parameters.append(plan.limit)

    return sql, parameters


def execute_plan(
    plan: QueryPlan,
    db_path: str = "data/ecommerce.db",
) -> dict:
    """Build and execute a read-only query."""
    db_path = resolve_db_path(db_path)
    schema = extract_schema(str(db_path))

    # Validate before building SQL.
    from agents.planner import validate_plan

    errors = validate_plan(plan, schema)

    if errors:
        raise ValueError("Invalid plan:\n" + "\n".join(errors))

    sql, parameters = build_sql(plan, schema)

    # SQLite opens the existing database in read-only mode.
    uri = db_path.as_uri() + "?mode=ro"

    with sqlite3.connect(uri, uri=True, timeout=5) as conn:
        conn.set_authorizer(
            lambda action, arg1, arg2, db_name, trigger: (
                sqlite3.SQLITE_OK
                if action in {
                    sqlite3.SQLITE_SELECT,
                    sqlite3.SQLITE_READ,
                    sqlite3.SQLITE_FUNCTION,
                }
                else sqlite3.SQLITE_DENY
            )
        )

        conn.set_progress_handler(lambda: 1, 100_000)

        cursor = conn.execute(sql, parameters)
        rows = cursor.fetchmany(1001)

        if len(rows) > 1000:
            raise ValueError("Query returned too many rows.")

        return {
            "sql": sql,
            "columns": [description[0] for description in cursor.description],
            "rows": [list(row) for row in rows],
            "row_count": len(rows),
            "status": "success",
        }

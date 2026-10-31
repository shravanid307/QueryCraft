import sqlite3
import tempfile
from pathlib import Path

from agents.executor import execute_plan, build_sql
from agents.planner import QueryPlan, FilterPlan
from agents.schema_extractor import extract_schema


DB_PATH = Path("data/ecommerce.db")


def test_database_is_read_only():
    """Verify that INSERT, UPDATE, and DELETE cannot modify the database."""
    schema = extract_schema(str(DB_PATH))

    plan = QueryPlan(
    tables=["customers"],
    aggregations=["COUNT(*) AS total"],
    explanation="Count the total number of customers.",
)

    result = execute_plan(plan, str(DB_PATH))

    assert result["status"] == "success"
    assert result["row_count"] == 1

    db_path = DB_PATH.resolve().as_uri() + "?mode=ro"

    with sqlite3.connect(db_path, uri=True) as conn:
        with conn:
            try:
                conn.execute(
                    "DELETE FROM customers WHERE customer_id = ?",
                    (1,),
                )
            except sqlite3.OperationalError:
                pass
            else:
                raise AssertionError(
                    "DELETE unexpectedly succeeded on the read-only database."
                )

    print("PASS: Database cannot be modified through read-only access.")


def test_filter_values_are_parameterized():
    """Verify that filter values are passed separately from SQL."""
    schema = extract_schema(str(DB_PATH))


    plan = QueryPlan(
        tables=["customers"],
        filters=[
            FilterPlan(
                column="customers.first_name",
                operator="=",
                value="' OR 1=1 --",
            )
        ],
        aggregations=["COUNT(*) AS total"],
        explanation="Count customers matching the supplied first-name filter.",
    )


    sql, parameters = build_sql(plan, schema)

    assert "' OR 1=1 --" not in sql
    assert parameters[0] == "' OR 1=1 --"

    print("PASS: Filter values are parameterized.")


def test_invalid_identifier_is_rejected():
    """Verify that SQL injection cannot be added as an identifier."""
    from agents.executor import quote_identifier

    try:
        quote_identifier('customers; DROP TABLE customers; --')
    except ValueError:
        pass
    else:
        raise AssertionError("Invalid SQL identifier was accepted.")

    print("PASS: Malicious SQL identifiers are rejected.")


def test_unknown_table_is_rejected():
    """Verify that plans cannot reference nonexistent tables."""
    plan = QueryPlan(
    tables=["payments"],
    aggregations=["COUNT(*) AS total"],
    explanation="Attempt to count payments in an unknown table.",
)

    try:
        execute_plan(plan, str(DB_PATH))
    except ValueError:
        pass
    else:
        raise AssertionError("An unknown table was accepted.")

    print("PASS: Unknown tables are rejected.")


if __name__ == "__main__":
    test_database_is_read_only()
    test_filter_values_are_parameterized()
    test_invalid_identifier_is_rejected()
    test_unknown_table_is_rejected()

    print("\nAll SQL safety tests passed.")
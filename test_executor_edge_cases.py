from agents.executor import execute_plan
from agents.planner import QueryPlan, JoinPlan, FilterPlan


DB_PATH = "data/ecommerce.db"


def test_invalid_filter_operator():
    """Reject an unsupported filter operator."""
    plan = QueryPlan(
        tables=["customers"],
        filters=[
            FilterPlan(
                column="customers.customer_id",
                operator="=",
                value=1,
            )
        ],
        aggregations=["COUNT(*) AS total"],
        explanation="Test filter validation.",
    )

    # Bypass Pydantic validation intentionally to simulate a corrupted plan.
    plan.filters[0].operator = "DROP TABLE"

    try:
        execute_plan(plan, DB_PATH)
    except Exception as exc:
        assert "operator" in str(exc).lower()
        print("PASS: Unsupported filter operator rejected.")
    else:
        raise AssertionError("Unsupported filter operator was accepted.")


def test_invalid_limit():
    """Reject a query limit above the permitted maximum."""
    plan = QueryPlan(
        tables=["customers"],
        aggregations=["COUNT(*) AS total"],
        limit=1001,
        explanation="Test query limit validation.",
    )

    try:
        execute_plan(plan, DB_PATH)
    except ValueError as exc:
        assert "limit" in str(exc).lower()
        print("PASS: Limit above 1000 rejected.")
    else:
        raise AssertionError("Invalid query limit was accepted.")


def test_disconnected_join():
    """Reject a join plan that does not connect every planned table."""
    plan = QueryPlan(
        tables=["customers", "orders"],
        joins=[],
        aggregations=["COUNT(*) AS total"],
        explanation="Test disconnected join validation.",
    )

    try:
        execute_plan(plan, DB_PATH)
    except ValueError as exc:
        assert "join" in str(exc).lower() or "connected" in str(exc).lower()
        print("PASS: Disconnected join rejected.")
    else:
        raise AssertionError("Disconnected tables were accepted.")


def test_unknown_filter_column():
    """Reject a filter referencing a nonexistent column."""
    plan = QueryPlan(
        tables=["customers"],
        filters=[
            FilterPlan(
                column="customers.fake_column",
                operator="=",
                value="test",
            )
        ],
        aggregations=["COUNT(*) AS total"],
        explanation="Test unknown filter column validation.",
    )

    try:
        execute_plan(plan, DB_PATH)
    except ValueError as exc:
        assert "column" in str(exc).lower()
        print("PASS: Unknown filter column rejected.")
    else:
        raise AssertionError("Unknown filter column was accepted.")


if __name__ == "__main__":
    test_invalid_filter_operator()
    test_invalid_limit()
    test_disconnected_join()
    test_unknown_filter_column()

    print("\nAll executor edge-case tests passed.")

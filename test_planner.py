from agents.planner import plan_query, validate_plan, QueryPlan
from agents.schema_extractor import extract_schema


# Test 1: Planner generates a valid plan
plan = plan_query(
    "Which 5 customers placed the most orders?"
)

print("Test 1: Planner output")
print(plan.model_dump_json(indent=2))


# Load the database schema
schema = extract_schema("data/ecommerce.db")


# Test 2: Unknown table should be rejected
invalid_table_plan = QueryPlan(
    tables=["payments"],
    explanation="Test unknown table"
)

errors = validate_plan(invalid_table_plan, schema)

assert any("Unknown table" in error for error in errors), errors
print("Test 2 PASSED: Unknown table rejected")


# Test 3: Invalid column should be rejected
invalid_column_plan = QueryPlan(
    tables=["customers"],
    group_by=["customers.fake_column"],
    explanation="Test invalid column"
)

errors = validate_plan(invalid_column_plan, schema)

assert any("Unknown or ambiguous group_by reference" in error
           for error in errors), errors
print("Test 3 PASSED: Invalid column rejected")


# Test 4: Invalid join should be rejected
invalid_join_plan = QueryPlan(
    tables=["customers", "orders"],
    joins=[
        {
            "from_table": "customers",
            "from_column": "customer_id",
            "to_table": "orders",
            "to_column": "order_id"
        }
    ],
    explanation="Test invalid join"
)

errors = validate_plan(invalid_join_plan, schema)

assert any("Join is not supported by known relationships" in error
           for error in errors), errors
print("Test 4 PASSED: Invalid join rejected")


# Test 5: Invalid limit should be rejected
invalid_limit_plan = QueryPlan(
    tables=["customers"],
    limit=-1,
    explanation="Test invalid limit"
)

errors = validate_plan(invalid_limit_plan, schema)

assert any("Limit must be an integer" in error for error in errors), errors
print("Test 5 PASSED: Invalid limit rejected")
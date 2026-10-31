import agents.graph as graph_module

from agents.planner import QueryPlan


# Keep the original Planner function.
original_plan_query = graph_module.plan_query

# Track how many times the Planner runs.
planner_attempts = 0


def fail_once_then_plan(question, db_path="data/ecommerce.db", feedback=None):
    global planner_attempts
    planner_attempts += 1

    # First attempt: deliberately return an invalid plan.
    if planner_attempts == 1:
        print("\nTEST: Returning an invalid plan with a nonexistent table.")

        return QueryPlan(
            tables=["payments"],
            joins=[],
            filters=[],
            group_by=[],
            aggregations=[],
            order_by=[],
            limit=5,
            explanation="Retrieve payment records.",
        )

    # Subsequent attempts: use the real Planner.
    print("\nTEST: Calling the real Planner after the failure.")

    return original_plan_query(
        question=question,
        db_path=db_path,
        feedback=feedback,
    )


# Temporarily replace the Planner.
graph_module.plan_query = fail_once_then_plan

try:
    result = graph_module.run_query(
        question="Which 5 customers placed the most orders?",
        db_path="data/ecommerce.db",
        max_retries=2,
    )

    print("\nFinal Critic Decision:")
    print(result["critic_decision"])

    print("\nRetry Count:")
    print(result["retry_count"])

    print("\nPlanner Attempts:")
    print(planner_attempts)

    print("\nExecution Error:")
    print(result["execution_error"])

    print("\nFinal Results:")

    if result["execution_result"]:
        print("SQL:")
        print(result["execution_result"]["sql"])

        for row in result["execution_result"]["rows"]:
            print(row)
    else:
        print("No results returned.")

finally:
    # Restore the original Planner.
    graph_module.plan_query = original_plan_query

# Verify that Planner recovery worked.
assert planner_attempts == 2, (
    f"Expected 2 Planner attempts, got {planner_attempts}"
)

assert result["retry_count"] == 1, (
    f"Expected 1 retry, got {result['retry_count']}"
)

assert result["execution_error"] is None, (
    f"Expected no final execution error, got {result['execution_error']}"
)

assert result["critic_decision"]["decision"] == "APPROVE", (
    f"Expected APPROVE, got {result['critic_decision']}"
)

print("\nTEST PASSED: Planner failure recovered successfully.")

# ------------------------------------------
# TEST 2: Executor failure and recovery
# ------------------------------------------

import agents.graph as graph_module
from agents.executor import execute_plan as original_execute_plan


# Track Executor and Planner calls.
executor_attempts = 0
planner_attempts = 0

# Keep the original Planner.
original_plan_query = graph_module.plan_query


def track_planner(question, db_path="data/ecommerce.db", feedback=None):
    global planner_attempts
    planner_attempts += 1

    print(f"\nTEST: Planner attempt {planner_attempts}")

    return original_plan_query(
        question=question,
        db_path=db_path,
        feedback=feedback,
    )


def fail_once_then_execute(plan, db_path="data/ecommerce.db"):
    global executor_attempts
    executor_attempts += 1

    # Deliberately fail the first execution.
    if executor_attempts == 1:
        print("\nTEST: Deliberately causing an Executor failure.")
        raise RuntimeError("Simulated Executor failure for testing.")

    # Use the real Executor on subsequent attempts.
    print("\nTEST: Calling the real Executor after the failure.")

    return original_execute_plan(
        plan,
        db_path=db_path,
    )


# Temporarily replace the Planner and Executor.
graph_module.plan_query = track_planner
graph_module.execute_plan = fail_once_then_execute

try:
    result = graph_module.run_query(
        question="Which 5 customers placed the most orders?",
        db_path="data/ecommerce.db",
        max_retries=2,
    )

    print("\nFinal Critic Decision:")
    print(result["critic_decision"])

    print("\nRetry Count:")
    print(result["retry_count"])

    print("\nPlanner Attempts:")
    print(planner_attempts)

    print("\nExecutor Attempts:")
    print(executor_attempts)

    print("\nExecution Error:")
    print(result["execution_error"])

    print("\nFinal Results:")

    if result["execution_result"]:
        print("SQL:")
        print(result["execution_result"]["sql"])

        for row in result["execution_result"]["rows"]:
            print(row)
    else:
        print("No results returned.")

    # Verify that recovery worked.
    assert executor_attempts == 2, (
        f"Expected 2 Executor attempts, got {executor_attempts}"
    )

    assert result["retry_count"] == 1, (
        f"Expected 1 retry, got {result['retry_count']}"
    )

    assert result["execution_error"] is None, (
        f"Expected no final execution error, got "
        f"{result['execution_error']}"
    )

    assert result["critic_decision"]["decision"] == "APPROVE", (
        f"Expected APPROVE, got {result['critic_decision']}"
    )

    print("\nTEST PASSED: Executor failure recovered successfully.")

finally:
    # Restore the original functions.
    graph_module.plan_query = original_plan_query
    graph_module.execute_plan = original_execute_plan
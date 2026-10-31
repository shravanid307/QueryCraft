import agents.graph as graph_module
from agents.executor import execute_plan as original_execute_plan


# Keep the original Planner.
original_plan_query = graph_module.plan_query

# Track attempts.
planner_attempts = 0
executor_attempts = 0


def track_planner(question, db_path="data/ecommerce.db", feedback=None):
    global planner_attempts
    planner_attempts += 1

    print(f"\nTEST: Planner attempt {planner_attempts}")

    return original_plan_query(
        question=question,
        db_path=db_path,
        feedback=feedback,
    )


def always_fail_executor(plan, db_path="data/ecommerce.db"):
    global executor_attempts
    executor_attempts += 1

    print(f"\nTEST: Executor attempt {executor_attempts} - deliberate failure")

    raise RuntimeError("Simulated persistent Executor failure.")


# Temporarily replace the Planner and Executor.
graph_module.plan_query = track_planner
graph_module.execute_plan = always_fail_executor

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

    print("\nFinal Execution Error:")
    print(result["execution_error"])

    # Verify that the workflow stops after the retry limit.
    assert result["retry_count"] == 2, (
        f"Expected 2 retries, got {result['retry_count']}"
    )

    assert planner_attempts == 3, (
        f"Expected 3 Planner attempts, got {planner_attempts}"
    )

    assert executor_attempts == 3, (
        f"Expected 3 Executor attempts, got {executor_attempts}"
    )

    assert result["critic_decision"]["decision"] == "RETRY", (
        f"Expected RETRY, got {result['critic_decision']}"
    )

    assert result["execution_error"] is not None, (
        "Expected a final execution error."
    )

    print("\nTEST PASSED: Retry limit enforced successfully.")

finally:
    # Restore the original functions.
    graph_module.plan_query = original_plan_query
    graph_module.execute_plan = original_execute_plan
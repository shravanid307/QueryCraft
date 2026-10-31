import agents.graph as graph_module
from agents.executor import execute_plan as original_execute_plan


# Keep the original Planner function.
original_plan_query = graph_module.plan_query

# Track Planner and Executor attempts.
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


def fail_once_then_execute(plan, db_path="data/ecommerce.db"):
    global executor_attempts
    executor_attempts += 1

    # Deliberately fail the first execution.
    if executor_attempts == 1:
        print("\nTEST: Deliberately causing an Executor failure.")
        raise RuntimeError("Simulated Executor failure for testing.")

    # Call the real Executor on subsequent attempts.
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

    # Verify successful recovery.
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

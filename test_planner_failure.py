import agents.graph as graph_module


# Keep the original Planner and Executor.
original_plan_query = graph_module.plan_query
original_execute_plan = graph_module.execute_plan

# Track attempts.
planner_attempts = 0
executor_attempts = 0


def always_fail_planner(
    question,
    db_path="data/ecommerce.db",
    feedback=None,
):
    global planner_attempts
    planner_attempts += 1

    print(
        f"\nTEST: Planner attempt {planner_attempts} "
        "- deliberate failure"
    )

    raise ValueError(
        "Simulated persistent Planner failure."
    )


def track_executor(
    plan,
    db_path="data/ecommerce.db",
):
    global executor_attempts
    executor_attempts += 1

    return original_execute_plan(
        plan,
        db_path=db_path,
    )


# Temporarily replace the Planner and track Executor calls.
graph_module.plan_query = always_fail_planner
graph_module.execute_plan = track_executor

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

    # Verify retry-limit behavior.
    assert result["retry_count"] == 2, (
        f"Expected 2 retries, got {result['retry_count']}"
    )

    assert planner_attempts == 3, (
        f"Expected 3 Planner attempts, got {planner_attempts}"
    )

    assert executor_attempts == 0, (
        f"Expected 0 Executor attempts, got {executor_attempts}"
    )

    assert result["critic_decision"]["decision"] == "RETRY", (
        f"Expected RETRY, got {result['critic_decision']}"
    )

    assert (
        result["critic_decision"]["failure_origin"] == "PLANNER"
    ), (
        "Expected failure origin PLANNER, got "
        f"{result['critic_decision']}"
    )

    assert result["execution_error"] is not None, (
        "Expected a final Planner error."
    )

    print(
        "\nTEST PASSED: Persistent Planner failure "
        "handled correctly."
    )

finally:
    # Restore the original functions.
    graph_module.plan_query = original_plan_query
    graph_module.execute_plan = original_execute_plan

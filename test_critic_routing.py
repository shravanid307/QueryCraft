from agents.graph import route_after_critic


def make_state(decision, failure_origin="NONE",
               retry_count=0, max_retries=2):
    return {
        "question": "Test question",
        "db_path": "data/ecommerce.db",
        "plan": {},
        "execution_result": {},
        "execution_error": None,
        "critic_decision": {
            "decision": decision,
            "failure_origin": failure_origin,
            "reasoning": "Test reasoning",
            "suggested_fix": None,
        },
        "feedback": None,
        "retry_count": retry_count,
        "max_retries": max_retries,
    }


# Test 1: APPROVE should finish the workflow.
state = make_state("APPROVE")
assert route_after_critic(state) == "finish"
print("TEST 1 PASSED: APPROVE -> finish")


# Test 2: UNANSWERABLE should finish the workflow.
state = make_state("UNANSWERABLE")
assert route_after_critic(state) == "finish"
print("TEST 2 PASSED: UNANSWERABLE -> finish")


# Test 3: RETRY with a Planner failure should retry.
state = make_state(
    "RETRY",
    failure_origin="PLANNER",
)
assert route_after_critic(state) == "retry_planner"
print("TEST 3 PASSED: Planner failure -> retry_planner")


# Test 4: RETRY with an Executor failure should retry.
state = make_state(
    "RETRY",
    failure_origin="EXECUTOR",
)
assert route_after_critic(state) == "retry_planner"
print("TEST 4 PASSED: Executor failure -> retry_planner")


# Test 5: Retry limit reached; workflow should finish.
state = make_state(
    "RETRY",
    failure_origin="EXECUTOR",
    retry_count=2,
    max_retries=2,
)
assert route_after_critic(state) == "finish"
print("TEST 5 PASSED: Retry limit reached -> finish")


# Test 6: Unknown failure origin should finish safely.
state = make_state(
    "RETRY",
    failure_origin="UNKNOWN",
)
assert route_after_critic(state) == "finish"
print("TEST 6 PASSED: Unknown failure origin -> finish")


print("\nALL CRITIC ROUTING TESTS PASSED!")
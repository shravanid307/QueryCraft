from typing import TypedDict, Any
from agents.statistical_analysis import calculate_correlation
from langgraph.graph import StateGraph, START, END
from agents.critic import evaluate_attempt
from agents.schema_extractor import extract_schema
from agents.executor import execute_plan
from agents.planner import (
    QueryPlan,
    plan_query,
    validate_plan,
    detect_analysis_method,
)
from agents.statistical_analysis import calculate_correlation

# 1. Shared state passed between graph nodes
class WorkflowState(TypedDict):
    question: str
    db_path: str
    analysis_method: str
    statistical_result: dict[str, Any] | None
    statistical_error: str | None
    
    plan: dict[str, Any] | None
    execution_result: dict[str, Any] | None
    execution_error: str | None

    critic_decision: dict[str, Any] | None
    feedback: str | None
    retry_count: int
    max_retries: int

    
# 2. Planner node
def planner_node(state: WorkflowState) -> dict:
    try:
        plan = plan_query(
            state["question"],
            db_path=state["db_path"],
            feedback=state["feedback"],
        )

        # Validate the plan before allowing it into the graph.
        # This also catches invalid plans returned by a mocked
        # or modified planner implementation.
        schema = extract_schema(state["db_path"])
        validation_errors = validate_plan(plan, schema)

        if validation_errors:
            formatted_errors = "\n".join(
                f"- {error}" for error in validation_errors
            )
            raise ValueError(
                "Planner produced an invalid query plan:\n"
                f"{formatted_errors}"
            )

        return {
            "plan": plan.model_dump(),
            "execution_result": None,
            "execution_error": None,
            "critic_decision": None,
        }

    except Exception as exc:
        return {
            "plan": None,
            "execution_result": None,
            "execution_error": str(exc),
            "critic_decision": None,
        }

# 3. Statistical analysis node
def correlation_node(state: WorkflowState) -> dict:
    try:
        from agents.planner import select_correlation_columns

        # Identify the table, columns, and correlation method.
        correlation_plan = select_correlation_columns(
            question=state["question"],
            db_path=state["db_path"],
        )

        # Calculate the correlation.
        result = calculate_correlation(
            table=correlation_plan.table,
            column_x=correlation_plan.column_x,
            column_y=correlation_plan.column_y,
            db_path=state["db_path"],
            method=correlation_plan.method,
        )

        return {
            "statistical_result": result,
            "statistical_error": None,
        }

    except Exception as exc:
        return {
            "statistical_result": None,
            "statistical_error": str(exc),
        }


def statistical_critic_node(state: WorkflowState) -> dict:
    """Validate the result produced by statistical analysis."""

    result = state.get("statistical_result")
    error = state.get("statistical_error")

    # Case 1: Correlation analysis failed.
    if error is not None:
        decision = {
            "decision": "UNANSWERABLE",
            "reasoning": (
                "Statistical analysis could not be completed."
            ),
            "suggested_fix": error,
        }

    # Case 2: No result was produced.
    elif result is None:
        decision = {
            "decision": "UNANSWERABLE",
            "reasoning": (
                "No statistical result was produced."
            ),
            "suggested_fix": (
                "Check the correlation selection and calculation steps."
            ),
        }

    # Case 3: Validate the returned statistical result.
    elif (
        result.get("status") == "success"
        and isinstance(
            result.get("correlation_coefficient"), (int, float)
        )
        and -1 <= result["correlation_coefficient"] <= 1
        and result.get("observations_used", 0) >= 3
    ):
        decision = {
            "decision": "APPROVE",
            "reasoning": (
                "The correlation result passed basic validation."
            ),
            "suggested_fix": None,
        }

    # Case 4: The result failed validation.
    else:
        decision = {
            "decision": "UNANSWERABLE",
            "reasoning": (
                "The statistical result failed validation."
            ),
            "suggested_fix": (
                "Review the correlation calculation and its output."
            ),
        }

    print("\nStatistical Critic Decision:", decision)

    return {
        "critic_decision": decision,
        "feedback": (
            decision.get("suggested_fix")
            or decision["reasoning"]
        ),
    }

# 3. Executor node

def executor_node(state: WorkflowState) -> dict:
    try:
        plan_data = state["plan"]

        if plan_data is None:
            raise ValueError("Planner did not produce a valid plan.")

        plan = QueryPlan.model_validate(plan_data)

        result = execute_plan(
            plan,
            db_path=state["db_path"],
        )

        return {
            "execution_result": result,
            "execution_error": None,
        }

    except Exception as exc:
        print("DEBUG executor error:", repr(exc))
        return {
            "execution_result": None,
            "execution_error": str(exc),
        }


# 4. Critic node
def critic_node(state: WorkflowState) -> dict:
    plan_data = state.get("plan")
    execution_result = state.get("execution_result")
    execution_error = state.get("execution_error")

    # Case 1: The Planner failed to produce a valid plan.
    if plan_data is None:
        decision = {
            "decision": "RETRY",
            "failure_origin": "PLANNER",
            "reasoning": "The Planner did not produce a valid plan.",
            "suggested_fix": (
                f"Correct the planning error: {execution_error}"
            ),
        }

    # Case 2: The Executor encountered an error.
    elif execution_error is not None:
        decision = {
            "decision": "RETRY",
            "failure_origin": "EXECUTOR",
            "reasoning": "The query plan could not be executed.",
            "suggested_fix": (
                f"Review and correct the execution error: "
                f"{execution_error}"
            ),
        }

    # Case 3: Execution produced no result.
    elif execution_result is None:
        decision = {
            "decision": "RETRY",
            "failure_origin": "UNKNOWN",
            "reasoning": "No execution result was produced.",
            "suggested_fix": "Review the plan and execution workflow.",
        }

    # Case 4: Execution succeeded; ask the LLM Critic to evaluate it.
    else:
        try:
            critic_result = evaluate_attempt(
                question=state["question"],
                plan=plan_data,
                execution_result=execution_result,
                execution_error=None,
            )

            decision = (
                critic_result.model_dump()
                if hasattr(critic_result, "model_dump")
                else critic_result
            )

        except Exception as exc:
            # Prevent an LLM/API failure from crashing the graph.
            decision = {
                "decision": "RETRY",
                "failure_origin": "UNKNOWN",
                "reasoning": (
                    "The Critic could not complete its evaluation."
                ),
                "suggested_fix": (
                    f"Critic evaluation error: {exc}"
                ),
            }

    print("\nCritic Decision:", decision)

    return {
        "critic_decision": decision,
        "feedback": (
            decision.get("suggested_fix")
            or decision["reasoning"]
        ),
    }

# 5. Decide what happens after Critic
def route_after_critic(state: WorkflowState) -> str:
    decision = state["critic_decision"]

    if decision is None:
        return "finish"

    if decision["decision"] in ("APPROVE", "UNANSWERABLE"):
        return "finish"

    if state["retry_count"] >= state["max_retries"]:
        return "finish"

    if decision["failure_origin"] == "PLANNER":
        return "retry_planner"

    if decision["failure_origin"] == "EXECUTOR":
        # The current Executor is deterministic. Repeating it
        # unchanged would not repair a persistent SQL error.
        return "retry_planner"

    return "finish"


# 6. Count a retry before returning to Planner
def retry_planner_node(state: WorkflowState) -> dict:
    return {
        "retry_count": state["retry_count"] + 1,
    }


# 7. Assemble the graph
def build_graph():
    workflow = StateGraph(WorkflowState)

    workflow.add_node("planner", planner_node)
    workflow.add_node("executor", executor_node)
    workflow.add_node("critic", critic_node)
    workflow.add_node("retry_planner", retry_planner_node)
    workflow.add_node("correlation", correlation_node)
    workflow.add_node("statistical_critic", statistical_critic_node)

    workflow.add_conditional_edges(
    START,
    route_analysis_method,
    {
        "planner": "planner",
        "correlation": "correlation",
    },
)
    workflow.add_conditional_edges(
        "planner",
        lambda state: (
            "critic"
            if state["execution_error"]
            else "executor"
        ),
        {
            "critic": "critic",
            "executor": "executor",
        },
    )

    workflow.add_edge("executor", "critic")

    workflow.add_conditional_edges(
        "critic",
        route_after_critic,
        {
            "finish": END,
            "retry_planner": "retry_planner",
        },
    )

    workflow.add_edge("retry_planner", "planner")
    workflow.add_edge("correlation", "statistical_critic")
    workflow.add_edge("statistical_critic", END)

    return workflow.compile()

def route_analysis_method(state: WorkflowState) -> str:
    """Choose the SQL or statistical analysis path."""
    if state["analysis_method"] == "correlation":
        return "correlation"
    return "planner"
    
# 8. Public function for running a question

def run_query(
    question: str,
    db_path: str = "data/ecommerce.db",
    max_retries: int = 2,
) -> dict:
    if isinstance(max_retries, bool) or not isinstance(max_retries, int):
        raise ValueError("max_retries must be a non-negative integer.")

    if max_retries < 0:
        raise ValueError("max_retries must be a non-negative integer.")

    graph = build_graph()

    initial_state: WorkflowState = {
    "question": question,
    "db_path": db_path,
    "analysis_method": detect_analysis_method(question),
    "statistical_result": None,
    "statistical_error": None,
    "plan": None,
    "execution_result": None,
    "execution_error": None,
    "critic_decision": None,
    "feedback": None,
    "retry_count": 0,
    "max_retries": max_retries,
}

    return graph.invoke(initial_state)

from typing import TypedDict, Any

from langgraph.graph import StateGraph, START, END

from agents.planner import QueryPlan, plan_query
from agents.executor import execute_plan
from agents.critic import evaluate_attempt


class WorkflowState(TypedDict):
    question: str
    db_path: str

    plan: dict[str, Any] | None
    execution_result: dict[str, Any] | None
    execution_error: str | None

    critic_decision: dict[str, Any] | None
    feedback: str | None
    retry_count: int
    max_retries: int


# 1. Planner node
def planner_node(state: WorkflowState) -> dict:
    try:
        plan = plan_query(
            state["question"],
            db_path=state["db_path"],
            feedback=state["feedback"],
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


# 2. Executor node
def executor_node(state: WorkflowState) -> dict:
    try:
        plan_data = state["plan"]

        if plan_data is None:
            raise ValueError(
                "Planner did not produce a valid plan."
            )

        # LangGraph state contains a dictionary.
        # Convert it back to the Pydantic QueryPlan object.
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
        return {
            "execution_result": None,
            "execution_error": str(exc),
        }


# 3. Critic node
def critic_node(state: WorkflowState) -> dict:
    plan_data = state["plan"]
    execution_error = state["execution_error"]
    execution_result = state["execution_result"]

    if execution_error and plan_data is None:
        decision = {
            "decision": "RETRY",
            "failure_origin": "PLANNER",
            "reasoning": execution_error,
            "suggested_fix": (
                "Correct the planning error using the database "
                "schema and produce a valid structured query plan."
            ),
        }

    elif execution_error:
        decision = {
            "decision": "RETRY",
            "failure_origin": "EXECUTOR",
            "reasoning": f"Execution failed: {execution_error}",
            "suggested_fix": (
                "Review the execution error and revise the plan. "
                "Check table relationships, columns, aggregations, "
                "filters, and ordering expressions."
            ),
        }

    elif execution_result is None:
        decision = {
            "decision": "RETRY",
            "failure_origin": "EXECUTOR",
            "reasoning": "No execution result was produced.",
            "suggested_fix": (
                "Review the plan and ensure the query executes "
                "and returns a result."
            ),
        }

    else:
        try:
            critic = evaluate_attempt(
                question=state["question"],
                plan=plan_data,
                execution_result=execution_result,
                execution_error=None,
            )
            decision = critic.model_dump()

        except Exception as exc:
            # Do not silently approve if the Critic itself fails.
            decision = {
                "decision": "RETRY",
                "failure_origin": "UNKNOWN",
                "reasoning": f"Critic evaluation failed: {exc}",
                "suggested_fix": (
                    "Retry the evaluation after checking the "
                    "Critic configuration and model response."
                ),
            }

    feedback = (
        decision.get("suggested_fix")
        or decision.get("reasoning")
    )

    return {
        "critic_decision": decision,
        "feedback": feedback,
    }


# 4. Route after Critic
def route_after_critic(state: WorkflowState) -> str:
    decision = state["critic_decision"]

    if decision is None:
        return "finish"

    if decision["decision"] in ("APPROVE", "UNANSWERABLE"):
        return "finish"

    if state["retry_count"] >= state["max_retries"]:
        return "finish"

    if decision["decision"] == "RETRY":
        return "retry_planner"

    return "finish"


# 5. Count retries
def retry_planner_node(state: WorkflowState) -> dict:
    return {
        "retry_count": state["retry_count"] + 1,
        # Clear the previous attempt before planning again.
        "plan": None,
        "execution_result": None,
        "execution_error": None,
        "critic_decision": None,
    }


# 6. Build the LangGraph workflow
def build_graph():
    workflow = StateGraph(WorkflowState)

    workflow.add_node("planner", planner_node)
    workflow.add_node("executor", executor_node)
    workflow.add_node("critic", critic_node)
    workflow.add_node("retry_planner", retry_planner_node)

    workflow.add_edge(START, "planner")

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

    return workflow.compile()


# 7. Run a question through the workflow
def run_query(
    question: str,
    db_path: str = "data/ecommerce.db",
    max_retries: int = 2,
) -> dict:
    if max_retries < 0:
        raise ValueError("max_retries cannot be negative.")

    graph = build_graph()

    initial_state: WorkflowState = {
        "question": question,
        "db_path": db_path,
        "plan": None,
        "execution_result": None,
        "execution_error": None,
        "critic_decision": None,
        "feedback": None,
        "retry_count": 0,
        "max_retries": max_retries,
    }

    return graph.invoke(initial_state)

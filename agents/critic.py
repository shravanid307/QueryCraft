from typing import Literal
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field


class CriticDecision(BaseModel):
    decision: Literal["APPROVE", "RETRY", "UNANSWERABLE"] = Field(
        description="Whether to approve, retry, or reject the query as unanswerable"
    )

    failure_origin: Literal[
        "NONE",
        "PLANNER",
        "EXECUTOR",
        "DATABASE",
        "UNKNOWN",
    ] = Field(
        description="Where the problem originated, if any"
    )

    reasoning: str = Field(
        description="Brief explanation supporting the decision"
    )

    suggested_fix: str | None = Field(
        default=None,
        description="Specific correction for a retry, if applicable"
    )


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def create_critic():
    if not os.getenv("GROQ_API_KEY"):
        raise RuntimeError("GROQ_API_KEY was not found in .env")

    model_name = os.getenv(
        "GROQ_MODEL",
        "openai/gpt-oss-120b",
    )

    llm = ChatGroq(
        model=model_name,
        temperature=0,
    )

    return llm.with_structured_output(
        CriticDecision,
        method="json_schema",
    )


def evaluate_attempt(
    question: str,
    plan: dict,
    execution_result: dict | None = None,
    execution_error: str | None = None,
) -> CriticDecision:
    """Evaluate whether a query adequately answers the user's question."""

    # A reported execution error must never be approved.
    if execution_error:
        return CriticDecision(
            decision="RETRY",
            failure_origin="EXECUTOR",
            reasoning=f"Execution failed: {execution_error}",
            suggested_fix=(
                "Inspect the execution error, correct the query, "
                "and retry."
            ),
        )

    if execution_result is None:
        return CriticDecision(
            decision="RETRY",
            failure_origin="EXECUTOR",
            reasoning="No execution result was provided.",
            suggested_fix=(
                "Execute the query and provide the execution result."
            ),
        )

    critic = create_critic()

    prompt = f"""
You are the Critic agent in QueryCraft, a self-correcting
natural-language-to-SQL system.

Your job is to determine whether the attempted analysis adequately
answers the user's actual question.

USER QUESTION:
{question}

PLANNER OUTPUT:
{plan}

EXECUTION RESULT:
{execution_result}

EXECUTION ERROR:
{execution_error}

Evaluate the attempt using these rules.

1. EXECUTION IS NOT PROOF OF CORRECTNESS.
A query can execute successfully and still fail to answer the question.

2. CHECK THE USER'S INTENT.
Identify the specific information or calculation the user is requesting.
Check whether the plan and results actually provide it.

3. DISTINGUISH ANALYTICAL METHODS.
Examples:
- Counting records can answer how many records exist.
- Grouping and averaging can compare group averages.
- Asking whether two numerical variables are correlated generally
  requires a correlation statistic, such as Pearson or Spearman correlation,
  or another explicitly justified statistical analysis.
- Grouping one variable and averaging another may reveal a pattern,
  but it does not by itself calculate a correlation coefficient.
- A causal question cannot be established merely by observing an association.

4. DO NOT OVERCLAIM.
Do not say a statistical relationship has been established if the
execution result contains only descriptive aggregates.
Do not claim statistical significance without a suitable statistical test.
Do not invent calculations that are absent from the result.

5. DECISION RULES.
APPROVE:
The plan and execution result adequately answer the user's question.

RETRY:
The question is answerable, but the current plan or execution does not
provide the required information, calculation, or analysis.
Identify the missing requirement and provide a specific suggested_fix.

UNANSWERABLE:
The available database information is insufficient to answer the
question reliably, and a different query against the same available
information would not resolve the limitation.

6. FAILURE ORIGIN.
PLANNER: The selected tables, columns, aggregation, or analytical method
do not match the user's intent.
EXECUTOR: The SQL construction or execution is incorrect.
DATABASE: Required information is missing or inadequate.
NONE: The attempt is approved.
UNKNOWN: The cause cannot be determined.

7. RETRY FEEDBACK.
When returning RETRY, provide an actionable correction that identifies
the missing calculation or incorrect planning decision.
Do not suggest repeating an equivalent query that has the same limitation.

8. BE EVIDENCE-BASED.
Use only the supplied question, plan, and execution result.
Do not assume that an unshown calculation was performed.
Do not invent database columns, values, or results.

Return a structured CriticDecision.
"""

    return critic.invoke(prompt)
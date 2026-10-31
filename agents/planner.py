import os
import re
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field

from agents.schema_extractor import extract_schema


# ============================================================
# 1. PROJECT CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


# ============================================================
# 2. PYDANTIC MODELS
# ============================================================

class JoinPlan(BaseModel):
    from_table: str = Field(
        description="Table containing the referencing column"
    )
    from_column: str = Field(
        description="Referencing column"
    )
    to_table: str = Field(
        description="Table containing the referenced column"
    )
    to_column: str = Field(
        description="Referenced column"
    )


class FilterPlan(BaseModel):
    column: str = Field(
        description="Column to filter on, including its table"
    )
    operator: Literal[
        "=", "!=", ">", ">=", "<", "<=",
        "LIKE", "IN", "IS NULL", "IS NOT NULL"
    ]
    value: (
        str
        | int
        | float
        | bool
        | list[str | int | float | bool]
        | None
    ) = None


class QueryPlan(BaseModel):
    tables: list[str] = Field(
        description="Tables needed for the query"
    )
    joins: list[JoinPlan] = Field(default_factory=list)
    filters: list[FilterPlan] = Field(default_factory=list)
    group_by: list[str] = Field(default_factory=list)
    aggregations: list[str] = Field(
        default_factory=list,
        description=(
            "Calculations such as "
            "COUNT(orders.order_id) AS order_count"
        ),
    )
    order_by: list[str] = Field(default_factory=list)
    limit: int | None = None
    explanation: str = Field(
        description="Brief explanation of the planned query"
    )

class CorrelationPlan(BaseModel):
    table: str = Field(
        description="Table containing both numerical columns"
    )
    column_x: str = Field(
        description="First numerical column for correlation"
    )
    column_y: str = Field(
        description="Second numerical column for correlation"
    )
    method: Literal["pearson", "spearman"] = Field(
        description="Correlation method appropriate to the question"
    )
    
# ============================================================
# 3. CREATE THE PLANNER LLM
# ============================================================

def create_planner():
    """Create a Groq-powered LLM that returns structured query plans."""

    if not os.getenv("GROQ_API_KEY"):
        raise RuntimeError(
            "GROQ_API_KEY was not found. Check the project .env file."
        )

    model_name = os.getenv(
        "GROQ_MODEL",
        "openai/gpt-oss-120b",
    )

    llm = ChatGroq(
        model=model_name,
        temperature=0,
    )

    return llm.with_structured_output(QueryPlan)

def create_correlation_selector():
    """Create a Groq-powered LLM for selecting correlation columns."""

    if not os.getenv("GROQ_API_KEY"):
        raise RuntimeError(
            "GROQ_API_KEY was not found. Check the project .env file."
        )

    model_name = os.getenv(
        "GROQ_MODEL",
        "openai/gpt-oss-120b",
    )

    llm = ChatGroq(
        model=model_name,
        temperature=0,
    )

    return llm.with_structured_output(CorrelationPlan)

def select_correlation_columns(
    question: str,
    db_path: str = "data/ecommerce.db",
) -> CorrelationPlan:
    """Select and validate columns for correlation analysis."""

    if not isinstance(question, str) or not question.strip():
        raise ValueError("The question must be a non-empty string.")

    # Read the selected database schema.
    schema = extract_schema(db_path)

    # Ask the LLM to select the table and columns.
    selector = create_correlation_selector()

    prompt = f"""
You are selecting columns for statistical correlation analysis.

USER QUESTION:
{question}

DATABASE SCHEMA:
{schema}

RULES:
1. Select a table that exists in the provided schema.
2. Both columns must belong to the same table.
3. Both columns must exist in that table.
4. Select columns suitable for numerical correlation.
5. Use Pearson for linear correlation when appropriate.
6. Use Spearman for rank-based or monotonic relationships when appropriate.
7. Do not invent tables or columns.
8. Do not claim correlation proves causation.
9. If the question does not identify two suitable columns,
   do not invent a relationship.
"""

    result = selector.invoke(prompt)

    if not isinstance(result, CorrelationPlan):
        result = CorrelationPlan.model_validate(result)

    # Validate the table.
    if result.table not in schema["tables"]:
        raise ValueError(f"Unknown table: {result.table}")

    columns = schema["tables"][result.table]["columns"]

    # Validate both columns.
    if result.column_x not in columns:
        raise ValueError(
            f"Unknown column: {result.table}.{result.column_x}"
        )

    if result.column_y not in columns:
        raise ValueError(
            f"Unknown column: {result.table}.{result.column_y}"
        )

    if result.column_x == result.column_y:
        raise ValueError("Choose two different columns.")

    return result
# ============================================================
# 4. COLUMN NAME NORMALIZATION
# ============================================================

def normalize_column_name(column: str) -> str:
    """
    Convert a qualified column name into its column component.

    Example:
        orders.customer_id -> customer_id
    """
    return column.rsplit(".", 1)[-1].strip()

def detect_analysis_method(question: str) -> str:
    """
    Identify whether a question explicitly requests correlation analysis.
    """
    question_lower = question.lower()

    correlation_keywords = (
        "correlation",
        "correlated",
        "correlate",
        "pearson",
        "spearman",
        "relationship between",
        "association between",
    )

    if any(keyword in question_lower for keyword in correlation_keywords):
        return "correlation"

    return "sql"
# ============================================================
# 5. DETERMINISTIC PLAN VALIDATION
# ============================================================

def validate_plan(plan: QueryPlan, schema: dict) -> list[str]:
    """
    Validate a query plan before SQL generation or execution.

    Returns:
        A list of validation errors.
        An empty list means the plan passed these checks.
    """

    errors = []
    tables = schema["tables"]
    relationships = schema["relationships"]

    allowed_operators = {
        "=", "!=", ">", ">=", "<", "<=",
        "LIKE", "IN", "IS NULL", "IS NOT NULL",
    }

    allowed_aggregations = {
        "COUNT", "SUM", "AVG", "MIN", "MAX",
    }

    # --------------------------------------------------------
    # Helper: resolve column references
    # --------------------------------------------------------

    def resolve_column(reference: str) -> bool:
        """
        Accept table.column references.

        Unqualified column names are accepted only when they
        belong to exactly one selected table.
        """

        if not isinstance(reference, str) or not reference.strip():
            return False

        reference = reference.strip()

        if "." in reference:
            table, column = reference.split(".", 1)

            return (
                table in tables
                and table in plan.tables
                and column in tables[table]["columns"]
            )

        matching_tables = [
            table
            for table in plan.tables
            if table in tables
            and reference in tables[table]["columns"]
        ]

        return len(matching_tables) == 1

    # --------------------------------------------------------
    # 1. Validate selected tables
    # --------------------------------------------------------

    if not plan.tables:
        errors.append(
            "The plan must include at least one table."
        )

    if len(plan.tables) != len(set(plan.tables)):
        errors.append(
            "Duplicate tables are not allowed in plan.tables."
        )

    for table in plan.tables:
        if table not in tables:
            errors.append(f"Unknown table: {table}")

    # --------------------------------------------------------
    # 2. Validate joins and relationships
    # --------------------------------------------------------

    for join in plan.joins:

        if join.from_table not in tables:
            errors.append(
                f"Unknown join table: {join.from_table}"
            )
            continue

        if join.to_table not in tables:
            errors.append(
                f"Unknown join table: {join.to_table}"
            )
            continue

        if (
            join.from_table not in plan.tables
            or join.to_table not in plan.tables
        ):
            errors.append(
                "Both tables in a join must appear in plan.tables: "
                f"{join.from_table}, {join.to_table}"
            )

        from_column = normalize_column_name(
            join.from_column
        )
        to_column = normalize_column_name(
            join.to_column
        )

        if from_column not in tables[join.from_table]["columns"]:
            errors.append(
                f"Unknown column: "
                f"{join.from_table}.{from_column}"
            )

        if to_column not in tables[join.to_table]["columns"]:
            errors.append(
                f"Unknown column: "
                f"{join.to_table}.{to_column}"
            )

        known_relationship = any(
            (
                relationship["from_table"] == join.from_table
                and relationship["from_column"] == from_column
                and relationship["to_table"] == join.to_table
                and relationship["to_column"] == to_column
            )
            or (
                relationship["from_table"] == join.to_table
                and relationship["from_column"] == to_column
                and relationship["to_table"] == join.from_table
                and relationship["to_column"] == from_column
            )
            for relationship in relationships
        )

        if not known_relationship:
            errors.append(
                "Join is not supported by known relationships: "
                f"{join.from_table}.{from_column} -> "
                f"{join.to_table}.{to_column}"
            )

    # --------------------------------------------------------
    # 3. Validate filters
    # --------------------------------------------------------

    for filter_item in plan.filters:

        if not resolve_column(filter_item.column):
            errors.append(
                "Unknown or ambiguous filter column: "
                f"{filter_item.column}"
            )

        operator = filter_item.operator.upper()
        value = filter_item.value

        if operator not in allowed_operators:
            errors.append(
                f"Unsupported filter operator: {operator}"
            )
            continue

        if operator in {"IS NULL", "IS NOT NULL"}:
            if value is not None:
                errors.append(
                    f"{operator} must not have a filter value."
                )

        elif operator == "IN":
            if not isinstance(value, list) or not value:
                errors.append(
                    "IN requires a non-empty list of values."
                )

        elif value is None:
            errors.append(
                f"Filter operator {operator} requires "
                "a non-null value."
            )

        elif isinstance(value, list):
            errors.append(
                f"Filter operator {operator} does not accept "
                "a list of values."
            )

    # --------------------------------------------------------
    # 4. Validate GROUP BY references
    # --------------------------------------------------------

    for reference in plan.group_by:
        if not resolve_column(reference):
            errors.append(
                "Unknown or ambiguous group_by reference: "
                f"{reference}"
            )

    # --------------------------------------------------------
    # 5. Validate aggregation expressions
    # --------------------------------------------------------

    aggregation_aliases = set()

    for aggregation in plan.aggregations:

        if not isinstance(aggregation, str):
            errors.append(
                f"Invalid aggregation expression: {aggregation}"
            )
            continue

        match = re.fullmatch(
            r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*"
            r"\(\s*([^()]+?)\s*\)\s*"
            r"(?:AS\s+([A-Za-z_][A-Za-z0-9_]*))?\s*",
            aggregation,
            flags=re.IGNORECASE,
        )

        if not match:
            errors.append(
                f"Invalid aggregation expression: {aggregation}"
            )
            continue

        function_name, argument, alias = match.groups()

        function_name = function_name.upper()
        argument = argument.strip()

        if function_name not in allowed_aggregations:
            errors.append(
                f"Unsupported aggregation function: {function_name}"
            )
            continue

        if argument == "*":
            if function_name != "COUNT":
                errors.append(
                    f"{function_name}(*) is not supported."
                )

        elif not resolve_column(argument):
            errors.append(
                "Unknown or ambiguous aggregation column: "
                f"{argument}"
            )

        if alias:
            alias_key = alias.lower()

            if alias_key in aggregation_aliases:
                errors.append(
                    f"Duplicate aggregation alias: {alias}"
                )

            aggregation_aliases.add(alias_key)

    # --------------------------------------------------------
    # 6. Validate ORDER BY references
    # --------------------------------------------------------

    for order_item in plan.order_by:

        if not isinstance(order_item, str):
            errors.append(
                f"Invalid order_by expression: {order_item}"
            )
            continue

        match = re.fullmatch(
            r"\s*(.+?)\s*(?:\s+(ASC|DESC))?\s*",
            order_item,
            flags=re.IGNORECASE,
        )

        if not match:
            errors.append(
                f"Invalid order_by expression: {order_item}"
            )
            continue

        reference = match.group(1).strip()

        if reference.lower() in aggregation_aliases:
            continue

        if not resolve_column(reference):
            errors.append(
                "Unknown or ambiguous order_by reference: "
                f"{reference}"
            )

    # --------------------------------------------------------
    # 7. Validate LIMIT
    # --------------------------------------------------------

    if plan.limit is not None:
        if (
            isinstance(plan.limit, bool)
            or not isinstance(plan.limit, int)
            or not 1 <= plan.limit <= 1000
        ):
            errors.append(
                "Limit must be an integer between 1 and 1000."
            )

    return errors


# ============================================================
# 6. GENERATE A QUERY PLAN
# ============================================================

def plan_query(
    question: str,
    db_path: str = "data/ecommerce.db",
    feedback: str | None = None,
) -> QueryPlan:
    """
    Generate and validate a structured query plan.

    The Planner decides which tables, joins, filters,
    aggregations, grouping, ordering, and limit are needed.

    It does not generate executable SQL.
    """

    if not isinstance(question, str) or not question.strip():
        raise ValueError(
            "The question must be a non-empty string."
        )

    # Extract the current database schema.
    schema = extract_schema(db_path)

    # Create the structured-output LLM.
    planner = create_planner()

    # Build the prompt.
    prompt = f"""
You are the Planner agent in a multi-agent SQL system.

Your job is to convert a user's natural-language question
into a structured query plan.

You must NOT generate SQL.

USER QUESTION:
{question}

DATABASE SCHEMA:
{schema}

PLANNING RULES:

1. Select only the tables needed to answer the question.

2. Use only tables and columns present in the schema.

3. Every join must follow a relationship listed in the schema.
   Do not invent joins or relationships.

4. Include both joined tables in the tables list.

5. For filters, specify the table-qualified column when possible.

6. Use only the supported filter operators:
   =, !=, >, >=, <, <=, LIKE, IN, IS NULL, IS NOT NULL.

7. For IN filters, provide a list of values.

8. For IS NULL and IS NOT NULL filters, use a null value.

9. For calculations, use only these aggregation functions:
   COUNT, SUM, AVG, MIN, MAX.

10. Write aggregation expressions in this format:
    COUNT(orders.order_id) AS order_count

11. For questions asking for the top or bottom entities,
    use the appropriate aggregation and ordering.

12. When ranking customers, include the customer identifier
    and identifying columns in group_by when appropriate:
    customers.customer_id,
    customers.first_name,
    customers.last_name

13. When grouping entities, include the necessary identifying
    columns so different entities are not accidentally combined.

14. Use the aggregation alias in order_by when available.
    For example: order_count DESC

15. Use table-qualified column names for group_by and
    aggregation arguments to avoid ambiguity.

16. Set limit only when the question requests a limited number
    of results or when a limit is otherwise appropriate.
    Any specified limit must be between 1 and 1000.

17. Keep the plan minimal and relevant to the question.

18. Do not invent tables, columns, values, or business rules.

19. Provide a brief explanation of how the plan answers
    the user's question.
"""

    # Add feedback when the graph is retrying a failed attempt.
    if feedback:
        prompt += f"""

FEEDBACK FROM THE PREVIOUS ATTEMPT:
{feedback}

Correct the previous problem. Reconsider the relevant tables,
relationships, columns, filters, aggregations, and ordering.
Do not repeat the same mistake.
"""

    # Ask the LLM to produce a structured QueryPlan.
    plan = planner.invoke(prompt)

    # Ensure the returned object has the expected type.
    if not isinstance(plan, QueryPlan):
        plan = QueryPlan.model_validate(plan)

    # Run deterministic validation before passing the plan
    # to the Executor.
    validation_errors = validate_plan(plan, schema)

    if validation_errors:
        formatted_errors = "\n".join(
            f"- {error}" for error in validation_errors
        )

        raise ValueError(
            "Planner produced an invalid query plan:\n"
            f"{formatted_errors}"
        )

    return plan
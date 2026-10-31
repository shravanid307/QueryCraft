import streamlit as st
import pandas as pd
import sqlite3
import re
from pathlib import Path

from agents.graph import run_query

# --------------------------------------------------
# Page configuration
# --------------------------------------------------
st.set_page_config(
    page_title="QueryCraft",
    page_icon="🔎",
    layout="wide",
)

# --------------------------------------------------
# Paths
# --------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploaded_databases"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_DB = DATA_DIR / "ecommerce.db"


# --------------------------------------------------
# Helper functions
# --------------------------------------------------
def clean_table_name(filename):
    name = Path(filename).stem.lower()
    name = re.sub(r"[^a-z0-9_]", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")

    if not name:
        name = "uploaded_data"

    if name[0].isdigit():
        name = f"table_{name}"

    return name


def load_dataset(uploaded_file):
    filename = uploaded_file.name.lower()

    try:
        uploaded_file.seek(0)

        if filename.endswith(".csv"):
            dataframe = pd.read_csv(uploaded_file)

        elif filename.endswith(".xlsx"):
            dataframe = pd.read_excel(
                uploaded_file,
                engine="openpyxl",
            )

        else:
            raise ValueError(
                "Unsupported file format. Upload a CSV or XLSX file."
            )

        if dataframe.empty:
            raise ValueError(
                "The file contains no data rows. Upload a file with data."
            )

        if len(dataframe.columns) == 0:
            raise ValueError(
                "No columns were found. Check that the file contains a header row."
            )

        return dataframe

    except pd.errors.EmptyDataError:
        raise ValueError(
            "The uploaded CSV is empty or contains no readable columns. "
            "Please upload a CSV containing column headers and data."
        )

    except pd.errors.ParserError:
        raise ValueError(
            "The CSV format could not be parsed. Check the delimiters "
            "and formatting, then try again."
        )

def save_dataset(uploaded_file):
    dataframe = load_dataset(uploaded_file)

    if dataframe.empty:
        raise ValueError("The uploaded file contains no data.")

    if len(dataframe.columns) == 0:
        raise ValueError("The uploaded file has no columns.")

    dataframe.columns = [
        str(column).strip() for column in dataframe.columns
    ]

    if any(not column for column in dataframe.columns):
        raise ValueError("Column names cannot be empty.")

    if len(set(dataframe.columns)) != len(dataframe.columns):
        raise ValueError("Column names must be unique.")

    table_name = clean_table_name(uploaded_file.name)
    db_path = UPLOAD_DIR / f"{table_name}.db"

    with sqlite3.connect(db_path) as connection:
        dataframe.to_sql(
            table_name,
            connection,
            if_exists="replace",
            index=False,
        )

    return db_path, table_name, dataframe


def get_available_databases():
    databases = {}

    if DEFAULT_DB.exists():
        databases["E-commerce sample database"] = str(DEFAULT_DB)

    for db_file in sorted(UPLOAD_DIR.glob("*.db")):
        label = db_file.stem.replace("_", " ").title()
        databases[f"Uploaded: {label}"] = str(db_file)

    return databases


# --------------------------------------------------
# Sidebar navigation
# --------------------------------------------------
st.sidebar.title("QueryCraft")
st.sidebar.caption("Multi-agent Natural Language to SQL")

page = st.sidebar.radio(
    "Navigation",
    ["Ask Questions", "Add Data"],
)

st.sidebar.divider()

# --------------------------------------------------
# Add Data page
# --------------------------------------------------
if page == "Add Data":
    st.title("Add Your Data")
    st.write(
        "Upload a CSV or Excel file to create an independent "
        "SQLite database for querying."
    )

    uploaded_file = st.file_uploader(
        "Choose a dataset",
        type=["csv", "xlsx"],
        help="Supported formats: CSV and Excel (.xlsx).",
    )

    if uploaded_file is not None:
        try:
            preview = load_dataset(uploaded_file)

            st.subheader("Dataset Preview")
            st.dataframe(preview.head(10), use_container_width=True)

            col1, col2 = st.columns(2)

            with col1:
                st.metric("Rows", len(preview))

            with col2:
                st.metric("Columns", len(preview.columns))

            st.subheader("Column Information")

            column_info = pd.DataFrame({
                "Column": preview.columns,
                "Data Type": preview.dtypes.astype(str).values,
                "Missing Values": preview.isna().sum().values,
            })

            st.dataframe(column_info, use_container_width=True)

            if st.button("Add Dataset", type="primary"):
                db_path, table_name, dataframe = save_dataset(
                    uploaded_file
                )

                st.success("Dataset added successfully!")

                st.write(f"**Table name:** `{table_name}`")
                st.write(f"**Rows imported:** {len(dataframe)}")
                st.write(f"**Columns imported:** {len(dataframe.columns)}")

                st.info(
                    "Your dataset has been saved in its own SQLite "
                    "database. Open Ask Questions to query it."
                )

        except Exception as exc:
            st.error(f"Could not process the dataset: {exc}")


# --------------------------------------------------
# Ask Questions page
# --------------------------------------------------
else:
    st.title("QueryCraft")
    st.caption(
        "Ask questions in natural language. The Planner, Executor, "
        "and Critic work together to generate and validate SQL."
    )

    databases = get_available_databases()

    if not databases:
        st.warning("No databases are available. Add a dataset first.")
        st.stop()

    selected_database = st.selectbox(
        "Select a database",
        options=list(databases.keys()),
    )

    db_path = databases[selected_database]

    question = st.text_input(
        "Ask a question about your data",
        placeholder="e.g., What are the top 5 records?",
    )

    run_button = st.button("Run Query", type="primary")

    if run_button:
        if not question.strip():
            st.warning("Please enter a question first.")

        else:
            with st.spinner(
                "Planner, Executor, and Critic are working..."
            ):
                try:
                    result = run_query(
                        question,
                        db_path=db_path,
                    )

                    st.session_state["querycraft_result"] = result
                    st.session_state["querycraft_question"] = question
                    st.session_state["querycraft_database"] = db_path

                except Exception as exc:
                    st.error(f"An unexpected error occurred: {exc}")

    
    result = st.session_state.get("querycraft_result")

    if (
        result
        and st.session_state.get("querycraft_database") == db_path
    ):
        st.divider()

        analysis_method = result.get("analysis_method", "sql")
        critic_decision = result.get("critic_decision") or {}

        # --------------------------------------------------
        # Correlation Analysis Results
        # --------------------------------------------------
        if analysis_method == "correlation":
            st.subheader("Correlation Analysis")

            statistical_result = result.get("statistical_result")
            statistical_error = result.get("statistical_error")

            if (
                statistical_result
                and statistical_result.get("status") == "success"
            ):
                coefficient = statistical_result.get(
                    "correlation_coefficient"
                )
                p_value = statistical_result.get("p_value")
                observations = statistical_result.get(
                    "observations_used", 0
                )
                excluded = statistical_result.get(
                    "observations_excluded", 0
                )

                column_x = statistical_result.get("column_x", "Unknown")
                column_y = statistical_result.get("column_y", "Unknown")
                method = statistical_result.get(
                    "method", "pearson"
                ).title()

                col1, col2, col3 = st.columns(3)

                with col1:
                    st.metric(
                        "Correlation Coefficient",
                        f"{coefficient:.4f}",
                    )

                with col2:
                    st.metric(
                        "Correlation Strength",
                        statistical_result.get(
                            "strength", "Unknown"
                        ).title(),
                    )

                with col3:
                    st.metric(
                        "Direction",
                        statistical_result.get(
                            "direction", "Unknown"
                        ).title(),
                    )

                st.write(
                    f"**Variables:** `{column_x}` and `{column_y}`"
                )
                st.write(f"**Method:** {method}")

                col4, col5, col6 = st.columns(3)

                with col4:
                    st.metric("Valid Observations", observations)

                with col5:
                    st.metric("Excluded Observations", excluded)

                with col6:
                    if p_value is not None:
                        st.metric("P-value", f"{p_value:.4e}")
                    else:
                        st.metric("P-value", "Not available")

                st.info(
                    statistical_result.get(
                        "interpretation_note",
                        "Correlation indicates association, not causation.",
                    )
                )

                if p_value is not None:
                    if p_value < 0.05:
                        st.write(
                            "**Statistical significance:** "
                            "The p-value is below 0.05."
                        )
                    else:
                        st.write(
                            "**Statistical significance:** "
                            "The p-value is not below 0.05."
                        )

            elif statistical_error:
                st.error(
                    "The correlation analysis could not be completed."
                )
                st.code(statistical_error)

            else:
                st.warning(
                    "No successful correlation result is available."
                )

        # --------------------------------------------------
        # SQL Query Results
        # --------------------------------------------------
        else:
            st.subheader("SQL Query Results")

            execution_result = result.get("execution_result")
            execution_error = result.get("execution_error")

            if (
                execution_result
                and execution_result.get("status") == "success"
            ):
                rows = execution_result.get("rows", [])
                columns = execution_result.get("columns", [])

                if rows:
                    dataframe = pd.DataFrame(
                        rows,
                        columns=columns,
                    )
                    st.dataframe(
                        dataframe,
                        use_container_width=True,
                    )
                else:
                    st.info(
                        "The query executed successfully but returned no rows."
                    )

                st.caption(
                    f"Rows returned: "
                    f"{execution_result.get('row_count', len(rows))}"
                )

                with st.expander("Generated SQL"):
                    st.code(
                        execution_result.get("sql", ""),
                        language="sql",
                    )

                with st.expander("Query Plan"):
                    st.json(result.get("plan") or {})

            elif execution_error:
                st.error(
                    "The system could not execute the query successfully."
                )
                st.code(execution_error)

            else:
                st.info(
                    "No successful query result is available."
                )

        # --------------------------------------------------
        # Critic Assessment (shared by both routes)
        # --------------------------------------------------
        st.subheader("Critic Assessment")

        decision = critic_decision.get("decision", "UNKNOWN")
        reasoning = critic_decision.get(
            "reasoning",
            "No assessment available.",
        )

        if decision == "APPROVE":
            st.success(f"Decision: {decision}")
        elif decision == "UNANSWERABLE":
            st.warning(f"Decision: {decision}")
        else:
            st.error(f"Decision: {decision}")

        st.write(f"**Reasoning:** {reasoning}")

        if analysis_method == "sql":
            failure_origin = critic_decision.get(
                "failure_origin", "UNKNOWN"
            )
            st.write(f"**Failure origin:** {failure_origin}")
            st.write(
                f"**Retries used:** {result.get('retry_count', 0)}"
            )

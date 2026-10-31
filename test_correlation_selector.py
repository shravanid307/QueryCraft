from agents.planner import select_correlation_columns

result = select_correlation_columns(
    question="Is alcohol correlated with quality?",
    db_path="data/uploaded_databases/WineQT.db",
)

print("Selected table:", result.table)
print("Column X:", result.column_x)
print("Column Y:", result.column_y)
print("Method:", result.method)
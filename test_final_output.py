from agents.graph import run_query
from pprint import pprint

result = run_query(
    "Which 5 customers placed the most orders?"
)

print("\n--- FINAL GRAPH OUTPUT ---")
pprint(result)

print("\n--- GENERATED SQL ---")
execution = result.get("execution_result")

if execution:
    print(execution["sql"])
    print("\n--- RESULTS ---")
    print(execution["columns"])
    pprint(execution["rows"])
else:
    print("Execution failed:", result.get("execution_error"))

print("\n--- CRITIC DECISION ---")
pprint(result.get("critic_decision"))

print("\n--- RETRY COUNT ---")
print(result["retry_count"])
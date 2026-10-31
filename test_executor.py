
from agents.planner import plan_query
from agents.executor import execute_plan

question = "Which 5 customers placed the most orders?"

plan = plan_query(question)

print("\nGenerated plan:")
print(plan.model_dump_json(indent=2))

result = execute_plan(plan)

print("\nGenerated SQL:")
print(result["sql"])

print("\nColumns:")
print(result["columns"])

print("\nRows:")
for row in result["rows"]:
    print(row)

print("\nStatus:", result["status"])

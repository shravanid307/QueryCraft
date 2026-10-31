
# from agents.planner import plan_query
# from agents.executor import execute_plan
# from agents.critic import evaluate_attempt

# question = "Which 5 customers placed the most orders?"

# plan = plan_query(question)
# result = execute_plan(plan)

# decision = evaluate_attempt(
#     question=question,
#     plan=plan.model_dump(),
#     execution_result=result
# )

# print(decision.model_dump_json(indent=2))


from agents.planner import plan_query
from agents.critic import evaluate_attempt

question = "Which 5 customers placed the most orders?"

plan = plan_query(question)

decision = evaluate_attempt(
    question=question,
    plan=plan.model_dump(),
    execution_result=None,
    execution_error="SQLite OperationalError: near 'FORM': syntax error"
)

print(decision.model_dump_json(indent=2))

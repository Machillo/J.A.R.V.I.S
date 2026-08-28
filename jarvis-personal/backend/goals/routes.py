from fastapi import APIRouter
from backend.goals.goal_analyzer import analyze_goal_by_id, analyze_all_goals
from backend.goals.goal_planner import generate_goal_plan

from backend.goals.models import (
    FinancialGoalRequest,
    FinancialGoalUpdateRequest,
    GoalContributionRequest,
)

from backend.goals.service import (
    add_financial_goal,
    get_financial_goals,
    get_financial_goal,
    update_financial_goal,
    delete_financial_goal,
    add_goal_contribution,
)


router = APIRouter(prefix="/goals", tags=["Goals"])


@router.post("/")
def create_goal(request: FinancialGoalRequest):
    return add_financial_goal(
        name=request.name,
        target_amount=request.target_amount,
        current_amount=request.current_amount,
        target_date=request.target_date,
        priority=request.priority,
    )


@router.get("/")
def goals():
    return get_financial_goals()


@router.get("/{goal_id}")
def goal(goal_id: int):
    return get_financial_goal(goal_id)


@router.put("/{goal_id}")
def edit_goal(goal_id: int, request: FinancialGoalUpdateRequest):
    return update_financial_goal(
        goal_id=goal_id,
        name=request.name,
        target_amount=request.target_amount,
        current_amount=request.current_amount,
        target_date=request.target_date,
        priority=request.priority,
        status=request.status,
    )


@router.delete("/{goal_id}")
def remove_goal(goal_id: int):
    return delete_financial_goal(goal_id)


@router.patch("/{goal_id}/contribute")
def contribute_to_goal(goal_id: int, request: GoalContributionRequest):
    return add_goal_contribution(
        goal_id=goal_id,
        amount=request.amount,
    )

@router.get("/analysis/all")
def all_goals_analysis():
    return analyze_all_goals()


@router.get("/{goal_id}/analysis")
def goal_analysis(goal_id: int):
    return analyze_goal_by_id(goal_id)

@router.get("/{goal_id}/plan")
def goal_plan(goal_id: int):
    return generate_goal_plan(goal_id)
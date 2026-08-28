from backend.finance.service import get_financial_summary
from backend.finance.allocation_engine import calculate_allocation_plan
from backend.finance.strategy_rules import select_recommended_strategy


def get_debt_target_from_strategy(strategy: dict):
    strategy_data = strategy.get("strategy")

    if not strategy_data:
        return None

    priority_order = strategy_data.get("priority_order", [])

    if not priority_order:
        return None

    return priority_order[0]


def build_debt_allocation(amount: float, strategy: dict, reason: str):
    debt_target = get_debt_target_from_strategy(strategy)

    if not debt_target:
        return {
            "target_type": "debt",
            "target": "Pago extraordinario de deuda",
            "amount": amount,
            "reason": reason
        }

    return {
        "target_type": "debt",
        "target": debt_target["name"],
        "debt_id": debt_target["id"],
        "amount": amount,
        "reason": (
            f"{reason} Según la estrategia {strategy['name']}, "
            f"la deuda prioritaria es {debt_target['name']}."
        )
    }


def decide_extra_money(
    amount: float,
    source: str = "extra_money",
    description: str = ""
):
    summary = get_financial_summary()
    allocation_plan = calculate_allocation_plan()
    strategy = select_recommended_strategy()

    debt_total = summary["debts"]["debt_total"]

    allocations = []
    remaining_extra_money = amount

    if allocation_plan["status"] != "OK":
        return {
            "status": "ERROR",
            "message": "No fue posible generar una recomendación."
        }

    goal_allocations = [
        item
        for item in allocation_plan["allocations"]
        if item["target_type"] == "goal"
    ]

    if allocation_plan["urgent_critical_goal"] and goal_allocations:
        for goal in goal_allocations:
            if remaining_extra_money <= 0:
                break

            goal_data = next(
                (
                    item for item in allocation_plan["goals"]
                    if item["id"] == goal["target_id"]
                ),
                None
            )

            if not goal_data:
                continue

            goal_remaining = goal_data["remaining_amount"]
            amount_to_goal = min(remaining_extra_money, goal_remaining)

            allocations.append({
                "target_type": "goal",
                "target": goal["target_name"],
                "goal_id": goal["target_id"],
                "amount": amount_to_goal,
                "reason": "Meta crítica activa."
            })

            remaining_extra_money -= amount_to_goal

        if remaining_extra_money > 0 and debt_total > 0:
            allocations.append(
                build_debt_allocation(
                    amount=remaining_extra_money,
                    strategy=strategy,
                    reason="Sobrante después de cubrir meta crítica."
                )
            )

            remaining_extra_money = 0

        elif remaining_extra_money > 0:
            allocations.append({
                "target_type": "savings",
                "target": "Ahorro disponible",
                "amount": remaining_extra_money,
                "reason": "Sobrante después de cubrir meta crítica."
            })

            remaining_extra_money = 0

        reason = (
            "Existe una meta crítica activa. Primero se cubre esa meta. "
            "Si sobra dinero, se redirige según la estrategia recomendada."
        )

    elif debt_total > 0:
        allocations.append(
            build_debt_allocation(
                amount=remaining_extra_money,
                strategy=strategy,
                reason="Existen deudas activas."
            )
        )

        remaining_extra_money = 0

        reason = (
            "Existen deudas activas. "
            "La recomendación es usar el dinero extra para acelerar pagos según la estrategia activa."
        )

    else:
        allocations.append({
            "target_type": "savings_investment",
            "target": "Ahorro e inversión",
            "amount": remaining_extra_money,
            "reason": "No existen deudas críticas ni metas urgentes."
        })

        remaining_extra_money = 0

        reason = (
            "No existen deudas críticas ni metas urgentes. "
            "La recomendación es fortalecer ahorro e inversión."
        )

    return {
        "status": "OK",
        "source": source,
        "description": description,
        "extra_amount": amount,
        "decision_reason": reason,
        "strategy_used": strategy["name"],
        "recommended_allocations": allocations
    }
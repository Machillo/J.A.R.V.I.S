from fastapi import APIRouter

from backend.reports.service import (
    get_weekly_report,
    get_monthly_report,
    get_annual_report,
)


router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("/weekly")
def weekly_report():
    return get_weekly_report()


@router.get("/monthly")
def monthly_report():
    return get_monthly_report()


@router.get("/annual")
def annual_report():
    return get_annual_report()
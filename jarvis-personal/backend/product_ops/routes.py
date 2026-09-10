from fastapi import APIRouter

from backend.auth.current_user import require_roles
from backend.product_ops.models import FeedbackCreate, FeedbackUpdate, ProductEvent, TestPaymentUpdate
from backend.product_ops.service import catalog, create_feedback, list_feedback, owner_dashboard, record_event, resolve_test_order, update_feedback

router = APIRouter(prefix="/product-ops", tags=["Product Operations"])

@router.get("/billing/catalog")
def billing_catalog(): return catalog()

@router.post("/events")
def event(payload: ProductEvent): return record_event(**payload.model_dump())

@router.get("/feedback")
def feedback_list(): return list_feedback()

@router.post("/feedback")
def feedback_create(payload: FeedbackCreate): return create_feedback(payload)

@router.get("/owner/dashboard")
def dashboard(): require_roles("owner"); return owner_dashboard()

@router.post("/owner/orders/{order_id}")
def payment(order_id: int, payload: TestPaymentUpdate): require_roles("owner"); return resolve_test_order(order_id, payload.action)

@router.patch("/owner/feedback/{ticket_id}")
def feedback_update(ticket_id: int, payload: FeedbackUpdate): require_roles("owner"); return update_feedback(ticket_id, payload)

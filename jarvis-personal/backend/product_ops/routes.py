from fastapi import APIRouter, File, UploadFile
from fastapi.responses import Response

from backend.auth.current_user import require_roles
from backend.product_ops.models import FeedbackCreate, FeedbackUpdate, ProductEvent, TestPaymentUpdate
from backend.product_ops.service import MAX_RECEIPT_BYTES, catalog, create_feedback, get_receipt, list_feedback, owner_dashboard, record_event, resolve_test_order, submit_receipt, update_feedback

router = APIRouter(prefix="/product-ops", tags=["Product Operations"])

@router.get("/billing/catalog")
def billing_catalog(): return catalog()

@router.post("/events")
def event(payload: ProductEvent): return record_event(**payload.model_dump())

@router.get("/feedback")
def feedback_list(): return list_feedback()

@router.post("/billing/orders/{order_id}/receipt")
async def receipt_submit(order_id: int, receipt: UploadFile = File(...)):
    content = await receipt.read(MAX_RECEIPT_BYTES + 1)
    return submit_receipt(order_id, receipt.filename or "comprobante", receipt.content_type or "", content)

@router.post("/feedback")
def feedback_create(payload: FeedbackCreate): return create_feedback(payload)

@router.get("/owner/dashboard")
def dashboard(): require_roles("owner"); return owner_dashboard()

@router.post("/owner/orders/{order_id}")
def payment(order_id: int, payload: TestPaymentUpdate): require_roles("owner"); return resolve_test_order(order_id, payload.action)

@router.get("/owner/orders/{order_id}/receipt")
def receipt_download(order_id: int):
    require_roles("owner")
    row = get_receipt(order_id)
    filename = str(row.get("receipt_filename") or "comprobante").replace('"', "").replace("\r", "").replace("\n", "")
    return Response(
        content=row["receipt_data"],
        media_type=row.get("receipt_content_type") or "application/octet-stream",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Content-Security-Policy": "sandbox",
            "X-Content-Type-Options": "nosniff",
        },
    )

@router.patch("/owner/feedback/{ticket_id}")
def feedback_update(ticket_id: int, payload: FeedbackUpdate): require_roles("owner"); return update_feedback(ticket_id, payload)

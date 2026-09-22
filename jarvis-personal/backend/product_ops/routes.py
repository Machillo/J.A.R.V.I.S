from fastapi import APIRouter, File, Query, UploadFile
from fastapi.responses import Response

from backend.auth.current_user import require_roles
from backend.product_ops.models import AutomaticIncidentCreate, FeatureFlagUpdate, FeedbackCreate, FeedbackResolutionUpdate, FeedbackUpdate, ProductEvent, ReleasePolicyUpdate, StoreLifecycleSimulation, TestPaymentUpdate
from backend.product_ops.service import MAX_RECEIPT_BYTES, catalog, create_automatic_incident, create_feedback, get_receipt, list_feedback, owner_dashboard, platform_health, record_event, release_policy, resend_feedback_email, resolve_test_order, send_discord_test, submit_receipt, update_feature_flag, update_feedback, update_release_policy, update_user_feedback_resolution
from backend.core.feature_flags import user_feature_flags
from backend.product_ops.store_billing import entitlement_state, restore_owner_access, simulate_lifecycle, store_catalog

router = APIRouter(prefix="/product-ops", tags=["Product Operations"])

@router.get("/billing/catalog")
def billing_catalog(): return catalog()

@router.get("/billing/store/catalog")
def billing_store_catalog(): return store_catalog()

@router.get("/billing/store/entitlement")
def billing_store_entitlement(): return entitlement_state()

@router.post("/owner/billing/store/restore-owner-access")
def billing_store_restore_owner_access():
    require_roles("owner")
    return restore_owner_access()

@router.post("/owner/billing/store/simulate/{target_account_id}")
def billing_store_simulate_account(target_account_id: str, payload: StoreLifecycleSimulation):
    require_roles("owner")
    return simulate_lifecycle(**payload.model_dump(), target_account_id=target_account_id)

@router.post("/owner/billing/store/simulate")
def billing_store_simulate(payload: StoreLifecycleSimulation):
    require_roles("owner")
    return simulate_lifecycle(**payload.model_dump())

@router.post("/events")
def event(payload: ProductEvent): return record_event(**payload.model_dump())

@router.get("/feedback")
def feedback_list(): return list_feedback()

@router.get("/health")
def health(): return platform_health()

@router.get("/release-policy")
def get_release_policy(
    platform: str = Query(max_length=20, pattern=r"^(android|ios|web)$"),
    version: str = Query(max_length=30),
):
    return release_policy(platform, version)

@router.get("/feature-flags")
def feature_flags(): return user_feature_flags()

@router.post("/billing/orders/{order_id}/receipt")
async def receipt_submit(order_id: int, receipt: UploadFile = File(...)):
    content = await receipt.read(MAX_RECEIPT_BYTES + 1)
    return submit_receipt(order_id, receipt.filename or "comprobante", receipt.content_type or "", content)

@router.post("/feedback")
def feedback_create(payload: FeedbackCreate): return create_feedback(payload)

@router.patch("/feedback/{ticket_id}/resolution")
def feedback_resolution(ticket_id: int, payload: FeedbackResolutionUpdate):
    return update_user_feedback_resolution(ticket_id, payload.resolution)

@router.post("/incidents")
def incident_create(payload: AutomaticIncidentCreate): return create_automatic_incident(payload)

@router.get("/owner/dashboard")
def dashboard(): require_roles("owner"); return owner_dashboard()

@router.patch("/owner/release-policy/{platform}")
def release_policy_update(platform: str, payload: ReleasePolicyUpdate):
    require_roles("owner")
    return update_release_policy(platform, payload)

@router.patch("/owner/feature-flags/{flag_key}")
def feature_flag_update(flag_key: str, payload: FeatureFlagUpdate):
    require_roles("owner")
    return update_feature_flag(flag_key, payload)

@router.post("/owner/support/discord/test")
def discord_test(): require_roles("owner"); return send_discord_test()

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

@router.post("/owner/feedback/{ticket_id}/resend")
def feedback_resend(ticket_id: int): require_roles("owner"); return resend_feedback_email(ticket_id)

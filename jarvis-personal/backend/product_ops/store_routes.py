from typing import Any

from fastapi import APIRouter, Body, Header
from pydantic import BaseModel, Field

from backend.product_ops import store_verification

# Mounted at /product-ops like the rest of product operations. The notification and
# cron paths are listed in main.PUBLIC_PATHS: they authenticate by the store's
# signature, Google's OIDC token or the cron secret, never by a user session.
router = APIRouter(prefix="/product-ops/billing/store", tags=["Store billing"])


class AppleTransaction(BaseModel):
    signed_transaction: str = Field(min_length=20, max_length=20000)


class GooglePurchase(BaseModel):
    purchase_token: str = Field(min_length=10, max_length=4096)
    product_id: str = Field(min_length=1, max_length=200)


class AppleNotification(BaseModel):
    signedPayload: str = Field(min_length=20, max_length=60000)


@router.post("/customer-token")
def store_customer_token():
    return store_verification.my_customer_token()


@router.post("/apple/transactions")
def store_apple_transaction(payload: AppleTransaction):
    return store_verification.verify_apple_transaction(payload.signed_transaction)


@router.post("/google/purchases")
def store_google_purchase(payload: GooglePurchase):
    return store_verification.verify_google_purchase(payload.purchase_token, payload.product_id)


@router.post("/apple/notifications")
def store_apple_notification(payload: AppleNotification):
    return store_verification.apple_notification(payload.signedPayload)


@router.post("/google/notifications")
def store_google_notification(body: dict[str, Any] = Body(...), authorization: str | None = Header(default=None)):
    return store_verification.google_notification(authorization, body)


@router.post("/cron")
def store_lapse_cron(x_cron_secret: str | None = Header(default=None)):
    return store_verification.lapse_cron(x_cron_secret)

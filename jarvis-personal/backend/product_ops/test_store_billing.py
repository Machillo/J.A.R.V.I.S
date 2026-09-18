from backend.product_ops.store_billing import PRODUCTS, store_catalog


def test_store_catalog_has_monthly_and_annual_products():
    catalog = store_catalog()
    assert catalog["currency"] == "CRC"
    assert catalog["trial_days"] > 0
    plans = {item["code"]: item for item in catalog["plans"]}
    assert set(plans) == {"basic", "vip"}
    for code in ("basic", "vip"):
        assert plans[code]["monthly"]["product_id"] == PRODUCTS[code]["monthly"]["product_id"]
        assert plans[code]["annual"]["product_id"] == PRODUCTS[code]["annual"]["product_id"]
        assert plans[code]["annual"]["price_crc"] > plans[code]["monthly"]["price_crc"]

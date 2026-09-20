"""
The one "tool" our agent can use: look up a Sales Order in the
SAP API Business Hub sandbox (API_SALES_ORDER_SRV).
"""
import os
import requests
import streamlit as st

# Confirm this against the "Code Snippets → cURL" button on the
# API_SALES_ORDER_SRV try-it-out page (section 04.1) — SAP occasionally
# adjusts the sandbox hostname.
SANDBOX_HOST = "https://sandbox.api.sap.com/s4hanacloud"
SERVICE_PATH = "/sap/opu/odata/sap/API_SALES_ORDER_SRV/A_SalesOrder"


def _api_key() -> str:
    # Works whether the key comes from a shell env var (CLI testing)
    # or Streamlit secrets (app.py / Streamlit Cloud).
    return os.environ.get("SAP_API_KEY") or st.secrets.get("SAP_API_KEY", "")


def get_sales_order(sales_order_id: str) -> dict:
    """Fetch one sales order by ID and return the fields an AR user cares about.

    Returns found: True with the order's fields, found: False with no
    "error" key if the order genuinely doesn't exist (404), or found: False
    WITH an "error" key if something went wrong technically (bad/rejected
    key, network problem, unexpected SAP error) — the agent's system prompt
    tells the model to explain these two cases differently instead of
    treating a technical failure as if the order just wasn't found.
    """
    url = f"{SANDBOX_HOST}{SERVICE_PATH}('{sales_order_id}')"
    headers = {"APIKey": _api_key(), "Accept": "application/json"}
    params = {"$format": "json"}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
    except requests.exceptions.RequestException as exc:
        return {"found": False, "sales_order_id": sales_order_id,
                "error": f"Could not reach the SAP sandbox: {exc}"}

    if response.status_code == 404:
        return {"found": False, "sales_order_id": sales_order_id}

    if response.status_code in (401, 403):
        return {"found": False, "sales_order_id": sales_order_id,
                "error": "SAP rejected the API key (401/403). Regenerate the "
                         "sandbox key on api.sap.com, or the sandbox itself may "
                         "be having a known issue — see Annex A.3."}

    if not response.ok:
        return {"found": False, "sales_order_id": sales_order_id,
                "error": f"SAP returned an unexpected error ({response.status_code})."}

    data = response.json().get("d", {})
    return {
        "found": True,
        "sales_order_id": data.get("SalesOrder", sales_order_id),
        "order_type": data.get("SalesOrderType"),
        "sold_to_party": data.get("SoldToParty"),
        "creation_date": data.get("CreationDate"),
        "net_amount": data.get("TotalNetAmount"),
        "currency": data.get("TransactionCurrency"),
        "overall_status": data.get("OverallSDProcessStatus"),
    }
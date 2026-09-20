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
# Entity sets below A_SalesOrderItem/Partner/RelatedObject live directly
# under the service root, unlike A_SalesOrder('id') which is one named
# entity — hence a separate base path plus a $filter instead of a key.
ENTITY_BASE = "/sap/opu/odata/sap/API_SALES_ORDER_SRV"


def _fetch_entity_set(entity_set: str, sales_order_id: str) -> tuple[list, str | None]:
    """Fetch every row for one sales order from one entity set.

    Returns (rows, None) on success, or ([], "what went wrong") on failure.
    Same graceful-error idea as get_sales_order() — reused here across all
    three new entity sets instead of repeating the try/except three times.
    """
    url = f"{SANDBOX_HOST}{ENTITY_BASE}/{entity_set}"
    headers = {"APIKey": _api_key(), "Accept": "application/json"}
    params = {"$format": "json", "$filter": f"SalesOrder eq '{sales_order_id}'"}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
    except requests.exceptions.RequestException as exc:
        return [], f"could not reach {entity_set}: {exc}"

    if response.status_code in (401, 403):
        return [], f"SAP rejected the API key while fetching {entity_set} (401/403)"

    if not response.ok:
        return [], f"{entity_set} returned an unexpected error ({response.status_code})"

    return response.json().get("d", {}).get("results", []), None


def get_full_order_details(sales_order_id: str) -> dict:
    """Fetch items, header- and item-level partners, and related objects
    (linked documents such as deliveries or invoices) for one sales order.

    Use this for "what's in this order" / "who's involved" / "what's linked
    to it" questions — get_sales_order() alone only covers order status.
    """
    items, items_err = _fetch_entity_set("A_SalesOrderItem", sales_order_id)
    hdr_partners, hdr_err = _fetch_entity_set("A_SalesOrderHeaderPartner", sales_order_id)
    item_partners, itmp_err = _fetch_entity_set("A_SalesOrderItemPartner", sales_order_id)
    related, related_err = _fetch_entity_set("A_SalesOrderRelatedObject", sales_order_id)

    errors = [e for e in (items_err, hdr_err, itmp_err, related_err) if e]
    got_any_data = items or hdr_partners or item_partners or related

    if errors and not got_any_data:
        # Every call failed outright — a technical problem, not "nothing here."
        return {"found": False, "sales_order_id": sales_order_id,
                "error": "; ".join(errors)}

    if not got_any_data and not errors:
        # Calls all succeeded but came back empty — order likely doesn't
        # exist, or genuinely has none of these recorded.
        return {"found": False, "sales_order_id": sales_order_id}

    return {
        "found": True,
        "sales_order_id": sales_order_id,
        "items": [
            {
                "item_number": i.get("SalesOrderItem"),
                "material": i.get("Material"),
                "description": i.get("SalesOrderItemText"),
                "quantity": i.get("RequestedQuantity"),
                "unit": i.get("RequestedQuantityUnit"),
                "net_amount": i.get("NetAmount"),
                "currency": i.get("TransactionCurrency"),
            }
            for i in items
        ],
        "partners": {
            "header": [
                {"function": p.get("PartnerFunction"), "customer": p.get("Customer")}
                for p in hdr_partners
            ],
            "item_level": [
                {
                    "item_number": p.get("SalesOrderItem"),
                    "function": p.get("PartnerFunction"),
                    "customer": p.get("Customer"),
                }
                for p in item_partners
            ],
        },
        "related_objects": [
            {
                "related_object": r.get("RelatedObject"),
                "related_object_type": r.get("RelatedObjectType"),
            }
            for r in related
        ],
        # Partial failures (e.g. one entity set 401'd, others worked) ride
        # along here instead of silently vanishing.
        "warnings": errors or None,
    }
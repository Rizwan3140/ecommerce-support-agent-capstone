"""Deterministic mock backend APIs used by the support assistant.

These functions stand in for OMS, returns, refund, and catalog services.
They are intentionally simple and side-effect free for repeatable demos.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
ORDERS_PATH = ROOT / "data" / "mock_orders.json"
PRODUCTS_PATH = ROOT.parent / "Sample_Ecommerce_Capstone_Dataset" / "Products.json"
DEMO_TODAY = date(2026, 7, 1)


def extract_order_id(text: str, order_context: dict[str, Any] | None = None) -> str | None:
    """Find an order id from context or free text."""
    order_context = order_context or {}
    for key in ("order_id", "order_number", "id"):
        value = order_context.get(key)
        if value:
            return str(value).strip().lstrip("#")

    match = re.search(r"(?:order\s*(?:id|number|#)?\s*[:#-]?\s*|#)(\d{4,})", text, re.I)
    if match:
        return match.group(1)
    return None


def load_orders() -> list[dict[str, Any]]:
    with open(ORDERS_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_products() -> list[dict[str, Any]]:
    with open(PRODUCTS_PATH, encoding="utf-8") as f:
        return json.load(f)


def get_order_status(order_id: str) -> dict[str, Any]:
    """Mock OMS lookup."""
    order_id = str(order_id).strip().lstrip("#")
    for order in load_orders():
        if str(order.get("order_id")) == order_id:
            return {
                "ok": True,
                "tool": "get_order_status",
                "order": order,
                "message": _order_status_message(order),
            }
    return {
        "ok": False,
        "tool": "get_order_status",
        "order_id": order_id,
        "message": "Order not found. Ask the customer to confirm the order ID.",
    }


def create_return_request(order_id: str, reason: str) -> dict[str, Any]:
    """Mock returns API. It validates rough eligibility but does not persist state."""
    status = get_order_status(order_id)
    if not status.get("ok"):
        return {
            "ok": False,
            "tool": "create_return_request",
            "order_id": order_id,
            "message": "Cannot create a return because the order was not found.",
        }

    order = status["order"]
    if str(order.get("order_status", "")).lower() != "delivered":
        return {
            "ok": False,
            "tool": "create_return_request",
            "order_id": order_id,
            "message": "Return cannot be created until the order is delivered.",
            "order_status": order.get("order_status"),
        }

    if str(order.get("return_status", "")).lower() == "return_requested":
        return {
            "ok": True,
            "tool": "create_return_request",
            "order_id": order_id,
            "rma_id": f"RMA-{order_id}",
            "message": "A return request already exists for this order.",
        }

    eligible, note = _is_inside_return_window(order)
    if not eligible:
        return {
            "ok": False,
            "tool": "create_return_request",
            "order_id": order_id,
            "message": note,
        }

    return {
        "ok": True,
        "tool": "create_return_request",
        "order_id": order_id,
        "rma_id": f"RMA-{order_id}",
        "pickup_eta": "1-2 business days",
        "reason": reason or "customer_request",
        "message": "Return request created. Pickup will be scheduled in 1-2 business days.",
    }


def get_refund_policy() -> dict[str, Any]:
    """Mock policy tool for refund timelines in the supplied sample dataset."""
    return {
        "ok": True,
        "tool": "get_refund_policy",
        "window": "Most products are returnable within 7 days of delivery if unused and complete.",
        "timeline": "Refunds are processed after quality check, usually within 3-7 business days.",
        "exceptions": [
            "hygiene or personal care items",
            "software licenses and digital subscriptions",
            "items explicitly marked non-returnable",
        ],
    }


def search_products(query: str) -> dict[str, Any]:
    """Mock product catalog search over the sample Products.json file."""
    q = (query or "").lower()
    products = load_products()
    matches: list[dict[str, Any]] = []
    for product in products:
        haystack = " ".join(
            [
                str(product.get("id", "")),
                str(product.get("name", "")),
                str(product.get("category", "")),
                str(product.get("description", "")),
                json.dumps(product.get("specs", {})),
            ],
        ).lower()
        if any(token in haystack for token in _query_tokens(q)):
            matches.append(product)

    return {
        "ok": True,
        "tool": "search_products",
        "query": query,
        "matches": matches[:3],
        "message": f"Found {len(matches[:3])} matching product(s).",
    }


def run_mock_tools(ticket: str, order_context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Choose relevant mock tools from the customer ticket."""
    order_context = order_context or {}
    text = (ticket or "").lower()
    results: list[dict[str, Any]] = []
    order_id = extract_order_id(ticket, order_context)

    wants_order = any(word in text for word in ("where is", "track", "tracking", "status", "shipped", "delivery"))
    wants_return = any(word in text for word in ("return", "replace", "replacement", "refund", "damaged", "wrong product"))
    wants_product = any(word in text for word in ("spec", "hdmi", "battery", "bluetooth", "monitor", "charger", "headphone", "earbud"))

    if order_id and (wants_order or wants_return):
        results.append(get_order_status(order_id))

    if order_id and wants_return:
        results.append(create_return_request(order_id, _reason_from_ticket(ticket)))
        results.append(get_refund_policy())
    elif "refund" in text or "payment failed" in text or "money was deducted" in text:
        results.append(get_refund_policy())

    if wants_product:
        results.append(search_products(ticket))

    if wants_order and not order_id:
        results.append(
            {
                "ok": False,
                "tool": "get_order_status",
                "message": "Order ID is required before order status can be checked.",
            },
        )

    return results


def merge_order_context(
    order_context: dict[str, Any],
    tool_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Add found order facts into the context passed to RAG/LLM stages."""
    merged = dict(order_context or {})
    for result in tool_results:
        order = result.get("order")
        if result.get("tool") == "get_order_status" and isinstance(order, dict):
            merged.setdefault("order_id", order.get("order_id"))
            merged.setdefault("order_status", order.get("order_status"))
            merged.setdefault("order_date", order.get("order_date"))
            merged.setdefault("delivery_date", order.get("delivery_date"))
            merged.setdefault("payment_method", order.get("payment_method"))
            merged.setdefault("item_category", order.get("product_name"))
            merged.setdefault("tracking_id", order.get("tracking_id"))
    return merged


def summarize_tool_results(tool_results: list[dict[str, Any]]) -> str:
    """Compact tool output for prompts and UI."""
    if not tool_results:
        return "No tools were called."
    lines: list[str] = []
    for result in tool_results:
        tool = result.get("tool", "tool")
        message = result.get("message", "")
        lines.append(f"- {tool}: {message}")
        if result.get("tool") == "get_order_status" and isinstance(result.get("order"), dict):
            order = result["order"]
            lines.append(
                "  "
                + f"order_id={order.get('order_id')}, status={order.get('order_status')}, "
                + f"tracking_id={order.get('tracking_id')}, delivery_date={order.get('delivery_date')}"
            )
        if result.get("tool") == "search_products":
            names = [p.get("name") for p in result.get("matches", [])]
            if names:
                lines.append("  matches=" + ", ".join(str(name) for name in names))
    return "\n".join(lines)


def _order_status_message(order: dict[str, Any]) -> str:
    status = str(order.get("order_status", "Unknown"))
    tracking = order.get("tracking_id")
    eta = order.get("estimated_delivery")
    if tracking and eta:
        return f"Order is {status}. Tracking ID {tracking}; estimated delivery {eta}."
    if tracking:
        return f"Order is {status}. Tracking ID {tracking}."
    return f"Order is {status}."


def _is_inside_return_window(order: dict[str, Any]) -> tuple[bool, str]:
    delivery = order.get("delivery_date")
    if not delivery:
        return False, "Delivery date is unavailable, so eligibility must be reviewed by a human agent."
    try:
        delivered_on = datetime.strptime(str(delivery), "%Y-%m-%d").date()
    except ValueError:
        return False, "Delivery date format is invalid, so eligibility must be reviewed by a human agent."
    days = (DEMO_TODAY - delivered_on).days
    window = int(order.get("return_window_days") or 7)
    if days <= window:
        return True, "Order is inside the return window."
    return False, f"Order appears outside the {window}-day return window."


def _reason_from_ticket(ticket: str) -> str:
    text = (ticket or "").lower()
    if "damaged" in text or "broken" in text or "cracked" in text:
        return "damaged_item"
    if "wrong" in text:
        return "wrong_item"
    if "refund" in text:
        return "refund_requested"
    if "replace" in text or "replacement" in text:
        return "replacement_requested"
    return "customer_request"


def _query_tokens(query: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", query.lower())
    stop = {"does", "have", "with", "the", "and", "for", "your", "product", "support", "team"}
    return [token for token in tokens if len(token) > 2 and token not in stop]

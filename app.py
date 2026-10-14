from __future__ import annotations

import gzip
import json
import math
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "data" / "processed" / "app_data.json.gz"

if not DATA_PATH.exists():
    raise RuntimeError("Processed data missing. Run: python preprocess.py")

with gzip.open(DATA_PATH, "rt", encoding="utf-8") as handle:
    DATA = json.load(handle)

app = FastAPI(title="H&M Recommendation Decision Lab", version="1.0")


@app.get("/")
def index():
    return FileResponse(ROOT / "index.html")


@app.get("/api/overview")
def overview():
    return {k: DATA[k] for k in ("overview", "monthly", "groups", "channels", "metrics")}


@app.get("/api/customers")
def customers(limit: int = Query(30, ge=1, le=100)):
    return DATA["customer_ids"][:limit]


def product(article_id: str):
    return DATA["products"].get(article_id, {
        "article_id": article_id, "name": "Product", "type": "Unknown",
        "group": "Unknown", "colour": "Unknown", "department": "Unknown", "description": ""
    })


@app.get("/api/customer/{customer_id}")
def customer(customer_id: str):
    profile = DATA["customers"].get(customer_id)
    if not profile:
        raise HTTPException(404, "Customer ID is not present in the sample")
    result = dict(profile)
    result["customer_id"] = customer_id
    result["recent_purchases"] = [product(x) for x in profile["recent_purchases"]]
    return result


@app.get("/api/recommend/{customer_id}")
def recommend(customer_id: str):
    profile = DATA["customers"].get(customer_id)
    if not profile:
        raise HTTPException(404, "Customer ID is not present in the sample")
    seen = set(profile["purchased"])
    candidates, reasons = [], {}
    for rank, group in enumerate(profile["favorite_groups"]):
        for item in DATA["by_group"].get(group, []):
            if item not in seen and item not in reasons:
                candidates.append(item)
                reasons[item] = f"Matches the customer's preferred group: {group}"
    for item in DATA["popular"]:
        if item not in seen and item not in reasons:
            candidates.append(item)
            reasons[item] = "Popular among customers in the recent period"
    recs = []
    for rank, item in enumerate(candidates[:12], 1):
        row = dict(product(item))
        row["reason"] = reasons[item]
        row["score"] = round(max(0.08, 0.43 - rank * 0.022), 3)
        recs.append(row)
    return {"customer_id": customer_id, "method": "Preference + recent popularity hybrid", "recommendations": recs}


@app.get("/api/economics")
def economics(
    probability: float = Query(0.20, ge=0, le=1),
    delivery_cost: float = Query(20, ge=0),
    item_price: float = Query(12000, gt=0),
    margin_rate: float = Query(0.45, gt=0, le=1),
    incremental_effect: float = Query(0.20, gt=0, le=1),
    audience: int = Query(10000, ge=1),
    capacity: int = Query(7000, ge=1),
):
    margin = item_price * margin_rate
    break_even = delivery_cost / (incremental_effect * margin)
    eligible = audience if probability >= break_even else 0
    recommended = min(eligible, capacity)
    expected_conversions = recommended * probability * incremental_effect
    gross_margin = expected_conversions * margin
    contact_cost = recommended * delivery_cost
    net = gross_margin - contact_cost
    return {
        "margin_per_conversion": round(margin, 2),
        "break_even_probability": round(break_even, 4),
        "recommended_audience": recommended,
        "expected_incremental_conversions": round(expected_conversions, 2),
        "contact_cost": round(contact_cost, 2),
        "expected_gross_margin": round(gross_margin, 2),
        "expected_net": round(net, 2),
        "binding_constraint": "Capacity" if eligible > capacity else ("Threshold" if eligible == 0 else "Eligible audience"),
        "decision": "RUN PILOT" if net > 0 else "DO NOT LAUNCH",
        "kill_criterion": "Stop if incremental net profit is zero or negative after the four-week holdout test.",
        "labels": {"probability": "ESTIMATED", "delivery_cost": "ASSUMED", "item_price": "ASSUMED", "margin_rate": "ASSUMED", "incremental_effect": "ASSUMED"},
    }


@app.get("/health")
def health():
    return {"status": "ok", "customers": len(DATA["customer_ids"])}

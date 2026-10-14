from __future__ import annotations

import gzip
import json
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed" / "app_data.json.gz"


def locate(name: str) -> Path:
    for path in (RAW / name, RAW / f"{name}.zip"):
        if path.exists():
            return path
    raise FileNotFoundError(f"Missing {name} or {name}.zip in {RAW}")


def read_csv(name: str, **kwargs) -> pd.DataFrame:
    return pd.read_csv(locate(name), **kwargs)


def apk(actual: set[str], predicted: list[str], k: int = 12) -> float:
    if not actual:
        return 0.0
    score = hits = 0.0
    used: set[str] = set()
    for rank, item in enumerate(predicted[:k], 1):
        if item in actual and item not in used:
            hits += 1
            score += hits / rank
            used.add(item)
    return score / min(len(actual), k)


def evaluate(train: pd.DataFrame, valid: pd.DataFrame, article_group: dict[str, str]):
    popular = train["article_id"].value_counts().head(100).index.tolist()
    group_pop = {
        group: frame["article_id"].value_counts().head(100).index.tolist()
        for group, frame in train.assign(group=train["article_id"].map(article_group)).groupby("group")
    }
    histories = train.groupby("customer_id")["article_id"].agg(list)
    actuals = valid.groupby("customer_id")["article_id"].agg(set)
    base_scores, personal_scores, personal_prec, personal_rec = [], [], [], []
    covered = set()
    for customer, actual in actuals.items():
        history = histories.get(customer, [])
        groups = Counter(article_group.get(item, "Unknown") for item in history)
        candidates = []
        for group, _ in groups.most_common(3):
            candidates.extend(group_pop.get(group, []))
        candidates.extend(popular)
        seen, recs = set(history), []
        for item in candidates:
            if item not in seen and item not in recs:
                recs.append(item)
            if len(recs) == 12:
                break
        base = popular[:12]
        base_scores.append(apk(actual, base))
        personal_scores.append(apk(actual, recs))
        hits = len(actual.intersection(recs))
        personal_prec.append(hits / 12)
        personal_rec.append(hits / len(actual))
        covered.update(recs)
    mean = lambda x: round(sum(x) / len(x), 5) if x else 0
    return {
        "validation_customers": len(actuals),
        "baseline_map12": mean(base_scores),
        "personalized_map12": mean(personal_scores),
        "precision12": mean(personal_prec),
        "recall12": mean(personal_rec),
        "coverage": round(len(covered) / max(1, train["article_id"].nunique()), 5),
    }


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tx = read_csv(
        "transactions_sample.csv",
        dtype={"customer_id": "string", "article_id": "string", "sales_channel_id": "int8"},
        parse_dates=["t_dat"],
    )
    articles = read_csv("articles.csv", dtype={"article_id": "string"})
    customers = read_csv("customers.csv", dtype={"customer_id": "string"})
    tx["article_id"] = tx["article_id"].str.zfill(10)
    articles["article_id"] = articles["article_id"].str.zfill(10)

    customer_ids = set(tx["customer_id"].unique())
    customers = customers[customers["customer_id"].isin(customer_ids)].copy()
    used_articles = set(tx["article_id"].unique())
    articles_used = articles[articles["article_id"].isin(used_articles)].copy()
    article_group = articles.set_index("article_id")["product_group_name"].fillna("Unknown").to_dict()
    article_lookup = articles.set_index("article_id").fillna("")

    latest = tx["t_dat"].max()
    validation_start = latest - pd.Timedelta(days=6)
    train = tx[tx["t_dat"] < validation_start]
    valid = tx[tx["t_dat"] >= validation_start]
    metrics = evaluate(train, valid, article_group)

    recent_start = latest - pd.Timedelta(days=29)
    recent = tx[tx["t_dat"] >= recent_start]
    popularity_source = recent if len(recent) >= 100 else tx
    popular_ids = popularity_source["article_id"].value_counts().head(250).index.tolist()
    by_group = defaultdict(list)
    merged = popularity_source[["article_id"]].copy()
    merged["group"] = merged["article_id"].map(article_group).fillna("Unknown")
    for group, frame in merged.groupby("group"):
        by_group[group] = frame["article_id"].value_counts().head(100).index.tolist()

    cust_lookup = customers.set_index("customer_id").fillna("").to_dict("index")
    profiles = {}
    for customer, frame in tx.sort_values("t_dat").groupby("customer_id", sort=False):
        items = frame["article_id"].tolist()
        groups = [article_group.get(x, "Unknown") for x in items]
        meta = cust_lookup.get(customer, {})
        profiles[customer] = {
            "age": None if meta.get("age", "") == "" else int(float(meta["age"])),
            "club_status": meta.get("club_member_status") or "Unknown",
            "fashion_news": meta.get("fashion_news_frequency") or "Unknown",
            "transactions": len(frame),
            "total_spend": round(float(frame["price"].sum()), 4),
            "average_price": round(float(frame["price"].mean()), 4),
            "last_purchase": frame["t_dat"].max().strftime("%Y-%m-%d"),
            "favorite_groups": [x for x, _ in Counter(groups).most_common(3)],
            "purchased": list(dict.fromkeys(reversed(items)))[:100],
            "recent_purchases": list(dict.fromkeys(reversed(items)))[:8],
        }

    relevant_ids = set(popular_ids)
    for values in by_group.values():
        relevant_ids.update(values)
    for p in profiles.values():
        relevant_ids.update(p["recent_purchases"])

    products = {}
    for article_id in relevant_ids:
        if article_id not in article_lookup.index:
            continue
        row = article_lookup.loc[article_id]
        products[article_id] = {
            "article_id": article_id,
            "name": str(row.get("prod_name", "Unknown product")),
            "type": str(row.get("product_type_name", "Unknown")),
            "group": str(row.get("product_group_name", "Unknown")),
            "colour": str(row.get("colour_group_name", "Unknown")),
            "department": str(row.get("department_name", "Unknown")),
            "description": str(row.get("detail_desc", "")),
        }

    monthly = tx.assign(month=tx["t_dat"].dt.to_period("M").astype(str)).groupby("month").agg(
        transactions=("article_id", "size"), revenue=("price", "sum")
    ).reset_index()
    group_counts = tx.assign(group=tx["article_id"].map(article_group).fillna("Unknown"))["group"].value_counts().head(10)

    payload = {
        "overview": {
            "customers": int(tx["customer_id"].nunique()),
            "products": int(tx["article_id"].nunique()),
            "transactions": int(len(tx)),
            "date_min": tx["t_dat"].min().strftime("%Y-%m-%d"),
            "date_max": latest.strftime("%Y-%m-%d"),
            "average_price": round(float(tx["price"].mean()), 4),
            "online_share": round(float((tx["sales_channel_id"] == 2).mean()), 4),
            "sample_notice": "Results use a reproducible sample of 10,000 customers, not H&M's full operational population.",
        },
        "monthly": monthly.round({"revenue": 4}).to_dict("records"),
        "groups": [{"name": k, "value": int(v)} for k, v in group_counts.items()],
        "channels": {
            str(k): int(v) for k, v in tx["sales_channel_id"].value_counts().sort_index().items()
        },
        "metrics": metrics,
        "customers": profiles,
        "customer_ids": list(profiles.keys()),
        "products": products,
        "popular": popular_ids,
        "by_group": dict(by_group),
    }
    with gzip.open(OUT, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
    print(f"Created {OUT} ({OUT.stat().st_size / 1_000_000:.1f} MB)")


if __name__ == "__main__":
    main()

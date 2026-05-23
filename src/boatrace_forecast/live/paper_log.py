"""ペーパートレードのロギング・結果突合・PnLレポート."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from boatrace_forecast.utils.logging import get_logger

logger = get_logger(__name__)


def load_predictions(log_dir: Path) -> pd.DataFrame:
    """data/predictions/*.json をすべて読み込み 1行=1予想 の DataFrame に."""
    rows = []
    for p in sorted(log_dir.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("skip %s: %s", p.name, exc)
            continue
        top_combos = d.get("top_combos") or []
        top_combo_list = [c["combo"] for c in top_combos if "combo" in c]
        rows.append({
            "race_date": pd.to_datetime(d["race_date"]),
            "stadium_id": d["stadium_id"],
            "race_no": d["race_no"],
            "deadline": d.get("deadline"),
            "fetched_at": d.get("fetched_at"),
            "top1_combo": d["top1_combo"],
            "top1_prob": d.get("top1_prob"),
            "top1_odds": d.get("top1_odds"),
            "expected_value": d.get("expected_value"),
            "top_combos": top_combo_list,  # ['1-5-6', '1-6-5', ...]
            "buy_recommended": bool(d.get("buy_recommended", False)),
            "buy_reason": d.get("buy_reason", ""),
            "log_file": p.name,
        })
    return pd.DataFrame(rows)


def reconcile_predictions(
    predictions: pd.DataFrame,
    payouts: pd.DataFrame,
    *,
    stake_yen: int = 100,
) -> pd.DataFrame:
    """予想と実払戻を突合し、ヒットPnLを付加した DataFrame を返す."""
    if predictions.empty:
        return predictions
    p = predictions.copy()
    pay = payouts[["race_date", "stadium_id", "race_no", "trifecta", "trifecta_yen"]]
    merged = p.merge(pay, on=["race_date", "stadium_id", "race_no"], how="left")
    merged["hit"] = (merged["top1_combo"] == merged["trifecta"]).astype(int)
    merged["stake_yen"] = stake_yen
    merged["payout_yen"] = (
        merged["hit"] * merged["trifecta_yen"].fillna(0).astype(float) * (stake_yen / 100)
    ).astype(int)
    merged["pnl"] = merged["payout_yen"] - merged["stake_yen"]
    merged["resolved"] = merged["trifecta"].notna()
    return merged


def report_summary(reconciled: pd.DataFrame) -> dict:
    if reconciled.empty:
        return {"n": 0, "resolved": 0, "roi": None, "hit_rate": None}
    resolved = reconciled[reconciled["resolved"]]
    if resolved.empty:
        return {
            "n": len(reconciled),
            "resolved": 0,
            "roi": None,
            "hit_rate": None,
            "note": "結果未着のレースのみ",
        }
    total_stake = int(resolved["stake_yen"].sum())
    total_payout = int(resolved["payout_yen"].sum())
    return {
        "n": len(reconciled),
        "resolved": len(resolved),
        "n_hits": int(resolved["hit"].sum()),
        "stake": total_stake,
        "payout": total_payout,
        "roi": total_payout / total_stake if total_stake else 0.0,
        "hit_rate": float(resolved["hit"].mean()),
        "first_date": str(resolved["race_date"].min().date()),
        "last_date": str(resolved["race_date"].max().date()),
    }


def daily_breakdown(reconciled: pd.DataFrame) -> pd.DataFrame:
    if reconciled.empty:
        return pd.DataFrame()
    df = reconciled[reconciled["resolved"]].copy()
    df["date"] = df["race_date"].dt.date
    g = df.groupby("date").agg(
        n_bets=("hit", "size"),
        n_hits=("hit", "sum"),
        stake=("stake_yen", "sum"),
        payout=("payout_yen", "sum"),
    )
    g["roi"] = g["payout"] / g["stake"]
    g["hit_rate"] = g["n_hits"] / g["n_bets"]
    return g.reset_index()

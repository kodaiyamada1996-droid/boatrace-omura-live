"""公開ライブ実績ダッシュボード（Streamlit）.

起動:
    uv run --extra live streamlit run scripts/dashboard.py
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from boatrace_forecast.live.paper_log import (
    daily_breakdown,
    load_predictions,
    reconcile_predictions,
    report_summary,
)
from boatrace_forecast.utils.config import load_config, project_path

# ライブ運用開始日。これより前のレコードは検証用テストとみなして除外
LIVE_START_DATE = pd.Timestamp("2026-05-10")
STAKE_YEN = 100

st.set_page_config(
    page_title="大村3連単AI ライブ実績",
    page_icon="🚤",
    layout="wide",
)

st.title("大村3連単AI ライブ実績ダッシュボード")
st.caption("機械学習エンジニアが作る、データ完全公開の競艇予想AI（大村特化）")

with st.expander("⚠ 重要：投資結果の保証はありません（必ずお読みください）", expanded=False):
    st.markdown(
        """
- 本ダッシュボードは過去のライブ予想とその結果を**事実として透明に公開**するものです。
- 表示しているROI・的中率は**過去実績**であり、将来の結果を保証するものではありません。
- 競艇は公営競技です。**ご自身の判断と責任**のもとでお楽しみください。
- ベット単位は検証用に **1レース100円フラット**（買い目はトップ1の3連単コンボ）。
- モデルは LightGBM ベースの多クラス分類。学習データは大村場のみ。
"""
    )


@st.cache_data(ttl=300)
def load_data() -> tuple[pd.DataFrame, pd.DataFrame, int]:
    cfg = load_config()
    sid = int(cfg.section("target")["stadium_id"])
    interim = project_path(cfg.section("data")["interim_dir"])
    log_dir = project_path("data") / "predictions"
    preds = load_predictions(log_dir)
    payouts_path = interim / f"payouts_stadium{sid:02d}.parquet"
    payouts = pd.read_parquet(payouts_path) if payouts_path.exists() else pd.DataFrame()
    return preds, payouts, sid


try:
    preds, payouts, stadium_id = load_data()
except FileNotFoundError as exc:
    st.error(f"データの読み込みに失敗しました: {exc}")
    st.stop()

if preds.empty:
    st.warning("予想ログがまだありません。daemon の起動を確認してください。")
    st.stop()

# テストレコード除外: R99 (テスト用), LIVE_START_DATE 以前のレコード
preds = preds[(preds["race_no"] != 99) & (preds["race_date"] >= LIVE_START_DATE)].copy()
# 同一レースで複数回 fetch されている場合は最新のものを残す
preds = preds.sort_values("fetched_at").drop_duplicates(
    subset=["race_date", "stadium_id", "race_no"], keep="last"
)

if preds.empty:
    st.warning(f"{LIVE_START_DATE.date()} 以降のライブ予想がまだありません。")
    st.stop()

reconciled = reconcile_predictions(preds, payouts, stake_yen=STAKE_YEN)
summary = report_summary(reconciled)
resolved = reconciled[reconciled["resolved"]].sort_values(["race_date", "race_no"]).copy()

st.markdown("### 累計ライブ実績")
c1, c2, c3, c4 = st.columns(4)
c1.metric(
    "検証期間",
    f"{summary.get('first_date', '-')}  〜  {summary.get('last_date', '-')}",
)
c2.metric("予想レース数（結果確定）", f"{summary.get('resolved', 0):,}")
c3.metric("的中数", f"{summary.get('n_hits', 0):,}")
roi = summary.get("roi") or 0.0
c4.metric(
    "累計ROI",
    f"{roi * 100:.1f}%",
    delta=f"{(roi - 1.0) * 100:+.1f}pt vs 損益分岐",
)

n_pending = int(len(reconciled) - len(resolved))
if n_pending > 0:
    st.info(f"結果待ち: {n_pending} レース（K-fileの公開後に自動で反映されます）")

st.divider()

if not resolved.empty:
    st.markdown("### 累積収支推移")
    resolved_sorted = resolved.sort_values(["race_date", "race_no"]).reset_index(drop=True)
    resolved_sorted["cum_pnl"] = resolved_sorted["pnl"].cumsum()
    resolved_sorted["race_idx"] = range(1, len(resolved_sorted) + 1)

    fig_pnl = go.Figure()
    fig_pnl.add_trace(
        go.Scatter(
            x=resolved_sorted["race_idx"],
            y=resolved_sorted["cum_pnl"],
            mode="lines+markers",
            name="累積収支",
            line={"width": 2, "color": "#2563eb"},
            marker={"size": 4},
            hovertemplate=(
                "%{customdata[0]} R%{customdata[1]}<br>累積収支: ¥%{y:,}<extra></extra>"
            ),
            customdata=resolved_sorted[["race_date", "race_no"]].assign(
                race_date=resolved_sorted["race_date"].dt.strftime("%Y-%m-%d")
            ).values,
        )
    )
    fig_pnl.add_hline(y=0, line_dash="dash", line_color="gray")
    fig_pnl.update_layout(
        xaxis_title="レース通番",
        yaxis_title="累積収支（円）",
        height=380,
        margin={"t": 30, "b": 30},
    )
    st.plotly_chart(fig_pnl, use_container_width=True)

    daily = daily_breakdown(reconciled)
    if not daily.empty:
        st.markdown("### 日次ROI")
        colors = ["#16a34a" if r >= 1.0 else "#dc2626" for r in daily["roi"]]
        fig_daily = go.Figure()
        fig_daily.add_trace(
            go.Bar(
                x=daily["date"].astype(str),
                y=(daily["roi"] * 100).round(1),
                marker_color=colors,
                text=(daily["roi"] * 100).round(1).astype(str) + "%",
                textposition="outside",
                name="日次ROI",
            )
        )
        fig_daily.add_hline(
            y=100,
            line_dash="dash",
            line_color="gray",
            annotation_text="損益分岐 (100%)",
            annotation_position="right",
        )
        fig_daily.update_layout(
            xaxis_title="日付",
            yaxis_title="ROI (%)",
            xaxis={"type": "category"},
            height=350,
            margin={"t": 30, "b": 30},
        )
        st.plotly_chart(fig_daily, use_container_width=True)

st.markdown("### 最近の予想と結果（直近50件）")

display = reconciled.copy().sort_values(
    ["race_date", "race_no"], ascending=[False, False]
)


def _format_hit(row: pd.Series) -> str:
    if not row["resolved"]:
        return "－"
    return "🎯 的中" if row["hit"] == 1 else "✕"


def _format_pnl(v: float) -> str:
    if pd.isna(v):
        return "-"
    v_int = int(v)
    return f"+¥{v_int:,}" if v_int > 0 else f"¥{v_int:,}"


display_view = pd.DataFrame(
    {
        "日付": display["race_date"].dt.strftime("%Y-%m-%d"),
        "R": display["race_no"],
        "予想（3連単）": display["top1_combo"],
        "確率": (display["top1_prob"] * 100).round(1).astype(str) + "%",
        "予想時オッズ": display["top1_odds"].apply(
            lambda v: f"{v:.1f}" if pd.notna(v) else "-"
        ),
        "実結果": display["trifecta"].fillna("結果待ち"),
        "的中": display.apply(_format_hit, axis=1),
        "収支": display["pnl"].apply(_format_pnl),
    }
)
st.dataframe(display_view.head(50), use_container_width=True, hide_index=True)

st.divider()

with st.expander("このAIについて", expanded=False):
    st.markdown(
        """
**モデル**: LightGBM 多クラス分類（500本、num_leaves=63）
**学習データ**: 大村ボートレース場の過去レース（2020-01-01以降、約7万レース）
**特徴量**: 選手成績（級別・全国/当地勝率・モーター/ボート2連率）、進入、天候、水面など33種
**買い方**: 各レース「予想トップ1の3連単コンボに100円フラット」
**配信**: 締切5分前に予想を生成、結果はレース後にK-fileから自動取得して突合

**バックテスト実績（参考）**: 2022-01〜2024-12のwalk-forward検証で ROI 107.4%、的中率 10.5%
（過去実績であり将来の結果を保証するものではありません）
"""
    )

st.caption(
    "© 大村3連単AI ライブ実績 ／ 本サイトは予想の透明な記録公開を目的としており、"
    "投資勧誘または賭博の斡旋を行うものではありません。"
)

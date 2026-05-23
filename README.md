# 大村3連単AI ライブ実績ダッシュボード

機械学習エンジニアが作る、データ完全公開の競艇予想AI（大村特化）の **ライブ実績を透明に公開**するStreamlitアプリ。

## 公開URL

<!-- デプロイ後に追記 -->
https://boatrace-omura-live.streamlit.app/

## このリポジトリの目的

予想AIが事前公開した3連単予想と、実際のレース結果（払い戻し）を突合した日次・累計ROIを誰でも検証可能な形で公開すること。改竄不可性のためデータは git にコミットしている。

- **予想ログ**: `data/predictions/*.json` — 各レースの締切前に生成・コミット
- **払い戻し**: `data/interim/payouts_stadium24.parquet` — レース後の公式K-fileから集計
- **集計コード**: `src/boatrace_forecast/live/paper_log.py` — 予想と結果の突合・ROI計算
- **ダッシュボード**: `streamlit_app.py` — Streamlit表示

## ローカル起動

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## 重要な注意

- 表示されるROI・的中率は **過去実績** であり、将来の結果を保証しません。
- ベット単位は検証用に1レース100円フラット。
- 競艇は公営競技です。ご自身の判断と責任のもとでお楽しみください。

## 関連

- モデルの設計詳細・特徴量・バックテスト方法は別途noteで公開予定
- 学習スクリプト・モデルバイナリは本リポジトリには含まれません

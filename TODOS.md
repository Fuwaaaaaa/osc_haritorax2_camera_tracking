# TODOS

## P1 - Critical

### ~~Phase 0後: 布団モードの価値提案を再評価~~ ✅ 完了
- **解決:** 布団モードの真の価値は「布団から出た瞬間のドリフト即座補正」と再定義。README更新済み。

### ~~MediaPipe API移行確認~~ ✅ 完了
- **解決:** コードは既にMediaPipe Pose Landmarker Tasks APIを使用。CLAUDE.mdにも記載済み。

## P2 - Important

### ~~OBSオーバーレイ~~ ✅ 完了
- **解決:** OBS Browser Source対応オーバーレイサーバー実装。--obsフラグで有効化。7テスト。

### ~~両カメラ同時ロスト時の遷移ロジック~~ ✅ 完了
- **解決:** 両カメラconfidence < 0.05でヒステリシスをバイパスし即座にFULL_OCCLUSIONへ遷移。テスト3件追加。

### ~~セットアップウィザード（in-app）~~ ✅ 完了
- **解決:** 7ステップガイド付きセットアップ実装。カメラ検出・モデルDL自動化。8テスト。

### ~~統一品質閾値テーブル~~ ✅ 完了
- **解決:** ComplementaryFilter/WebDashboardがconfigから閾値を受け取るように変更。ハードコード0.7/0.3を排除。

### ~~残りモジュール統合（vmc_sender, hotkeys等）~~ ✅ 完了
- **解決:** 全17モジュールをmain.pyに統合済み。CLIフラグ（--vmc, --viewer, --discord, --api, --remap, --bvh, --smoothing等）で有効化。

## P3 - Nice to Have

### ~~汎用IMU+カメラフュージョンミドルウェアへのリブランド~~ ✅ 完了
- **解決:** README/osc_receiver.pyをトラッカー非依存に書き換え。HaritoraX2は「最初の対応デバイス」として位置付け。

### 直接BLE/Serial HaritoraX2接続
- **What:** SlimeTora+SlimeVR依存を排除し、bleakライブラリで直接BLE接続
- **Why:** SlimeToraは単一メンテナープロジェクト。破綻リスクがある。docs/haritora-protocol.mdに既にプロトコル仕様あり
- **Effort:** L（CC: 2時間）
- **Priority:** P2
- **Depends on:** v0.1リリース後
- **Context:** CEO Subagent #2指摘。「最も弱いリンク」

### 複数IMUトラッカー対応（SlimeVR, Tundra等）
- **What:** HaritoraX2以外のIMUトラッカーからのOSCデータ受信対応
- **Why:** リブランド後の自然な拡張。ユーザーベース拡大
- **Context:** CEO Subagent #1, #2とも推奨
- **Effort:** M（CC: 1時間）
- **Priority:** P3
- **Depends on:** リブランド完了後

### N台カメラ対応
- **What:** 2台以上のカメラをサポート
- **Why:** 12ヶ月理想状態の一部。カバレッジ向上
- **Effort:** M（CC: 1時間）
- **Priority:** P3
- **Depends on:** Phase 3完了

### 深層学習ベースポーズ予測
- **What:** 部分遮蔽時に過去の動きから次フレームを予測
- **Why:** 12ヶ月理想状態の一部。遮蔽時の品質向上
- **Effort:** L（CC: 3時間）
- **Priority:** P3
- **Depends on:** Phase 4完了

### main.pyリファクタ（SubsystemManager）
- **What:** main.pyのサブシステム初期化・更新・シャットダウンをSubsystemManagerクラスに抽出
- **Why:** 現在245LOC。モジュール追加のたびに肥大化する構造。start/update/stopのライフサイクルが統一されていない
- **Effort:** S（CC: 30分）
- **Priority:** P3
- **Context:** Eng Reviewで指摘。現状は動作に問題なし

### ステレオカメラ深度精度検証
- **What:** 2台Webカメラ（0.5-1m間隔）で2-3m先の被写体の三角測量精度を実測
- **Why:** CEO Subagentが指摘。消費者向けWebカメラの深度分解能は未検証
- **Effort:** S（CC: 15分）
- **Priority:** P3
- **Context:** 静的精度テスト。既知距離の物体で計測

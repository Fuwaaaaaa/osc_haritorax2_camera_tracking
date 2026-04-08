# TODOS

## P1 - Critical

### Phase 0後: 布団モードの価値提案を再評価
- **What:** HaritoraX2が回転データのみ（位置なし）の場合、布団モードの差別化価値を再評価
- **Why:** 回転のみの場合、布団モードは「位置凍結+関節回転」になり、HaritoraX2単体と同等。カメラによる位置推定が唯一の位置ソースになるため、カメラが見えない布団モードでの位置追跡が不可能
- **Pros:** 早期に方向転換できれば、無駄な実装を防げる
- **Cons:** Phase 0の結果次第で設計の大幅変更が必要になる可能性
- **Context:** Outside Voice（独立レビュー）で指摘。現在の設計はフォールバックを記載済みだが、フォールバックがデフォルトケースになる可能性が高い
- **Effort:** S（CC: 15分）
- **Priority:** P1
- **Depends on:** Phase 0完了

### MediaPipe API移行確認
- **What:** MediaPipe BlazePose (Legacy Solutions API) → MediaPipe Pose Landmarker (Tasks API) への移行を確認
- **Why:** Legacy Solutions APIは非推奨。Tasks APIへの移行が必要
- **Pros:** 将来のAPI廃止リスクを回避
- **Cons:** APIインターフェースの変更が必要
- **Context:** Outside Voiceで指摘。アーキテクチャ変更は不要だが、コード実装時にTasks APIを使用すること
- **Effort:** S（CC: 15分）
- **Priority:** P1
- **Depends on:** なし

## P2 - Important

### OBSオーバーレイ（WebSocketインターフェース）
- **What:** 配信者向けにトラッキング状態をOBSに表示するWebSocketインターフェース
- **Why:** 配信者がトラッキング品質を視聴者に見せられる。デモにも有用
- **Pros:** 配信コミュニティへのリーチ拡大
- **Cons:** コア機能ではない
- **Context:** CEO Review Expansion #6。コア安定後に追加
- **Effort:** S（CC: 20分）
- **Priority:** P2
- **Depends on:** Phase 4完了

### 両カメラ同時ロスト時の遷移ロジック
- **What:** 2台のカメラが同時にトラッキングロストした場合のステートマシン遷移を明確化
- **Why:** 現在のステートマシンは片カメラ劣化と全遮蔽を別々に扱うが、両カメラ同時ロストの遷移パスが未定義
- **Pros:** ロバスト性向上
- **Cons:** 追加のテストケースが必要
- **Context:** Outside Voiceで指摘。ヒステリシス（急速なモード切替防止）も検討
- **Effort:** S（CC: 15分）
- **Priority:** P2
- **Depends on:** Phase 1（ステートマシン実装時）

## P3 - Nice to Have

### 複数IMUトラッカー対応（SlimeVR, Tundra等）
- **What:** HaritoraX2以外のIMUトラッカーからのOSCデータ受信対応
- **Why:** 12ヶ月理想状態の一部。ユーザーベース拡大
- **Effort:** M（CC: 1時間）
- **Priority:** P3
- **Depends on:** Phase 2完了

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

# TODOS

## P1 - Critical

### ~~Phase 0後: 布団モードの価値提案を再評価~~ ✅ 完了
- **解決:** 布団モードの真の価値は「布団から出た瞬間のドリフト即座補正」と再定義。README更新済み。

### ~~MediaPipe API移行確認~~ ✅ 完了
- **解決:** コードは既にMediaPipe Pose Landmarker Tasks APIを使用。CLAUDE.mdにも記載済み。

### ~~compass_blend_factorバグ修正~~ ✅ 完了
- **解決:** config→FusionEngine→ComplementaryFilter/VisualCompassに正しくスレッディング。ハードコード0.3を排除。

### ~~FUTON_MODE実装~~ ✅ 完了
- **解決:** 6モードステートマシンに追加。ピッチ検出、ドウェルタイム、NaN安全、設定可能なトリガージョイント。

### ~~camera_tracker.pyテストカバレッジ~~ ✅ 完了
- **解決:** 17件のテスト追加。SharedMemory読み書き、失効データ、NaN、ライフサイクル、トーンリード。

## P2 - Important

### ~~OBSオーバーレイ（WebSocketインターフェース）~~ ✅ 完了
- **解決:** OBS Browser Source対応オーバーレイ実装（obs_overlay.py）。`--obs`フラグで有効化。http://localhost:8767 をBrowser Sourceとして追加。テスト7件。

### ~~両カメラ同時ロスト時の遷移ロジック~~ ✅ 完了
- **解決:** 両カメラconfidence < 0.05でヒステリシスをバイパスし即座にFULL_OCCLUSIONへ遷移。テスト3件追加。

### ~~セットアップウィザード（in-app）~~ ✅ 完了
- **解決:** 7ステップCLIウィザード実装（setup_wizard.py）。モデルDL→カメラ確認→SlimeVR接続→ポート確認→キャリブ→テスト→設定保存。テスト10件。

### ~~カメラ別・部位別confidence分離~~ ✅ 完了
- **解決:** カメラサブプロセスがSharedMemoryにカメラ別の信頼度を書き込み、fusion_engine.pyがカメラ別に信頼度を計算してstate_machineに渡す。SINGLE_CAM_DEGRADEDモードが正しくトリガーされるように。

### ~~統一品質閾値テーブル~~ ✅ 完了
- **解決:** ComplementaryFilter/web_dashboard/preview.pyのハードコード0.7/0.3をconfig値に置換。閾値はconfig.pyで一元管理。

### ~~残りモジュール統合（vmc_sender, hotkeys等）~~ ✅ 完了
- **解決:** 全17モジュールをmain.pyに統合済み。CLIフラグ（--vmc, --viewer, --discord, --api, --remap, --bvh, --smoothing等）で有効化。

## P3 - Nice to Have

### ~~汎用IMU+カメラフュージョンミドルウェアへのリブランド~~ ✅ 完了
- **解決:** docstring / CLI help / 通知 / setup wizard / README / QUICKSTART / DESIGN を汎用 framing に統一。`docs/other-trackers.md` を新規作成し、SlimeVR native / Tundra 等の SlimeVR-Server 互換トラッカーを "動作報告求む" ステータスで列挙。コードは元から device-agnostic (OSC 入力)。

### 直接BLE/Serial HaritoraX2接続
- **What:** SlimeTora+SlimeVR依存を排除し、bleakライブラリで直接BLE接続
- **Why:** SlimeToraは単一メンテナープロジェクト。破綻リスクがある。docs/haritora-protocol.mdに既にプロトコル仕様あり
- **Effort:** L（CC: 2時間）
- **Priority:** P2
- **Depends on:** v0.1リリース後
- **Context:** CEO Subagent #2指摘。「最も弱いリンク」

### GitHub Issueテンプレート（デバイス互換性レポート）
- **What:** `.github/ISSUE_TEMPLATE/device-compat.yml` を作成し、docs/other-trackers.md が誘導する「動作報告」フォーマットを構造化
- **Why:** other-trackers.md は Issues への自由記述に誘導しているため、デバイス名 / ファームウェア / トラッカー数 / ログ等の必須情報が揃わないリスク。plan (synchronous-hugging-gray.md) の Assignment で自問指示済み
- **Effort:** XS（CC: 5分）
- **Priority:** P3
- **Context:** GitHub の issue form (YAML) を使えば必須フィールド指定可能。other-trackers.md の "動作報告の書き方" セクションをそのまま form 化

### SlimeVR 実機動作検証 + docs/slimevr-setup-guide.md
- **What:** SlimeVR native トラッカーを実機テスト → docs/slimevr-setup-guide.md を作成 → other-trackers.md で SlimeVR を 🟡 未検証 → ✅ 動作確認 に昇格
- **Why:** other-trackers.md は現状「原理的に動くはず」と書いてあるが実証されていない。実機確認できれば community の信頼性が跳ね上がる。リブランドの delivery 完成形
- **Effort:** M（CC: 1時間、ただしハード所持が前提）
- **Priority:** P3
- **Depends on:** SlimeVR native トラッカーの入手
- **Context:** `osc_receiver.py:DEFAULT_BONE_ADDRESSES` は SlimeVR Server OSC output を直接受信するため、コード変更は理論上不要。セットアップガイドと動作証跡のみが必要

### 複数IMUトラッカー対応（SlimeVR, Tundra等）
- **What:** HaritoraX2以外のIMUトラッカーからのOSCデータ受信対応
- **Why:** リブランド後の自然な拡張。ユーザーベース拡大
- **Context:** CEO Subagent #1, #2とも推奨
- **Effort:** M（CC: 1時間）
- **Priority:** P3
- **Depends on:** リブランド完了後、SlimeVR 実機動作検証

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

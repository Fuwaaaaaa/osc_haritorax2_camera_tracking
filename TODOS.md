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

### ~~直接 BLE HaritoraX2 接続~~ ✅ 完了 (experimental)
- **解決:** `src/osc_tracking/ble_receiver.py` 実装済み。`--receiver ble` フラグで有効化。bleak 経由で HaritoraX2-* BLE peripheral をスキャン・接続・Sensor characteristic の notification を購読。`docs/ble-direct-guide.md` にセットアップ手順あり。実機動作検証は別 TODO (下記「BLE 実機動作検証」)。Serial (COM/SPP) 経路は別 TODO (下記「Serial (COM/SPP) 経路」)。

### BLE 実機動作検証
- **What:** HaritoraX2 実機で `--receiver ble` の動作確認、デコード精度・遅延・切断復旧の検証
- **Why:** BLE 経路は haritorax-interpreter 公開実装を参考にしたが未検証。実機確認で `docs/ble-direct-guide.md` を ✅ に昇格し community 信頼性向上
- **Effort:** M（CC: 1時間）
- **Priority:** P3
- **Depends on:** HaritoraX2 実機の入手
- **Context:** 検証内容: (1) 全 8 トラッカーの BLE local name を `ble_scan` で列挙、(2) `ble_local_name_to_bone` にマッピング、(3) `--receiver ble` 起動、(4) VRChat 等で実際に姿勢追従、(5) 30 分程度の長時間安定性（切断リトライ確認）

### ~~Serial (COM/SPP) 経路~~ ✅ 完了 (experimental)
- **解決:** `src/osc_tracking/serial_receiver.py` 実装済み。`--receiver serial --port COM3` で有効化。pyserial 経由で GX6/GX2 dongle / Bluetooth Classic SPP からフレーム (sync `0xAA 0x55` + tracker_id + int16×4 quaternion) を読み取り、`ble_receiver.decode_rotation` を共有して回転を復元。`docs/serial-direct-guide.md` にセットアップ手順あり。実機動作検証は別 TODO (下記「Serial 実機動作検証」)。

### Serial 実機動作検証
- **What:** GX6/GX2 dongle 実機で `--receiver serial` の動作確認、フレーム形式・遅延・切断復旧の検証
- **Why:** Serial 経路は haritorax-interpreter 公開実装を参考にしたが未検証。実機確認で `docs/serial-direct-guide.md` を ✅ に昇格
- **Effort:** M（CC: 1時間）
- **Priority:** P3
- **Depends on:** GX6/GX2 dongle の入手
- **Context:** 検証内容: (1) COM ポート認識、(2) `--receiver serial --port COMx` 起動、(3) `serial_tracker_id_to_bone` のマッピング、(4) 実際に姿勢追従、(5) 30 分程度の長時間安定性。フレーム形式が合わない場合は `src/osc_tracking/serial_receiver.py` の `parse_frames` / `SYNC_BYTES` を haritorax-interpreter `src/mode/com.ts` 実測値に合わせて調整

### ~~GitHub Issueテンプレート（デバイス互換性レポート）~~ ✅ 完了
- **解決:** `.github/ISSUE_TEMPLATE/device-compat.yml` を作成。接続経路 (OSC / BLE / other) の dropdown、デバイス / トラッカー数 / OS / ファームウェア / osc-tracking バージョン / SlimeVR Server バージョン / 結果 (動作 / 部分 / 失敗) / 動いた箇所 / 詰まった箇所 / ログ、を必須・任意項目としてフォーム化。`config.yml` で contact link も追加。docs/other-trackers.md と docs/ble-direct-guide.md の誘導リンクを新 URL (`?template=device-compat.yml`) に更新。

### SlimeVR 実機動作検証
- **What:** SlimeVR native トラッカーを実機テスト → other-trackers.md で SlimeVR を 🟡 未検証 → ✅ 動作確認 に昇格
- **Why:** セットアップガイド ([docs/slimevr-setup-guide.md](docs/slimevr-setup-guide.md)) は公開済みだが、実機検証による動作証跡がまだない。実機確認できれば community の信頼性が跳ね上がる。リブランドの delivery 完成形
- **Effort:** S (ハード所持後 CC: 30分)
- **Priority:** P3
- **Depends on:** SlimeVR native トラッカーの入手
- **Context:** `osc_receiver.py` は SlimeVR Server OSC output を直接受信するため、コード変更は理論上不要。動作証跡 (`connection_check` のログ、VRChat での追従動画など) のみが必要

### ~~複数IMUトラッカー対応（SlimeVR, Tundra等）~~ ✅ 完了（ドキュメント）
- **解決:** [docs/slimevr-setup-guide.md](docs/slimevr-setup-guide.md) を作成。SlimeVR native / Tundra Labs / その他 SlimeVR Server 互換トラッカー向けのセットアップ手順 (OSC 出力有効化、`connection_check` での疎通確認、マッピング不一致時の対処) を整備。[docs/other-trackers.md](docs/other-trackers.md) と README も新ガイドにリンク。コード変更は不要 (OSCReceiver は既に device-agnostic)。実機検証は「SlimeVR 実機動作検証」TODO で別途トラック。

### ~~N台カメラ対応（設定 API のみ）~~ ✅ 完了（scaffold）
- **解決:** `CameraConfig.cam_indices: list[int]` + `effective_cam_indices` / `camera_count` プロパティ、`--cams 0,1` CLI フラグ、`config.cam_indices` 設定項目を追加。1台 (mono) / 2台 (stereo) に対応。3台以上は warn + 先頭2台のみ使用。legacy `cam1_index` / `cam2_index` は back-compat で維持。実際のマルチビュー三角測量 (3+ カメラの bundle adjustment) は別 TODO (下記「真のマルチビュー三角測量」)。

### ~~真のマルチビュー三角測量（3+ カメラ）~~ ✅ 完了（linear DLT + BA refinement）
- **解決:** `stereo_calibration.py` に `MultiViewCalibration` + `triangulate_multiview()` (SVD-based DLT, per-view confidence 重み付け) を追加。`_camera_worker` を N-way (N=任意) に拡張、N-count の VideoCapture と PoseLandmarker を開いて全ビューから三角測量。`_load_multiview_or_stereo` が multi-view .npz を優先し、legacy stereo .npz は `multiview_from_stereo` で自動 promote するので 2 カメラ構成は挙動不変。SHM は wire 互換 (7 floats/joint) を維持 — N>=3 時は per-camera visibility を「前半/後半 min」に畳んで状態機の SINGLE_CAM_DEGRADED 検出を温存。
- **Bundle adjustment 追加:** `refine_multiview()` が scipy LM で DLT 推定を非線形 refinement。`refine_triangulation` config flag (tri-state: `True`/`False`/`None`=auto; auto は 3+ カメラで on、2 カメラで off)。観測ノイズ下で reprojection error を削減。
- **未対応項目:** `calibrate` tool の multi-view 対応 (現状は stereo pair を手動で組み合わせる必要あり)、実機 3+ カメラでの動作検証

### ~~速度ベースポーズ予測~~ ✅ 完了
- **解決:** `src/osc_tracking/pose_predictor.py` に `PosePredictor` Protocol + `VelocityPredictor` 実装。ローリング履歴からジョイント毎に線形速度を推定し、`FULL_OCCLUSION` / `PARTIAL_OCCLUSION` 時に `FusionEngine` が camera_pos 欠損箇所に予測値を注入。`stale_window_seconds` で長時間遮蔽後のワープを防止、`max_predict_seconds` で absurd extrapolation をクランプ。14 tests + fusion integration 3 tests.

### 深層学習ベースポーズ予測（将来の drop-in 置換）
- **What:** 小型 LSTM / Transformer による pose prediction で `VelocityPredictor` を置換
- **Why:** 12ヶ月理想状態の一部。長時間遮蔽時の精度向上（速度ベースは 500ms 程度までが有効）
- **Effort:** L（CC: 3時間+、訓練 dataset 収集が別途必要）
- **Priority:** P3
- **Depends on:** 速度ベース (済) → 録画データ収集 → モデル訓練 → Protocol 適合実装
- **Context:** `pose_predictor.PosePredictor` Protocol を実装すれば `FusionEngine.predictor` をそのまま差し替え可能。学習には `recorder.py` の JSONL セッションログが活用できる

### ~~main.pyリファクタ（SubsystemManager）~~ ✅ 完了
- **解決:** `src/osc_tracking/main.py:33-63` に `SubsystemManager` クラス抽出済み。`add` / `get` / `start_all` / `stop_all` で各サブシステム (tray / dashboard / viewer / discord / api / obs / vmc / recorder / profiler / bvh / gesture) のライフサイクルを統一。CHANGELOG v0.2.2 に既に記載あり。TODOS.md の stale entry を掃除 (/plan-eng-review See-Something-Say-Something 指摘より)。

### ステレオカメラ深度精度検証
- **What:** 2台Webカメラ（0.5-1m間隔）で2-3m先の被写体の三角測量精度を実測
- **Why:** CEO Subagentが指摘。消費者向けWebカメラの深度分解能は未検証
- **Effort:** S（CC: 15分）
- **Priority:** P3
- **Context:** 静的精度テスト。既知距離の物体で計測

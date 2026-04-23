# Changelog

## Unreleased

### Added (docs)
- **`docs/slimevr-setup-guide.md`**: SlimeVR native / Tundra Labs / その他 SlimeVR 互換 IMU トラッカー向けのセットアップガイド。OSC 出力有効化、`connection_check` での疎通確認、OSC トラッカー番号マッピングがズレた場合の対処、トラッカー数が 8 未満の場合の挙動を明記。コードは既に device-agnostic なのでガイドのみで対応可能。`docs/other-trackers.md` と `README.md` から新ガイドへリンクを追加
- **`BaseIMUReceiver` template-method abstract class** (`src/osc_tracking/receiver_base.py`): OSC / BLE / Serial receiver で重複していたライフサイクル (idempotent start, freshness-aware reads, thread join warning) を集約。各 receiver は `_run_loop` / `_prepare_start` / `_on_stop_requested` / `_thread_name` の hook のみ実装。`IMUReceiver` Protocol 非破壊で `FusionEngine` / `main._build_receiver()` に影響なし

### Added (Tier A/B/C housekeeping & automation)
- **`OcclusionDetected` event publisher**: FusionEngine が joint-level で visible→occluded 遷移時に `OcclusionDetected(timestamp, bone)` を publish。初回未観測ジョイントは「遷移」扱いせずに false positive を防止
- **`BoneId.all()` クラスメソッド**: pre-DDD な `JOINT_NAMES` 直接参照を型付き `BoneId` イテレーションに置換可能に
- **テストカバレッジ大幅増加** (0% → 90%+ の production-path モジュール): `vmc_sender` (100%), `bvh_exporter` (100%), `notifications` (93%), `profiler` (100%), `rest_api` (71% → 91%)。単体テスト +48 件、合計 388 → 446 tests
- **CI: pip-audit 週次 + PR トリガ** (`.github/workflows/ci.yml`): pinned 依存関係の CVE を `--strict` で自動検知。新規 `security-audit` ジョブ
- **CI: E2E smoke gate** (`e2e-smoke` ジョブ): `python -m osc_tracking.tools.simulate --verify-modes --no-network --duration 10` を毎 PR で実行。VISIBLE / PARTIAL/FULL_OCCLUSION / IMU_DISCONNECTED の遷移を scripted で検証
- **CI: coverage ratchet を 25% → 45%** に引き上げ (Tier B 完了後の実測 48% に対応)

### Changed
- **CLAUDE.md / README**: DDD レイヤー構成 (domain / application / persistence)、EventBus、Skeleton Aggregate を明記。新 contributor 向けのナビゲーション改善
- **`simulate.py`**: `--duration`, `--no-network`, `--verify-modes` フラグ追加。CI smoke gate としての役割を公式化

### Removed
- **`Skeleton.to_legacy_joint_dict()`**: DDD 移行の残骸 (呼び出し元ゼロ)。grep で確認済み、削除

### Security (P1/P2 findings from internal audit)
- **REST API**: `/api/config` POST endpoint を撤去 (unauthenticated 任意属性書き込み経路、ローカルブラウザタブからの CSRF で OSC 送信先を書き換え可能だった)。mutating endpoints に Origin チェックを追加、非 localhost origin は 403
- **Web dashboard**: `innerHTML` 構築を `textContent` + DOM API に置換 (将来 BLE/Serial 経路から非 canonical な bone 名が混入した場合の stored XSS を防止)
- **Serial receiver**: 未パースバッファに `MAX_BUFFER_BYTES=4096` の上限を導入 (sync パターンを含まない garbage ストリームによるメモリ枯渇 DoS を防止)
- **Calibration repository**: `FileCalibrationRepository` がパスを cwd 配下に制限 (path traversal 防止)
- **Recorder**: `filename` パラメータから directory components を strip (caller-supplied path traversal 防止)
- **OBS overlay**: threshold 値を [0,1] にクランプ + `json.dumps` でシリアライズ (inline JS 注入の将来リスクを緩和)
- **stereo_calibration**: `np.load(path, allow_pickle=False)` を明示 (NumPy デフォルトと同じだが将来の回帰を文書化)

### Added
- **DDD Tier 1 — 形式化**: domain 層を正式パッケージ化 (`src/osc_tracking/domain/`)。Value Object (`Position3D` 有限値 guard / `Confidence` [0,1] 制約 / `BoneId` `JOINT_NAMES` 照合) + `Skeleton` Aggregate Root + `SkeletonSnapshot` 不変ビュー。`VisionProvider` Protocol を `camera_protocol.py` に抽出し `CameraTracker` が準拠。`persistence/` パッケージに `CalibrationRepository` / `RecordingRepository` / `ConfigRepository` Protocol を定義し既存アダプタ (`TrackingRecorder`, `FileCalibrationRepository`) が準拠。`FusionEngine` は毎フレーム `Skeleton` を更新し `snapshot()` で consumers に提供
- **DDD Tier 2 — Event 駆動化**: `application/event_bus.py` に同期 pub/sub `EventBus` を実装。`domain/events.py` に `DomainEvent` 基底 + `FrameProcessed` / `TrackingModeChanged` / `OcclusionDetected` / `IMUDisconnected` / `IMUReconnected` を定義。`FusionEngine` が毎サイクル FrameProcessed を publish、mode 遷移と IMU 接続/切断も event 化。`main.py` の per-frame loop から 11 subsystem の直接呼び出しを撤去し、すべて `_wire_event_subscribers()` 経由の subscription に移行 (loop body ~120 行 → ~30 行)
- **`FusionEngine.snapshot()`**: UI / 出力 subsystem が安定した frame snapshot を取得するための公式 API
- **`FusionEngine.events`** + **`event_bus` コンストラクタ引数**: 外部が bus を持ち込んで subscribe できる

### Changed
- **`FusionEngine.__init__(camera=...)` 型**: `CameraTracker` 具象型 → `VisionProvider` Protocol。任意の vision provider (MediaPipe 以外、playback、test fake) を注入可能に
- **`main.py` のメインループ**: subsystem 更新を event bus 経由に一本化。FPS 計算を `FusionEngine` の EMA 実装に委譲 (loop は表示用 FPS だけ独自集計)

### Added (preceding)
- **速度ベースポーズ予測器**: `src/osc_tracking/pose_predictor.py` に `PosePredictor` Protocol + `VelocityPredictor` 実装。ローリング履歴 (default 5 samples) から per-joint 線形速度を推定し、`FULL_OCCLUSION` / `PARTIAL_OCCLUSION` 時に `FusionEngine` が camera_pos 欠損箇所に予測値を注入。`stale_window_seconds` で長時間遮蔽後の teleport を抑止、`max_predict_seconds` で absurd extrapolation をクランプ。将来の DL ベース predictor は同 Protocol を実装して drop-in 差し替え可能
- **N台カメラ対応 (scaffold)**: `CameraConfig.cam_indices: list[int]` + `effective_cam_indices` / `camera_count` プロパティ、`--cams 0,1` CLI フラグ、`config.cam_indices` 設定項目。1台 (mono) / 2台 (stereo) に対応。3台以上は warn + 先頭2台のみ使用。真のマルチビュー三角測量 (bundle adjustment) は別 TODO
- **設定項目**: `pose_predictor_enabled`, `pose_predictor_max_history`, `pose_predictor_stale_window_sec`, `pose_predictor_max_predict_sec`, `cam_indices`
- **CLI フラグ**: `--cams 0,1`
- **Serial 直接接続レシーバ (experimental)**: `--receiver serial --port COM3` で GX6/GX2 USB dongle または Bluetooth Classic SPP COM ポート経由で HaritoraX 系トラッカーに直接接続。`pyserial` 依存、専用デーモンスレッドで `0xAA 0x55` sync + tracker_id + int16×4 quaternion のフレームをデコード（haritorax-interpreter `src/mode/com.ts` 準拠、クォータニオンは `ble_receiver.decode_rotation` を共有）。実機検証はまだ — 動作報告求む
- **`src/osc_tracking/serial_receiver.py`**: Serial レシーバ実装 (IMUReceiver protocol 準拠、length-framed parser、open 失敗時の reconnect back-off 内蔵)
- **`docs/serial-direct-guide.md`**: Serial 直接接続のセットアップ手順と EXPERIMENTAL 注記
- **設定項目**: `serial_port`, `serial_baudrate`, `serial_tracker_id_to_bone` (JSON key は文字列だが内部で int にコース)
- **CLI フラグ**: `--receiver serial`, `--port COM3`, `--baud 500000`
- **GitHub Issue template (`device-compat.yml`)**: HaritoraX2 / SlimeVR native / Tundra 等の動作報告を構造化フォームで受け取れるように。接続経路 (OSC / BLE / other) の dropdown、デバイス / トラッカー数 / OS / ファームウェア / バージョン / 結果 / ログ欄を含む。`docs/other-trackers.md` と `docs/ble-direct-guide.md` の誘導リンクを新 URL に更新
- **BLE 直接接続レシーバ (experimental)**: `--receiver ble` で SlimeTora + SlimeVR Server を介さず HaritoraX2 に直接接続。`bleak` 依存、asyncio を背景スレッドで動かして既存の threaded アーキテクチャに橋渡し。Sensor characteristic (`00dbf1c6-...`) を購読し 4× int16LE クォータニオンを復号（haritorax-interpreter 仕様準拠、z/w 符号反転）。実機検証はまだ — 動作報告求む
- **`src/osc_tracking/ble_receiver.py`** + **`tools/ble_scan.py`**: BLE レシーバ実装と、HaritoraX2 peripheral を列挙するディスカバリツール
- **`src/osc_tracking/receiver_protocol.py`**: OSC / BLE / 将来の Serial で共有する `IMUReceiver` Protocol (`@runtime_checkable`)
- **`src/osc_tracking/tracker_mapping.py`**: HaritoraX2 native label と SlimeVR OSC index の対応を一元化、OSCReceiver / BLEReceiver 両方から再利用
- **`docs/ble-direct-guide.md`**: BLE 直接接続のセットアップ手順と EXPERIMENTAL 注記
- **`docs/other-trackers.md`**: SlimeVR native / Tundra / その他 SlimeVR-Server 互換トラッカーの対応マトリクス。"動作報告求む" ステータスと Issue テンプレートで community PR 受け入れ体制を明示
- **設定項目**: `receiver_type`, `ble_device_name_prefix`, `ble_scan_timeout_sec`, `ble_local_name_to_bone`
- **CLI フラグ**: `--receiver {osc,ble}`, `--ble-device NAME`

### Changed
- **state_machine**: `on_osc_received()` → `on_imu_received()` にリネーム（受信経路に依存しない命名に）。fusion_engine.py、tools/simulate.py、テスト追随
- **FusionEngine**: `receiver` 引数型を `OSCReceiver` から `IMUReceiver` protocol に
- **OSCReceiver**: `DEFAULT_BONE_ADDRESSES` を `tracker_mapping.slimevr_osc_addresses()` 由来に（BLE 側と DRY）
- **汎用IMUミドルウェアへのリブランド（文言統一パス）**: docstring / CLI help / 通知 / setup wizard / README / QUICKSTART / DESIGN から HaritoraX2 特権化表現を除去し、OSC対応IMUトラッカー汎用 framing に統一。HaritoraX2 は「最初の対応デバイス」として位置付け。コード動作は不変
- **pyproject.toml**: `bleak>=0.21,<1.0` と `pyserial>=3.5,<4.0` を dependencies に追加
- **build_exe.py**: PyInstaller hidden imports に `bleak.backends.winrt.*` を追加

## v0.2.2 (2026-04-14) — Hardening & Rebrand

### Changed
- **汎用IMUミドルウェア化**: HaritoraX2専用→OSC対応IMUトラッカー汎用ミドルウェアにリブランド。他トラッカー対応の道を開く
- **main.pyリファクタ**: SubsystemManagerクラス抽出。サブシステムのstart/stopライフサイクルを統一（396→375行）

### Fixed
- **SharedMemoryバージョニング**: レイアウト変更時に旧プロセスとの不整合を防止（SHM_NAMEにバージョン番号を含める）
- **futon_trigger_jointバリデーション**: 不正なジョイント名の設定ミスがサイレント失敗していた問題を修正（警告＋フォールバック）
- **Config型バリデーション**: 設定ファイルの型不正値（文字列→数値等）を検出・スキップ。int/float相互変換に対応

## v0.2.1 (2026-04-14) — Per-Camera Confidence & Setup Wizard

### Added
- **カメラ別confidence分離**: 各カメラの信頼度を個別に追跡し、片方のカメラだけが見えなくなった場合（SINGLE_CAM_DEGRADED）を正確に検出できるように
- **セットアップウィザード**: `python -m osc_tracking.tools.setup_wizard` — 初回セットアップを7ステップでガイド（モデルDL→カメラ確認→SlimeVR接続→ポート確認→キャリブ→テスト→設定保存）
- **camera_tracker.pyテスト**: SharedMemory読み書き、カメラ別confidence、失効・NaNフィルタ、ライフサイクル
- **fusion_engineカメラ別confidenceテスト**: SINGLE_CAM_DEGRADED/VISIBLE/FULL_OCCLUSION判定

### Changed
- **統一品質閾値**: 信頼度の判定基準（0.7/0.3）をconfig.pyで一元管理。設定ファイルから閾値を変更できるように
- カメラサブプロセスとの通信データを拡張（SharedMemory 5→7 floats/joint）し、カメラ別の可視性情報を伝達

## v0.2.0 (2026-04-14) — Auto Drift Correction

### Added
- **FUTON_MODE**: 寝転がり検出 (ピッチ角 >60度で自動検出、カメラ補正を停止しIMU回転のみに切替)。入退場とも500msドウェルタイム、NaN/inf安全、トリガージョイント設定可能
- **ベンチマークツール**: `python -m osc_tracking.tools.benchmark` — MediaPipe Pose Landmarker Tasks APIのp50/p95/p99レイテンシ計測。30fps達成可否のアーキテクチャ判定
- **camera_tracker.py テスト**: SharedMemory読み書き、失効データフィルタ、NaNハンドリング、ライフサイクル、トーンリード検出 (17テスト)

### Fixed
- **compass_blend_factor設定が反映されない問題**: config.jsonで設定した値がフィルタに渡されずハードコード0.3で動作していた問題を修正。設定どおりのブレンド比率で動作するように
- **FUTON_MODE表示エラー**: ダッシュボード・シミュレーション・メインUIでFUTON_MODEのカラー表示が未登録だった問題を修正
- **config設定がデフォルト値で固定される問題**: futon閾値・compass_blend_factor等のconfig設定がFusionEngineに渡されていなかった問題を修正。設定ファイルの値が正しく反映されるように
- **FUTON_MODE退場時のフリッカー**: 退場時にもドウェルタイムを適用し、一瞬のピッチ変動によるモードフリッカーを防止
- **VERSION形式不整合**: VERSIONファイルとpyproject.tomlのバージョン形式を統一

### Changed
- ステートマシンを5モードから6モードに拡張
- ComplementaryFilterのcompass_blend_factorを必須パラメータに変更 ([0,1]クランプ付き)

## v0.1.0 (2026-04-08) — Initial Release

HaritoraX2 + デュアルWebカメラのセンサーフュージョンによるVRフルボディトラッキングシステム初版。

### コア機能
- **相補フィルタ**: Slerp回転ブレンド、ジョイントごとの独立ドリフトカット
- **5モードステートマシン**: Visible / Partial Occlusion / Full Occlusion / IMU切断 / 片カメラ劣化
- **両カメラ同時ロスト**: ヒステリシスバイパスで即座にフォールバック
- **Visual Compass**: カメラの肩ラインからIMUヘディングを補正
- **ステレオ三角測量**: OpenCVキャリブレーション + 3D座標推定
- **SlimeVR OSC受信**: クォータニオン正規化、ポート衝突3ポートリトライ

### 出力
- OSC送信（VRChat対応）
- VMC Protocol送信（--vmc フラグ、Resonite/ChilloutVR等対応）
- BVHモーションキャプチャエクスポート（--bvh フラグ）

### モニタリング
- Webダッシュボード (http://localhost:8765) — リアルタイム信頼度表示
- システムトレイ品質メーター（緑/黄/赤 + カラーブラインド対応テキストラベル）
- パフォーマンスプロファイラ（--profile フラグ）
- Discord Rich Presence（--discord フラグ）
- REST API（--api フラグ）

### ツール
- ステレオキャリブレーション
- カメラプレビュー（MediaPipeランドマークオーバーレイ）
- OSCデバッグモニタ
- 接続確認ツール（SlimeVR Server OSC検証）
- MediaPipeモデルダウンロード
- チェッカーボード画像生成
- シミュレーションモード

### 品質
- 125テスト、コアモジュール95%+カバレッジ
- CI: lint (ruff) + typecheck (mypy) + test (Python 3.10/3.11/3.12)
- 共有メモリLock同期 + PID付き命名（多重起動防止）

### デザイン
- **DESIGN.md**: Retro-Futuristic + Industrialデザインシステム（シアンアクセント#06b6d4、Cabinet Grotesk + Geist + JetBrains Mono）

### ドキュメント
- README（セットアップガイド、CLI全オプション、アーキテクチャ図）
- HaritoraX2プロトコル仕様（docs/haritora-protocol.md）
- E2Eテストチェックリスト（docs/e2e-test-checklist.md）
- QUICKSTART
- DESIGN.md（デザインシステム定義）

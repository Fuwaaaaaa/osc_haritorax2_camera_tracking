# Changelog

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

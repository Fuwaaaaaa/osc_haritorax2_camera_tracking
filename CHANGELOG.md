# Changelog

## v0.2.0 (2026-04-14) — Auto Drift Correction

### Added
- **FUTON_MODE**: 寝転がり検出 (ピッチ角 >60度で自動検出、カメラ補正を停止しIMU回転のみに切替)。入退場とも500msドウェルタイム、NaN/inf安全、トリガージョイント設定可能
- **ベンチマークツール**: `python -m osc_tracking.tools.benchmark` — MediaPipe Pose Landmarker Tasks APIのp50/p95/p99レイテンシ計測。30fps達成可否のアーキテクチャ判定
- **camera_tracker.py テスト**: SharedMemory読み書き、失効データフィルタ、NaNハンドリング、ライフサイクル、トーンリード検出 (17テスト)

### Fixed
- **compass_blend_factor バグ**: config値がComplementaryFilter/VisualCompassに渡されずハードコード0.3だった問題を修正。configからFusionEngine経由で正しくスレッディング
- **FUTON_MODE enum未登録**: main.py、simulate.py、web_dashboard.pyのMODE_COLORSにFUTON_MODEを追加 (KeyError防止)
- **config伝搬バグ**: main.pyがFusionEngineにconfigを渡さず、futon閾値・compass_blend_factor等がデフォルト値で固定されていた問題を修正
- **FUTON_MODE exit フリッカー**: 退場時にもドウェルタイムを適用し、一瞬のピッチ変動によるモードフリッカーを防止
- **VERSION形式不整合**: VERSION(4パート)とpyproject.toml(3パート)の不整合を修正

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

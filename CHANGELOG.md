# Changelog

## v0.1.1 (2026-04-14) — Per-Camera Confidence & Setup Wizard

### Added
- **カメラ別confidence分離**: SharedMemoryレイアウトを拡張し、カメラ別の信頼度をステートマシンに渡すように。SINGLE_CAM_DEGRADEDモードが正しく動作
- **セットアップウィザード**: `python -m osc_tracking.tools.setup_wizard` — 初回セットアップを7ステップでガイド（モデルDL→カメラ確認→SlimeVR接続→ポート確認→キャリブ→テスト→設定保存）
- **camera_tracker.pyテスト**: SharedMemory読み書き、カメラ別confidence、失効・NaNフィルタ、ライフサイクル（13テスト）
- **fusion_engineカメラ別confidenceテスト**: SINGLE_CAM_DEGRADED/VISIBLE/FULL_OCCLUSION判定（3テスト）

### Changed
- **統一品質閾値**: ComplementaryFilter/web_dashboard/preview.pyのハードコード0.7/0.3を設定値に置換。閾値変更時の変更漏れを防止
- SharedMemoryレイアウトを5→7 floats/joint（cam1_vis, cam2_vis追加）

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

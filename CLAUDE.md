# OSC Tracking

## Project
OSC対応IMUトラッカー + デュアルWebカメラのセンサーフュージョンによるVRフルボディトラッキングミドルウェア。HaritoraX2が最初の対応デバイス。

## Language
- コード・コメント: 英語
- ドキュメント・ユーザー向け: 日本語OK

## Architecture
- 2プロセス構成: カメラサブプロセス(MediaPipe) + メインプロセス(フュージョン+OSC)
- 相補フィルタ（MEKF不使用）
- 6モードステートマシン
- HaritoraX2はBLE/Serial通信（OSCではない）。SlimeTora→SlimeVR Server→OSC経由で接続

### レイヤー構成 (DDD / Clean Architecture)
```
src/osc_tracking/
├── domain/               # 純粋ドメイン、I/O なし
│   ├── values.py         # Position3D / Confidence / BoneId (Value Object)
│   ├── skeleton.py       # Skeleton Aggregate + SkeletonSnapshot
│   └── events.py         # DomainEvent + FrameProcessed / TrackingModeChanged /
│                         #   IMUDisconnected / IMUReconnected / OcclusionDetected
├── application/          # ユースケース / オーケストレーション
│   └── event_bus.py      # 同期 pub/sub EventBus
├── persistence/          # 永続化 Protocol (Repository パターン)
│   ├── protocols.py      # Calibration / Recording / ConfigRepository Protocol
│   └── calibration_repo.py
├── camera_protocol.py    # VisionProvider Protocol (MediaPipe 以外を注入可)
├── receiver_protocol.py  # IMUReceiver Protocol (OSC / BLE / Serial)
├── pose_predictor.py     # PosePredictor Protocol + VelocityPredictor
├── fusion_engine.py      # Application 層: Skeleton 更新 + event publish
├── main.py               # CLI + subsystem 構築 + event 購読 wire-up
└── camera_tracker.py, osc_*.py, ble_receiver.py, serial_receiver.py,
    recorder.py, vmc_sender.py, bvh_exporter.py, web_dashboard.py,
    obs_overlay.py, rest_api.py, ...    # Infrastructure アダプタ
```

### イベント駆動フロー
- `FusionEngine.update()` が毎サイクル `Skeleton` aggregate を更新し、`EventBus` 経由で
  `FrameProcessed` を publish。mode 遷移 / IMU 接続変化 / per-joint 遮蔽も event 化
- `main.py` の `_wire_event_subscribers()` が各 subsystem (dashboard / tray / vmc /
  recorder / obs / viewer / discord / api / bvh / gesture / notifier) を event に bind
- 新しい subsystem を足すときは `main.py` のループを触らず、`bus.subscribe(FrameProcessed, handler)` を増やすだけ
- 新しい output format (VMC 以外の何か) は同じ FrameProcessed subscriber として実装すれば、FusionEngine と main loop は不変

### 依存方向
- `domain/` は他ファイルから import しない (pure)
- `application/` は `domain/` だけを import
- Infrastructure (`camera_tracker`, receivers, senders, UI) は上位層を import してよい
- 逆向き (infra から domain への書き戻し) は禁止 — レビュー対象

## Testing
```bash
pytest
```
- pytest + pytest-cov
- TDD: テスト先行で書く
- カバレッジ目標: コアモジュール90%以上

## Commands
```bash
python -m osc_tracking.main                          # メインアプリ起動
python -m osc_tracking.tools.preview --cam1 0 --cam2 1  # カメラプレビュー
python -m osc_tracking.tools.calibrate               # ステレオキャリブレーション
python -m osc_tracking.tools.osc_monitor              # OSCデバッグ
python -m osc_tracking.tools.download_model           # MediaPipeモデルDL
python -m osc_tracking.tools.generate_checkerboard    # チェッカーボード生成
python -m osc_tracking.tools.connection_check         # SlimeVR OSC接続確認
python -m osc_tracking.tools.simulate                 # シミュレーションモード
python -m osc_tracking.tools.benchmark --cam1 0 --cam2 1  # カメラ推論ベンチマーク
python -m osc_tracking.tools.setup_wizard             # 初回セットアップウィザード
python build_exe.py                                   # exe全ビルド
python build_exe.py --main                            # メインexeのみ
python build_exe.py --tools                           # ツールexeのみ
```

## Key Files
- `src/osc_tracking/fusion_engine.py` — メインループ + event publishing
- `src/osc_tracking/complementary_filter.py` — センサーフュージョン (内部 JointState / JOINT_NAMES)
- `src/osc_tracking/state_machine.py` — 6モードステートマシン
- `src/osc_tracking/camera_tracker.py` — デュアルカメラ+MediaPipe (VisionProvider 実装)
- `src/osc_tracking/stereo_calibration.py` — 三角測量
- `src/osc_tracking/domain/skeleton.py` — Skeleton Aggregate Root
- `src/osc_tracking/application/event_bus.py` — 同期 pub/sub
- `config/default.json` — 設定ファイル
- `docs/haritora-protocol.md` — HaritoraX2プロトコル仕様

## Design System
Always read DESIGN.md before making any visual or UI decisions.
All font choices, colors, spacing, and aesthetic direction are defined there.
Do not deviate without explicit user approval.
In QA mode, flag any code that doesn't match DESIGN.md.

## Dependencies
- mediapipe (Pose Landmarker Tasks API, NOT legacy BlazePose)
- opencv-python
- python-osc
- numpy, scipy

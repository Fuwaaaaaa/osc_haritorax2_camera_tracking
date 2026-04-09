# OSC Tracking

## Project
HaritoraX2 + デュアルWebカメラのセンサーフュージョンによるVRフルボディトラッキングシステム。

## Language
- コード・コメント: 英語
- ドキュメント・ユーザー向け: 日本語OK

## Architecture
- 2プロセス構成: カメラサブプロセス(MediaPipe) + メインプロセス(フュージョン+OSC)
- 相補フィルタ（MEKF不使用）
- 5モードステートマシン
- HaritoraX2はBLE/Serial通信（OSCではない）。SlimeTora→SlimeVR Server→OSC経由で接続

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
```

## Key Files
- `src/osc_tracking/fusion_engine.py` — メインループ
- `src/osc_tracking/complementary_filter.py` — センサーフュージョン
- `src/osc_tracking/state_machine.py` — 6モードステートマシン
- `src/osc_tracking/camera_tracker.py` — デュアルカメラ+MediaPipe
- `src/osc_tracking/stereo_calibration.py` — 三角測量
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

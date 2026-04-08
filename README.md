# OSC Tracking — HaritoraX2 x Dual WebCam Hybrid Tracking

[![CI](https://github.com/Fuwaaaaaa/OSC_tracking/actions/workflows/ci.yml/badge.svg)](https://github.com/Fuwaaaaaa/OSC_tracking/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)
![License](https://img.shields.io/badge/license-MIT-green)

HaritoraX2（IMU）と2台のWebカメラ（MediaPipe）を融合し、磁気耐性・長時間安定性・布団内動作を実現するVRフルボディトラッキングシステム。

## 特徴

- **布団モード**: 遮蔽環境でIMUのみにフォールバック、カメラ復帰時にスムーズ同期
- **磁気ぐねり耐性**: Visual Compassがカメラの肩ラインでIMUヘディングを補正
- **長時間安定**: 相補フィルタが毎フレームドリフトを補正
- **2台カメラ**: ステレオ三角測量で精度の高い3D座標推定
- **既存ハードウェアのみ**: HaritoraX2 + Webカメラ2台 + PC

## 必要環境

- Python 3.10+
- HaritoraX2
- Webカメラ x 2
- Windows (VRChat推奨)

## インストール

```bash
pip install -e ".[dev]"
```

## 使い方

```bash
osc-tracking
```

## テスト

```bash
pytest
```

## アーキテクチャ

```
[HaritoraX2] --OSC--> [OSCReceiver] ──┐
                                        ├──► [FusionEngine] --OSC--> [VRChat]
[WebCam x2] --subprocess--> [CameraTracker] ──┘
```

- **2プロセス構成**: カメラ推論をサブプロセスで実行（GIL回避）
- **相補フィルタ**: カメラ位置 + IMU回転の重み付き融合
- **6モードステートマシン**: Visible / Partial / Full Occlusion / IMU切断 / 片カメラ劣化 / 再接続

## ライセンス

MIT

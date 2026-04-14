# OSC Tracking — HaritoraX2 x Dual WebCam Hybrid Tracking

[![CI](https://github.com/Fuwaaaaaa/OSC_tracking/actions/workflows/ci.yml/badge.svg)](https://github.com/Fuwaaaaaa/OSC_tracking/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)
![License](https://img.shields.io/badge/license-MIT-green)

HaritoraX2（IMU）と2台のWebカメラ（MediaPipe Pose Landmarker）をセンサーフュージョンし、VRフルボディトラッキングの精度と安定性を大幅に向上させるシステム。

## 特徴

- **布団から出た瞬間にドリフトゼロ復帰**: 布団内ではIMU回転で追従し、カメラ復帰時に蓄積ドリフトを即座に補正。HaritoraX2単体で30分使うとヘディングが数十度ずれるが、このシステムならゼロに戻る
- **磁気ぐねり耐性**: Visual Compassがカメラの肩ラインでIMUヘディングを補正。磁石やPCの近くでも安定
- **長時間安定**: 相補フィルタ（Slerp回転ブレンド）が毎フレームドリフトを補正
- **2台カメラ三角測量**: ステレオキャリブレーションで精度の高い3D座標推定。死角を低減
- **6モードステートマシン**: Visible / Partial Occlusion / Full Occlusion / IMU切断 / 片カメラ劣化 / 布団モード（FUTON_MODE）を自動判定。両カメラ同時ロスト時はヒステリシスをバイパスして即座にフォールバック
- **布団モード（FUTON_MODE）**: ピッチ角>60度で寝転がりを自動検出し、カメラ補正を停止してIMU回転のみに切替。入退場とも500msドウェルタイムでフリッカー防止
- **既存ハードウェアのみ**: HaritoraX2 + Webカメラ2台 + PC。追加購入不要

## 必要環境

- Python 3.10+
- HaritoraX2 + [SlimeTora](https://github.com/OCSYT/SlimeTora) + [SlimeVR Server](https://github.com/SlimeVR/SlimeVR-Server)
- Webカメラ x 2
- Windows（VRChat推奨）

> **注意**: HaritoraX2はOSCプロトコルを直接使用しません。SlimeTora → SlimeVR Server → OSC出力の経路で接続します。詳細は `docs/haritora-protocol.md` を参照。

## インストール

```bash
git clone https://github.com/Fuwaaaaaa/osc_haritorax2_camera_tracking.git
cd osc_haritorax2_camera_tracking
pip install -e ".[dev]"
```

MediaPipeモデルのダウンロード:

```bash
python -m osc_tracking.tools.download_model
```

## セットアップ

### クイックセットアップ（推奨）

初回は7ステップのセットアップウィザードで全体を一括ガイド:

```bash
python -m osc_tracking.tools.setup_wizard
```

モデルDL→カメラ確認→SlimeVR接続→ポート確認→キャリブ→テスト→設定保存を順番に実行します。

### 手動セットアップ

#### 1. ステレオキャリブレーション

チェッカーボード（同梱の `checkerboard_9x6_25mm.png` を印刷）を両カメラの視野内で複数角度から撮影:

```bash
python -m osc_tracking.tools.calibrate
```

#### 2. カメラプレビューで確認

```bash
python -m osc_tracking.tools.preview --cam1 0 --cam2 1
```

#### 3. SlimeTora + SlimeVR Server を起動

SlimeVR ServerのOSC出力をポート6969に設定。

#### 4. トラッキング開始

```bash
python -m osc_tracking.main
```

## CLIオプション

```
基本:
  --config PATH           設定ファイルのパス
  --cam1 N                カメラ1のインデックス（デフォルト: 0）
  --cam2 N                カメラ2のインデックス（デフォルト: 1）
  --osc-port N            OSC受信ポート（デフォルト: 6969）
  --vrchat-port N         VRChat送信ポート（デフォルト: 9000）
  --no-camera             カメラなしモード（OSCパススルー）

モニタリング:
  --no-tray               システムトレイアイコンを無効化
  --no-dashboard          Webダッシュボードを無効化
  --dashboard-port N      ダッシュボードポート（デフォルト: 8765）
  --viewer                3Dスケルトンビューア表示（matplotlib）
  --profile               パフォーマンスプロファイリング有効化

出力:
  --vmc                   VMC Protocol出力（Resonite, ChilloutVR等）
  --vmc-port N            VMCポート（デフォルト: 39539）
  --remap PROFILE         OSCアドレスリマップ（vrchat/resonite/chilloutvr）

録画・エクスポート:
  --record                セッションをJSONLファイルに録画
  --bvh PATH              BVHモーションキャプチャファイルをエクスポート

その他:
  --discord               Discord Rich Presence有効化
  --api                   REST API有効化（外部連携用）
  --api-port N            REST APIポート（デフォルト: 8766）
  --smoothing PRESET      モーションスムージング（default/anime/realistic/dance/sleep）
```

## モニタリング

### Webダッシュボード

起動後 http://localhost:8765 を開くと、リアルタイムで以下が確認できます:

- トラッキングモード（GOOD/WARNING/ERROR テキスト付き）
- FPS
- 全体信頼度
- 各ジョイントの信頼度バー（カラーブラインド対応テキストラベル付き）

### システムトレイ

タスクトレイに緑/黄/赤のアイコンを表示。ツールチップに「GOOD: VISIBLE (30 fps)」のようなテキストラベルを含みます。

## ツール

```bash
python -m osc_tracking.tools.calibrate           # ステレオキャリブレーション
python -m osc_tracking.tools.preview --cam1 0 --cam2 1  # カメラプレビュー
python -m osc_tracking.tools.osc_monitor          # OSCデバッグモニタ
python -m osc_tracking.tools.download_model       # MediaPipeモデルDL
python -m osc_tracking.tools.generate_checkerboard # チェッカーボード画像生成
python -m osc_tracking.tools.simulate             # シミュレーションモード
python -m osc_tracking.tools.connection_check     # SlimeVR OSC接続確認
python -m osc_tracking.tools.benchmark --cam1 0 --cam2 1  # カメラ推論ベンチマーク
python -m osc_tracking.tools.setup_wizard         # 初回セットアップウィザード
```

## アーキテクチャ

```
[HaritoraX2] --BLE/Serial--> [SlimeTora] --> [SlimeVR Server] --OSC-->
                                                                      |
                                                            [OSCReceiver] ──┐
                                                                            |
[WebCam 1] ──┐                                                              |
             ├── [Camera Subprocess] ── shared_memory(Lock) ──► [FusionEngine]
[WebCam 2] ──┘   (MediaPipe x2)         (PID付き名前)          |    |    |
                  (三角測量)                                     |    |    |
                                                    [StateMachine] [Filter] [VisualCompass]
                                                                            |
                                                                    [OSCSender] ---> [VRChat]
                                                                    [VMCSender] ---> [Resonite等]

オプション:
  [QualityMeter] タスクトレイ    [WebDashboard] ブラウザ
  [Profiler] 性能計測           [GestureDetector] ジェスチャー
  [Recorder] JSONL録画          [BVHExporter] モーキャプ
  [SkeletonViewer] 3D表示       [DiscordPresence] Discord
  [RestAPI] HTTP API            [NotificationManager] 通知
  [OSCRemapper] アドレス変換     [MotionSmoothing] プリセット
```

- **2プロセス構成**: カメラ推論をサブプロセスで実行（GIL回避）。共有メモリはLockで同期、PID付き名前で多重起動を防止
- **相補フィルタ**: カメラ位置 + IMU回転のSlerp重み付き融合。ジョイントごとの独立ドリフトカット
- **6モードステートマシン**: 信頼度ベースの自動遷移。ヒステリシス付き（両カメラ同時ロストは即座遷移）。FUTON_MODEはピッチ角ベースの自動検出

## テスト

```bash
pytest
```

171テスト、コアモジュール95%+カバレッジ:

| モジュール | カバレッジ |
|-----------|----------|
| complementary_filter | 99% |
| fusion_engine | 100% |
| state_machine | 99% |
| osc_receiver | 95% |
| osc_sender | 98% |
| visual_compass | 100% |
| config | 100% |
| camera_tracker | 36% |

## ライセンス

MIT

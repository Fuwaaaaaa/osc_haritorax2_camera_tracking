# Quick Start Guide — テスト手順

> **ヒント:** 初回の方は `python -m osc_tracking.tools.setup_wizard` で7ステップのガイド付きセットアップも利用できます。

## 事前準備（HaritoraX2不要）

### 1. 依存関係インストール
```bash
pip install -e ".[dev]"
```

### 2. MediaPipeモデルダウンロード
```bash
python -m osc_tracking.tools.download_model --variant heavy
```
約30MB。`models/pose_landmarker_heavy.task` に保存される。

### 3. カメラ確認
```bash
python -m osc_tracking.tools.preview --cam1 0 --cam2 1
```
2台のカメラが映れば OK。ランドマークが表示されればMediaPipeも OK。
カメラ番号が違う場合は `--cam1` `--cam2` を変更。

### 4. ステレオキャリブレーション
```bash
python -m osc_tracking.tools.calibrate --cam1 0 --cam2 1
```
1. チェッカーボード（9x6、25mmマス）を印刷
2. 両カメラに見えるように持つ
3. SPACE で撮影（最低10枚、異なる角度で）
4. `c` でキャリブレーション実行
5. `calibration_data/stereo_calib.npz` に保存される

チェッカーボードがなければスキップ可能（単眼深度推定にフォールバック）。

---

## HaritoraX2 テスト手順

### 方法A: SlimeTora経由（推奨）

1. **SlimeToraをインストール**: https://github.com/OCSYT/SlimeTora/releases
2. **SlimeVR Serverをインストール**: https://slimevr.dev/download
3. HaritoraX2の電源を入れる
4. SlimeToraでHaritoraX2に接続
5. SlimeVR ServerでOSC出力を有効化（Settings → OSC）
6. トラッキング開始:
```bash
python -m osc_tracking.main
```

### 方法B: 接続確認ツール

SlimeVR ServerからOSCデータが来ているか確認:
```bash
python -m osc_tracking.tools.connection_check
```
30秒間受信し、トラッカー数、メッセージレート、健全性を評価。

より詳細なOSCパケットモニタリング:
```bash
python -m osc_tracking.tools.osc_monitor
```

---

## テスト項目チェックリスト

### カメラのみテスト（HaritoraX2不要）
- [ ] `preview` で2台のカメラにランドマークが表示される
- [ ] キャリブレーション完了（または単眼フォールバック確認）
- [ ] `main` 起動でカメラサブプロセスが動く

### HaritoraX2テスト
- [ ] SlimeToraでHaritoraX2に接続成功
- [ ] `osc_monitor` でOSCデータ受信確認
- [ ] `main` 起動でフュージョンが動く
- [ ] VRChatでアバターが動く

### 布団テスト
- [ ] カメラの前で動く → Visible モード
- [ ] 布団を被る → Full Occlusion モード（位置凍結、回転のみ）
- [ ] 布団から出る → スムーズ復帰

### 長時間テスト
- [ ] 30分連続使用でドリフトが発生するか
- [ ] 磁石をPCの横に置いてヘディングが安定するか

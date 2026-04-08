# HaritoraX2 Communication Protocol

調査日: 2026-04-08
情報源: [haritorax-interpreter](https://github.com/JovannMC/haritorax-interpreter), [SlimeTora](https://github.com/OCSYT/SlimeTora)

## 通信方式

HaritoraX2はOSCプロトコルを使用**しない**。以下の3つの通信方式をサポート:

1. **Bluetooth Low Energy (BLE)** — ワイヤレス直接接続
2. **Bluetooth Classic (Serial/SPP)** — COMポート経由のシリアル通信
3. **GX6/GX2 USBドングル** — USB→ワイヤレスブリッジ、COMポートインターフェース

## 送信データ

### 回転データ（IMUイベント）
- **クォータニオン (x, y, z, w)** — 16bit符号付き整数から復号、スケーラー: 0.01/180.0
- **位置データなし** — IMUベースのため絶対位置は送信されない

### 重力加速度
- **3軸ベクトル (x, y, z)** — スケーラー: 1/256.0

### 足首モーション
- **Boolean** — 足首のひねり検出フラグ

### バッテリー
- 電圧、充電状態

## トラッカー名（8箇所）

| トラッカー名 | 体の部位 | 設計書の対応 |
|-------------|---------|-------------|
| chest | 胸 | Chest |
| hip | 腰 | Hips |
| rightElbow | 右肘 | (設計書になし→追加候補) |
| leftElbow | 左肘 | (設計書になし→追加候補) |
| rightKnee | 右膝 | (設計書になし→追加候補) |
| rightAnkle | 右足首 | RightFoot |
| leftKnee | 左膝 | (設計書になし→追加候補) |
| leftAnkle | 左足首 | LeftFoot |

**注意**: 設計書の7関節（Hips, Chest, Head, LeftFoot, RightFoot, LeftHand, RightHand）と
HaritoraX2の8トラッカーにずれがある。Head、LeftHand、RightHandはHaritoraX2にない。
Elbow、Kneeは設計書にないが実機からデータが来る。

## アーキテクチャへの影響

1. **OSCReceiverは不要** — BLE/シリアル通信モジュールに置き換える必要がある
2. **haritorax-interpreterのPython移植**が必要、または**SlimeVR Server経由でOSC転送**する方法もある
3. **位置データなし確定** — フュージョンエンジンはカメラ由来の位置のみを使用
4. **トラッカーマッピングの修正**が必要

## 推奨アプローチ

**Option A: SlimeTora経由（簡単）**
SlimeToraがHaritoraX2→SlimeVR Serverに中継。SlimeVR ServerがOSC出力可能。
既存のOSCReceiverをそのまま使える。

**Option B: Python BLEライブラリで直接通信（完全）**
bleak（Python BLEライブラリ）でHaritoraX2に直接接続。
haritorax-interpreterのロジックをPythonに移植。

**Option C: haritorax-interpreterをNode.jsサブプロセスで実行（ハイブリッド）**
haritorax-interpreterをインストールし、データをstdout/パイプで受け取る。

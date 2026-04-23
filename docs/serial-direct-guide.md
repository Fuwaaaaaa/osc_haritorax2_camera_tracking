# HaritoraX Serial (GX6/GX2 / SPP) 直接接続ガイド (experimental)

> ⚠️ **EXPERIMENTAL — 実機動作未検証**
> この経路は haritorax-interpreter (`src/mode/com.ts`) と公開プロトコル仕様をもとに実装されていますが、
> 本プロジェクトではまだ実機での動作確認が取れていません。
> 動作報告・不具合報告を歓迎します → [Issues](https://github.com/Fuwaaaaaa/osc_haritorax2_camera_tracking/issues)

## 何が違うのか

従来の経路:
```
HaritoraX → SlimeTora → SlimeVR Server → OSC(:6969) → osc_tracking
```

Serial 直接経路:
```
HaritoraX → GX6/GX2 USB dongle (or SPP COM) → osc_tracking
```

SlimeTora と SlimeVR Server を挟まないので、中間ソフトウェアの更新停止やバグの影響を受けにくく、
BLE より低遅延が期待できる有線接続が使えます。ただし HaritoraX 系のトラッカーに限定されます（OSC 経路は引き続き汎用）。

## 対応ハードウェア

- **GX6 dongle** — 最大 6 トラッカー (tracker_id 0..5)
- **GX2 dongle** — 最大 2 トラッカー (tracker_id 0..1)
- **Bluetooth Classic SPP** — Windows で HaritoraX を COM ポートとしてペアリング可能な構成（要ドライバ確認）

## 必要環境

- Windows / macOS / Linux
- Python 3.10 以上（exe 版を使う場合は不要）
- `pyserial` 3.5 以上（コアで自動インストール）
- GX6/GX2 dongle の場合: USB 認識、COM ポートとして列挙されていること

## セットアップ

### 1. COM ポートを調べる

**Windows:**
- デバイスマネージャー → 「ポート (COM と LPT)」で `USB Serial Device (COMxx)` を確認
- もしくは PowerShell: `[System.IO.Ports.SerialPort]::GetPortNames()`

**Linux / macOS:**
- `ls /dev/tty.*` (macOS) または `ls /dev/ttyUSB* /dev/ttyACM*` (Linux)
- GX6/GX2 は通常 `/dev/ttyUSB0` として認識

### 2. config/user.json に tracker_id → 骨部位マッピングを書く

GX dongle は各トラッカーに 0 から始まる ID を振ります。どの ID がどの部位かは
SlimeTora や haritorax-configurator の設定に従います（初期状態は貼り付けた順）。

例: `config/user.json`
```json
{
  "receiver_type": "serial",
  "serial_port": "COM3",
  "serial_baudrate": 500000,
  "serial_tracker_id_to_bone": {
    "0": "Hips",
    "1": "Chest",
    "2": "LeftFoot",
    "3": "RightFoot",
    "4": "LeftKnee",
    "5": "RightKnee"
  }
}
```

> **JSON の制約**: `serial_tracker_id_to_bone` のキーは JSON では文字列として書きますが、
> 内部で自動的に `int` に変換されます。

骨部位名は次のいずれか: `Hips`, `Chest`, `LeftFoot`, `RightFoot`, `LeftKnee`, `RightKnee`, `LeftElbow`, `RightElbow`.

### 3. 起動

```bash
python -m osc_tracking.main --receiver serial --port COM3
```

CLI から baud rate を上書きする場合:
```bash
python -m osc_tracking.main --receiver serial --port COM3 --baud 500000
```

exe 版:
```bash
osc_tracking.exe --receiver serial --port COM3
```

起動ログ例:
```
SerialReceiver started (port=COM3, baud=500000, 6 tracker mappings)
Serial port COM3 opened
```

## トラブルシューティング

- **`Serial open COM3 @ 500000 failed: could not open port`**
  - 他アプリ（SlimeTora / haritorax-configurator 等）が COM ポートを掴んでいる可能性。それらを終了。
  - 管理者権限が必要な環境では Python を管理者として実行。
- **`pyserial is not installed`**
  - `pip install pyserial` で個別インストール、または `pip install -e .` で依存関係を再同期。
- **`Serial bone mapping contains unknown bone name(s)`**
  - 骨部位名のタイポ（大文字小文字区別あり）。`Hips` / `Chest` など正確に。
- **データが流れてこない（`IMU: DISCONNECTED`）**
  - baud rate が合っていない可能性。GX6/GX2 デフォルトは 500000 bps。
  - dongle 側で実際にトラッカーを受信しているか SlimeTora 等で一度確認してから接続。
  - 最後の手段: 本ガイドが参照した
    [haritorax-interpreter `src/mode/com.ts`](https://github.com/JovannMC/haritorax-interpreter/blob/main/src/mode/com.ts)
    とフレーム形式 (`src/osc_tracking/serial_receiver.py` docstring) を照合し、
    Issue で波形ログ（先頭 64 バイト程度）を共有してください。

## 動作報告の書き方

[**Device compatibility report テンプレート**](https://github.com/Fuwaaaaaa/osc_haritorax2_camera_tracking/issues/new?template=device-compat.yml)
から Issue を立ててください。フォームの「接続経路」で **Serial 直接 (--receiver serial, experimental)** を選択 →
OS / dongle モデル (GX6/GX2) / baud / ログ / 動いた箇所・詰まった箇所 を入力すれば必要情報が揃います。
`pyserial` のバージョン (`pip show pyserial`) と COM ポート一覧も「追加情報」欄に貼ってもらえると助かります。

フィードバックで `docs/other-trackers.md` の動作確認表を更新します。

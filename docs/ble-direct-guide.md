# HaritoraX2 BLE 直接接続ガイド (experimental)

> ⚠️ **EXPERIMENTAL — 実機動作未検証**
> この経路は haritorax-interpreter と公開プロトコル仕様をもとに実装されていますが、
> 本プロジェクトではまだ HaritoraX2 実機での動作確認が取れていません。
> 動作報告・不具合報告を歓迎します → [Issues](https://github.com/Fuwaaaaaa/osc_haritorax2_camera_tracking/issues)

## 何が違うのか

従来の接続経路:
```
HaritoraX2 → SlimeTora → SlimeVR Server → OSC(:6969) → osc_tracking
```

BLE 直接経路:
```
HaritoraX2 → (BLE) → osc_tracking
```

SlimeTora と SlimeVR Server を挟まないので、中間ソフトウェアの更新停止やバグの影響を受けにくい一方、**HaritoraX2 以外のトラッカー** は使えません（OSC 経路は引き続き汎用）。

## 必要環境

- Windows 10 build 1803 以降 / macOS / Linux (BlueZ)
- Python 3.10 以上（exe 版を使う場合は不要）
- HaritoraX2 本体が BLE 接続可能な状態（SlimeTora 側のペアリングを解除しておく）

## セットアップ

### 1. デバイスの local name を調べる

HaritoraX2 は 1 トラッカー = 1 BLE peripheral としてアドバタイズします（例: `HaritoraX2-A1B2`）。ご自身のキットで実際にアドバタイズされる名前を scan ツールで確認します。

```bash
python -m osc_tracking.tools.ble_scan
```

出力例:
```
HaritoraX2-A1B2    XX:XX:XX:XX:XX:XX
HaritoraX2-C3D4    XX:XX:XX:XX:XX:XX
HaritoraX2-E5F6    XX:XX:XX:XX:XX:XX
...
```

近くにいるのに出てこない場合は `--timeout 20` で scan 時間を延ばすか、`--all` で全デバイスを列挙してください。

### 2. config/user.json に peripheral → 骨部位マッピングを書く

どの peripheral がどの部位かは、現状ではユーザーが物理的に確認して設定する必要があります（本プロジェクトでは `BodyPartAssignment` の読取り対応は未実装）。

例: `config/user.json`
```json
{
  "receiver_type": "ble",
  "ble_local_name_to_bone": {
    "HaritoraX2-A1B2": "Hips",
    "HaritoraX2-C3D4": "Chest",
    "HaritoraX2-E5F6": "LeftFoot",
    "HaritoraX2-G7H8": "RightFoot",
    "HaritoraX2-I9J0": "LeftKnee",
    "HaritoraX2-K1L2": "RightKnee",
    "HaritoraX2-M3N4": "LeftElbow",
    "HaritoraX2-O5P6": "RightElbow"
  }
}
```

骨部位名は次のいずれか: `Hips`, `Chest`, `LeftFoot`, `RightFoot`, `LeftKnee`, `RightKnee`, `LeftElbow`, `RightElbow`.

### 3. 起動

```bash
python -m osc_tracking.main --receiver ble
```

もしくは exe 版:
```bash
osc_tracking.exe --receiver ble
```

起動時にログを確認してください。各 peripheral への接続が成立すると:
```
BLEReceiver started (prefix='HaritoraX2-', 8 bone mappings)
Connected to HaritoraX2-A1B2 (-> Hips)
Connected to HaritoraX2-C3D4 (-> Chest)
...
```

## トラブルシューティング

- **`No HaritoraX2-* devices found`**: 電源が入っているか、他アプリ（SlimeTora 等）が掴んでいないかを確認。
- **`bleak is not installed`**: `pip install bleak` で個別インストール、または `pip install -e .` で依存関係を再同期。
- **exe 版で動かない**: PyInstaller の WinRT バインディングが正しく同梱されているか `build_exe.py` の `HIDDEN_IMPORTS` に `bleak.backends.winrt.*` が入っているか確認してください。
- **Linux で `BleakError: Bluetooth adapter not found`**: `sudo apt install bluez libbluetooth-dev` (Ubuntu の場合)。

## 動作報告の書き方

[新しい Issue](https://github.com/Fuwaaaaaa/osc_haritorax2_camera_tracking/issues/new) で以下を教えてください:

- OS / bleak バージョン (`pip show bleak`)
- HaritoraX2 のファームウェアバージョン
- `ble_scan` の出力
- 動いた箇所 / 動かなかった箇所
- 起動時の `osc_tracking` ログ

フィードバックで `docs/other-trackers.md` の動作確認表を更新します。

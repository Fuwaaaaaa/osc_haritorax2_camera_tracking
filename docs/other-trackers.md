# 対応トラッカー一覧

このプロジェクトは **OSC 対応の任意の IMU トラッカー** を受信できるミドルウェアです。
具体的には **SlimeVR Server OSC output 形式** (`/tracking/trackers/{id}/rotation`) に
対応したトラッカーなら原理的に動作します。

## 動作確認済み

| デバイス | 接続経路 | ステータス | ガイド |
|---|---|---|---|
| HaritoraX2 | SlimeTora → SlimeVR Server → OSC | ✅ 動作確認 | [haritora-setup-guide.md](haritora-setup-guide.md) |
| HaritoraX2 | BLE 直接 (bleak) | 🧪 experimental | [ble-direct-guide.md](ble-direct-guide.md) |
| HaritoraX / HaritoraX2 | GX6/GX2 dongle or SPP (pyserial) | 🧪 experimental | [serial-direct-guide.md](serial-direct-guide.md) |

## 動作報告求む (原理的に動くはず)

以下は SlimeVR Server の OSC output を使うトラッカー。コードは既に対応しているはずですが、
実機動作報告がまだありません。**動いた / 動かなかった** どちらの報告も歓迎します
→ [Issues](https://github.com/Fuwaaaaaa/osc_haritorax2_camera_tracking/issues)

| デバイス | 接続経路 | ステータス | メモ |
|---|---|---|---|
| SlimeVR (native) | SlimeVR Server → OSC | 🟡 未検証 | [slimevr-setup-guide.md](slimevr-setup-guide.md) |
| Tundra Labs Trackers | SlimeVR Server → OSC | 🟡 未検証 | [slimevr-setup-guide.md](slimevr-setup-guide.md) (SlimeVR Server 経由は共通) |
| その他 SlimeVR 互換 | SlimeVR Server → OSC | 🟡 未検証 | 6〜8 トラッカー構成。[slimevr-setup-guide.md](slimevr-setup-guide.md) を参照 |

## 設定方法 (共通)

SlimeVR native / Tundra / その他 SlimeVR 互換トラッカーの詳細なセットアップ手順は
**[slimevr-setup-guide.md](slimevr-setup-guide.md)** に移しました (OSC 出力の有効化、
`connection_check` による疎通確認、マッピングがズレたときの対処まで)。

要点のみ:

1. SlimeVR Server の **Settings → OSC → OSC output** を **Enabled** にし、送信先を `127.0.0.1:6969` に設定
2. 本ミドルウェアの `config/default.json` で `osc_receive_port` を 6969 に合わせる (デフォルト値と同じ)
3. デフォルトのトラッカーマッピング: ID 1=Hips / 2=Chest / 3=LeftFoot / 4=RightFoot / 5=LeftKnee / 6=RightKnee / 7=LeftElbow / 8=RightElbow
4. 異なる構成の場合は [`src/osc_tracking/tracker_mapping.py`](../src/osc_tracking/tracker_mapping.py) を参照してカスタマイズ

## 動作報告の書き方

[**Device compatibility report テンプレート**](https://github.com/Fuwaaaaaa/osc_haritorax2_camera_tracking/issues/new?template=device-compat.yml) から Issue を立ててください。必要項目がフォームで揃うので、デバイス名 / ファームウェア / トラッカー数 / SlimeVR Server バージョン / 動いた箇所 / 詰まった箇所 / ログ、を漏れなく共有できます。

動作確認できたら README / この表を更新します。

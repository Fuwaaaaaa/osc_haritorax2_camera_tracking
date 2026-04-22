# 対応トラッカー一覧

このプロジェクトは **OSC 対応の任意の IMU トラッカー** を受信できるミドルウェアです。
具体的には **SlimeVR Server OSC output 形式** (`/tracking/trackers/{id}/rotation`) に
対応したトラッカーなら原理的に動作します。

## 動作確認済み

| デバイス | 接続経路 | ステータス | ガイド |
|---|---|---|---|
| HaritoraX2 | SlimeTora → SlimeVR Server → OSC | ✅ 動作確認 | [haritora-setup-guide.md](haritora-setup-guide.md) |

## 動作報告求む (原理的に動くはず)

以下は SlimeVR Server の OSC output を使うトラッカー。コードは既に対応しているはずですが、
実機動作報告がまだありません。**動いた / 動かなかった** どちらの報告も歓迎します
→ [Issues](https://github.com/Fuwaaaaaa/osc_haritorax2_camera_tracking/issues)

| デバイス | 接続経路 | ステータス | メモ |
|---|---|---|---|
| SlimeVR (native) | SlimeVR Server → OSC | 🟡 未検証 | SlimeVR Server Settings → OSC Output を有効化 |
| Tundra Labs Trackers | SlimeVR Server → OSC | 🟡 未検証 | SlimeVR Server 経由なら同様に動作想定 |
| その他 SlimeVR 互換 | SlimeVR Server → OSC | 🟡 未検証 | 6〜8 トラッカー想定 |

## 設定方法 (共通)

1. SlimeVR Server の OSC Output を有効化し、送信先を `127.0.0.1:6969` に設定
2. 本ミドルウェアの `config/default.json` で `osc_receiver.port` を 6969 に合わせる
3. デフォルトのトラッカーマッピング: ID 1=Hips / 2=Chest / 3=LeftFoot / 4=RightFoot / 5=LeftKnee / 6=RightKnee / 7=LeftElbow / 8=RightElbow
4. 異なる構成の場合は `src/osc_tracking/osc_receiver.py` の `DEFAULT_TRACKER_MAP` を参照してカスタマイズ

## 動作報告の書き方

[新しい Issue](https://github.com/Fuwaaaaaa/osc_haritorax2_camera_tracking/issues/new) を立てて以下を教えてください:

- デバイス名 / ファームウェアバージョン
- トラッカー数
- SlimeVR Server バージョン
- 動いた箇所 / 詰まった箇所
- ログ (`osc_tracking.exe` のコンソール出力) があればなお嬉しい

動作確認できたら README / この表を更新します。

# SlimeVR native / Tundra セットアップガイド

> **ステータス:** 🟡 未検証 (原理的に動作するはず)
>
> OSC Tracking の OSC 受信機は SlimeVR Server の OSC 出力形式にそのまま対応しているため、
> **SlimeVR 互換トラッカーであればコード変更なしで動作するはず**です。実機確認ができ次第
> [docs/other-trackers.md](other-trackers.md) のステータスを ✅ に昇格します。
> 動いた／動かなかった、どちらの報告も [Issues](https://github.com/Fuwaaaaaa/osc_haritorax2_camera_tracking/issues/new?template=device-compat.yml) から歓迎します。

対象: SlimeVR native トラッカー、Tundra Labs トラッカー、その他 SlimeVR Server が
直接認識する IMU トラッカー。

接続経路:

```
SlimeVR/Tundra トラッカー --WiFi/BLE--> SlimeVR Server --OSC(port 6969)--> OSC Tracking
```

HaritoraX2 (SlimeTora 経由) のガイドは [docs/haritora-setup-guide.md](haritora-setup-guide.md) を参照。

---

## 必要ソフトウェア

### 1. SlimeVR Server (トラッカーゲートウェイ + OSC 出力)

**ダウンロード:** https://slimevr.dev/download

1. 最新版をダウンロード・インストール
2. 初回起動時のウィザードで身体計測を完了
3. トラッカーの電源を入れる
4. SlimeVR Server がトラッカーを自動検出
5. 必要なトラッカー (6〜8個) が全て認識されることを確認

トラッカー自体のセットアップ (ファームウェア更新、Wi-Fi 接続、ペアリング) は
SlimeVR / Tundra 各公式ドキュメントに従ってください:

- SlimeVR: https://docs.slimevr.dev/
- Tundra Labs: https://docs.tundra-labs.com/

### 2. SlimeVR Server の OSC 出力を有効化

1. SlimeVR Server の **Settings** → **OSC** を開く
2. **OSC output** を **Enabled** にする
3. **Port** を **6969** に設定 (OSC Tracking のデフォルト受信ポート)
4. **Address** は `127.0.0.1` (ローカル送信)

> **注意:** SlimeVR Server の OSC アドレスパターンは `/tracking/trackers/{N}/rotation` 形式。
> OSC Tracking の `osc_receiver.py` はこの形式をそのまま受信します。

---

## 接続確認

### ステップ1: OSC データ受信確認

```bash
python -m osc_tracking.tools.connection_check --port 6969 --duration 15
```

**期待される結果:**

```
  First message received!
  /tracking/trackers/1/rotation: [0.0012, -0.7071, 0.0034, 0.7071]
  ...
  HEALTH: GOOD - N rotation trackers detected
  Ready for tracking!
```

- `HEALTH: GOOD` + 6 個以上の `rotation` アドレス → OK
- `HEALTH: PARTIAL` → 一部のトラッカーが未接続
- `NO MESSAGES RECEIVED` → SlimeVR Server の OSC 設定を確認

### ステップ2: 詳細モニタリング (オプション)

```bash
python -m osc_tracking.tools.osc_monitor
```

リアルタイムで OSC パケットの中身を表示。アドレスパターンとデータ形式を確認できます。

### ステップ3: フルシステム起動

```bash
python -m osc_tracking.main
```

---

## OSC アドレスマッピング

SlimeVR Server の OSC 出力と、OSC Tracking の関節マッピング:

| SlimeVR OSC アドレス | OSC Tracking 関節名 | 標準的な装着位置 |
|---|---|---|
| `/tracking/trackers/1/rotation` | Hips | 腰 |
| `/tracking/trackers/2/rotation` | Chest | 胸 |
| `/tracking/trackers/3/rotation` | LeftFoot | 左足首 |
| `/tracking/trackers/4/rotation` | RightFoot | 右足首 |
| `/tracking/trackers/5/rotation` | LeftKnee | 左膝 |
| `/tracking/trackers/6/rotation` | RightKnee | 右膝 |
| `/tracking/trackers/7/rotation` | LeftElbow | 左肘 |
| `/tracking/trackers/8/rotation` | RightElbow | 右肘 |

デフォルト値は [`src/osc_tracking/tracker_mapping.py`](../src/osc_tracking/tracker_mapping.py) の
`SLIMEVR_OSC_INDEX_TO_SKELETON` で定義されています。

### マッピングが合わないとき

SlimeVR Server のトラッカー番号は **トラッカーを検出した順序** で割り当てられるため、
構成によっては上記と一致しないことがあります。以下のいずれかで対処できます:

**A. SlimeVR Server 側で順序を固定する**

Body Settings でトラッカーの **Role** を明示的に割り当て、Hips が index 1 に来る配置にする。

**B. `osc_monitor` で実際のアドレスを確認してから修正する**

```bash
python -m osc_tracking.tools.osc_monitor
```

で受信しているアドレスを確認し、[`src/osc_tracking/osc_receiver.py`](../src/osc_tracking/osc_receiver.py)
の `OSCReceiver.DEFAULT_BONE_ADDRESSES` を実構成に合わせて上書きする
(今後 `config/user.json` でのオーバーライドを足す予定)。

---

## トラッカー数が 8 未満の場合

OSC Tracking は 8 個フルセットを想定した設定になっていますが、6 個 (腰・胸・両足首・両膝)
構成でも動作します。足りないトラッカーは単にデータが来ないため、該当ボーンは
`FusionEngine` 内で IMU ソースなしとして扱われます。

- 手のトラッカー (LeftElbow / RightElbow) が無い場合 → 上半身の yaw ドリフト補正が
  "布団モード" 等で精度低下する可能性があります。Chest の Visual Compass 補正は働きます
- 膝 (LeftKnee / RightKnee) が無い場合 → 足の pose は足首トラッカーのみから推定されます

---

## チェックリスト

- [ ] トラッカーの電源 ON、Wi-Fi / BLE 接続済み
- [ ] SlimeVR Server インストール済み
- [ ] SlimeVR Server でトラッカーが認識されている (必要数)
- [ ] SlimeVR Server の OSC 出力を有効化 (ポート 6969)
- [ ] `connection_check` で `HEALTH: GOOD` 確認
- [ ] `python -m osc_tracking.main` で起動確認
- [ ] VRChat / VMC 等で姿勢追従を確認
- [ ] 動作報告を [Issue](https://github.com/Fuwaaaaaa/osc_haritorax2_camera_tracking/issues/new?template=device-compat.yml) に投稿

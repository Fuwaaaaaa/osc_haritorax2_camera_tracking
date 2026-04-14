# HaritoraX2 実機テストセットアップガイド

HaritoraX2をOSC Trackingで使うための接続経路:

```
HaritoraX2 --BLE--> SlimeTora ---> SlimeVR Server --OSC(port 6969)--> OSC Tracking
```

## 必要ソフトウェア

### 1. SlimeTora（HaritoraX2 → SlimeVR ブリッジ）

**ダウンロード:** https://github.com/OCSYT/SlimeTora/releases

1. 最新版の `SlimeTora-Setup-x.x.x.exe` をダウンロード
2. インストーラーを実行
3. 起動後、HaritoraX2の電源を入れる
4. SlimeToraが自動的にBLE接続を検出
5. 全トラッカー（8個）が接続されるのを確認:
   - chest, hip, leftElbow, rightElbow
   - leftKnee, rightKnee, leftAnkle, rightAnkle

**トラブルシューティング:**
- BLEが検出されない → PCのBluetooth設定を確認（Realtek BLEアダプタが有効であること）
- 接続が不安定 → HaritoraX2を充電、PCとの距離を2m以内に
- 一部のトラッカーだけ検出 → トラッカーのIMU校正をリセット（HaritoraX2本体でリセット操作）

### 2. SlimeVR Server（OSC出力ゲートウェイ）

**ダウンロード:** https://slimevr.dev/download

1. 最新版をダウンロード・インストール
2. 初回起動時のウィザードをスキップ（または完了）
3. SlimeToraからのトラッカーが自動認識される

**OSC出力の設定（重要）:**
1. SlimeVR Serverの **Settings** → **OSC** を開く
2. **OSC output** を **Enabled** にする
3. **Port** を **6969** に設定（OSC Trackingのデフォルト受信ポート）
4. **Address** は `127.0.0.1`（ローカル）

> **注意:** SlimeVR ServerのOSCアドレスパターンは `/tracking/trackers/{N}/rotation` 形式。
> OSC Trackingのosc_receiver.pyはこの形式を受信するように設定済み。

## 接続確認

### ステップ1: OSCデータ受信確認

```bash
python -m osc_tracking.tools.connection_check --port 6969 --duration 15
```

**期待される結果:**
```
  First message received!
  /tracking/trackers/1/rotation: [0.0012, -0.7071, 0.0034, 0.7071]
  ...
  HEALTH: GOOD - 8 rotation trackers detected
  Ready for tracking!
```

- `HEALTH: GOOD` + 6個以上のrotationアドレス → OK
- `HEALTH: PARTIAL` → 一部のトラッカーが未接続
- `NO MESSAGES RECEIVED` → SlimeVR ServerのOSC設定を確認

### ステップ2: 詳細モニタリング（オプション）

```bash
python -m osc_tracking.tools.osc_monitor
```

リアルタイムでOSCパケットの中身を表示。アドレスパターンとデータ形式を確認できる。

### ステップ3: フルシステム起動

```bash
python -m osc_tracking.main
```

## OSCアドレスマッピング

SlimeVR Serverが送信するOSCアドレスと、OSC Trackingの関節マッピング:

| SlimeVR OSCアドレス | HaritoraX2トラッカー | OSC Tracking関節名 |
|---|---|---|
| `/tracking/trackers/1/rotation` | hip | Hips |
| `/tracking/trackers/2/rotation` | chest | Chest |
| `/tracking/trackers/3/rotation` | leftAnkle | LeftFoot |
| `/tracking/trackers/4/rotation` | rightAnkle | RightFoot |
| `/tracking/trackers/5/rotation` | leftKnee | LeftKnee |
| `/tracking/trackers/6/rotation` | rightKnee | RightKnee |
| `/tracking/trackers/7/rotation` | leftElbow | LeftElbow |
| `/tracking/trackers/8/rotation` | rightElbow | RightElbow |

> **マッピングが合わない場合:** SlimeVR ServerのOSCトラッカー番号は設定によって変わることがあります。
> `osc_monitor` で実際のアドレスを確認し、`config/user.json` でオーバーライドするか、
> `--remap` オプションを使用してください。

## チェックリスト

- [ ] Bluetooth LEアダプタが有効（Realtek Wireless Bluetooth Adapter: OK）
- [ ] SlimeToraインストール済み
- [ ] SlimeVR Serverインストール済み
- [ ] HaritoraX2充電済み・電源ON
- [ ] SlimeToraでBLE接続確認（8トラッカー）
- [ ] SlimeVR ServerでOSC出力有効化（ポート6969）
- [ ] `connection_check` でHEALTH: GOOD確認
- [ ] `python -m osc_tracking.main` で起動確認

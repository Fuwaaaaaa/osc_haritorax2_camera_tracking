# E2Eテストチェックリスト（実機テスト）

リリース前に実機で確認するシナリオ。
全項目PASSでリリース基準達成。

## 必要機材

- HaritoraX2（充電済み）
- Webカメラ x 2（USB接続済み）
- SlimeTora（インストール済み）
- SlimeVR Server（インストール済み）
- Windows PC（VRChat推奨だがなくてもOK）

## 事前準備

- [ ] SlimeToraでHaritoraX2にBLE接続
- [ ] SlimeVR ServerでSlimeToraからのデータを確認
- [ ] SlimeVR ServerのOSC出力をポート6969に設定
- [ ] `python -m osc_tracking.tools.connection_check` で接続確認 → HEALTH: GOOD

## テストシナリオ

### 0. ベンチマーク（アーキテクチャ判定）
- [ ] `python -m osc_tracking.tools.benchmark --cam1 0 --cam2 1 --duration 60` を実行
- [ ] p99レイテンシが表示されること
- [ ] 判定結果: PASS (p99 < 40ms) / WARN (40-50ms) / FAIL (> 50ms)
- [ ] FAILの場合: ONNX Runtime移行またはシングルカメラモードを検討

### 0.5. セットアップウィザード
- [ ] `python -m osc_tracking.tools.setup_wizard` を実行
- [ ] Step 1: MediaPipeモデル検出またはダウンロードが成功すること
- [ ] Step 2: 2台のカメラが「OK」と表示されること
- [ ] Step 3: SlimeVR OSC接続が確認できること
- [ ] Step 4: ポート確認が完了すること
- [ ] Step 5-7: キャリブ→テスト→設定保存が完了すること
- [ ] 最終サマリーで7/7ステップ成功と表示されること

### 1. カメラキャリブレーション
- [ ] `python -m osc_tracking.tools.calibrate` を実行
- [ ] チェッカーボード（印刷済み）を両カメラ視野で複数角度から撮影
- [ ] キャリブレーション成功メッセージを確認
- [ ] `calibration_data/stereo_calib.npz` が生成されること

### 2. カメラプレビュー
- [ ] `python -m osc_tracking.tools.preview --cam1 0 --cam2 1` を実行
- [ ] 2台のカメラ映像が表示されること
- [ ] MediaPipeランドマーク（骨格線）がオーバーレイされること
- [ ] 自分の動きにランドマークが追従すること

### 3. 通常トラッキング（VISIBLE mode）
- [ ] `python -m osc_tracking.main` を実行
- [ ] ステータス表示が `[VISIBLE]` になること
- [ ] FPSが25以上であること
- [ ] IMU: OK、CAM: OK と表示されること
- [ ] http://localhost:8765 でダッシュボードが表示されること
- [ ] ダッシュボードの各ジョイント信頼度が70%以上であること

### 4. Partial Occlusion（片手隠し）
- [ ] 片手をカメラから隠す
- [ ] ステータスが `[PARTIAL_OCCLUSION]` に遷移すること
- [ ] 隠した手のジョイント信頼度がダッシュボードで低下すること
- [ ] 手を戻すと `[VISIBLE]` に復帰すること

### 5. Full Occlusion（布団モード）
- [ ] 布団を被り両カメラから完全に見えなくする
- [ ] ステータスが `[FULL_OCCLUSION]` に遷移すること
- [ ] **ヒステリシスバイパス**: 両カメラ同時ロスト時は即座に遷移すること
- [ ] 布団内でIMU回転が追従していること（HaritoraX2が動くとステータスに変化）
- [ ] 布団から出た瞬間にステータスが `[VISIBLE]` に復帰すること
- [ ] **ドリフト補正**: 布団から出た後、ヘディングのずれが即座に補正されること（これがキラー機能）

### 6. IMU切断/再接続
- [ ] SlimeToraを停止またはHaritoraX2の電源をOFF
- [ ] ステータスが `[IMU_DISCONNECTED]` に遷移すること（1秒以内）
- [ ] カメラのみでトラッキングが継続すること
- [ ] SlimeToraを再起動/HaritoraX2電源ON
- [ ] ステータスが `[VISIBLE]` に復帰すること
- [ ] 復帰時のスムーズリシンク（ジャンプしないこと）

### 7. 片カメラ劣化（カメラ別confidence検証）
- [ ] 片方のカメラを手で覆う
- [ ] ステータスが `[SINGLE_CAM_DEGRADED]` に遷移すること
- [ ] ダッシュボードで片側のカメラ信頼度のみが低下していること
- [ ] カメラを戻すと `[VISIBLE]` に復帰すること
- [ ] 逆のカメラを覆っても同様に検出されること

### 8. 布団モード（FUTON_MODE）
- [ ] 寝転がる（ピッチ角>60度を500ms維持）
- [ ] ステータスが `[FUTON_MODE]` に遷移すること
- [ ] FUTON_MODE中はカメラ補正が停止し、IMU回転のみで追従すること
- [ ] 起き上がる（ピッチ角<30度を500ms維持）
- [ ] ステータスが `[VISIBLE]` に復帰すること
- [ ] 一瞬だけ傾いてもモードが切り替わらないこと（ドウェルタイムによるフリッカー防止）

### 9. 両カメラ同時ロスト
- [ ] 両方のカメラを同時に手で覆う
- [ ] ステータスが即座に `[FULL_OCCLUSION]` に遷移すること（ヒステリシスなし）

### 10. 長時間安定性（30分テスト）
- [ ] 通常トラッキングで30分間放置
- [ ] FPSが安定していること（±5fps以内の変動）
- [ ] メモリ使用量が大幅に増加しないこと
- [ ] ドリフトが知覚できるレベルでないこと

### 11. VRChat OSC出力（オプション）
- [ ] VRChatを起動しOSC受信を有効化
- [ ] `python -m osc_tracking.main --vrchat-port 9000` を実行
- [ ] VRChatのアバターがフルボディトラッキングで動くこと
- [ ] 布団モード→復帰でアバターが正しく追従すること

## 結果記録

| # | シナリオ | 結果 | 備考 |
|---|---------|------|------|
| 0 | ベンチマーク | PASS/WARN/FAIL | p99: ___ms |
| 0.5 | セットアップウィザード | PASS/FAIL | ___/7ステップ |
| 1 | キャリブレーション | PASS/FAIL | |
| 2 | カメラプレビュー | PASS/FAIL | |
| 3 | VISIBLE mode | PASS/FAIL | FPS: ___ |
| 4 | Partial Occlusion | PASS/FAIL | |
| 5 | Full Occlusion + ドリフト補正 | PASS/FAIL | |
| 6 | IMU切断/再接続 | PASS/FAIL | |
| 7 | 片カメラ劣化 + カメラ別confidence | PASS/FAIL | |
| 8 | 布団モード（FUTON_MODE） | PASS/FAIL | |
| 9 | 両カメラ同時ロスト | PASS/FAIL | |
| 10 | 30分安定性 | PASS/FAIL | |
| 11 | VRChat出力 | PASS/FAIL | |

**リリース基準: シナリオ0, 1-9がPASS（0.5, 10, 11はベストエフォート）**

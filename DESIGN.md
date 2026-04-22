# Design System — OSC Tracking

## Product Context
- **What this is:** OSC対応IMUトラッカー + デュアルWebカメラのセンサーフュージョンによるVRフルボディトラッキングミドルウェア。HaritoraX2 が最初の対応デバイス
- **Who it's for:** VRフルボディトラッキングユーザー（HaritoraX2 / SlimeVR / Tundra 等）、VRChatコミュニティ、日本のVRコミュニティ
- **Space/industry:** VR body tracking, IMU sensor fusion
- **Project type:** デスクトップツール（Webダッシュボード + システムトレイ + CLI）

## Aesthetic Direction
- **Direction:** Retro-Futuristic + Industrial
- **Decoration level:** intentional（微妙なグリッドライン、端末風アクセント）
- **Mood:** SFコクピットの計器類。冷たいが信頼感がある。技術的だが威圧的ではない。データが主役。
- **Reference sites:** SlimeVR Server (差別化対象), Driver4VR

## Typography
- **Display/Hero:** Cabinet Grotesk 700/800 — 太く幾何学的。SF感と可読性のバランス
- **Body:** Geist 400/500/600 — Vercel製。技術プロダクトに最適な現代的sans-serif
- **UI/Labels:** Geist（bodyと同じ）
- **Data/Tables:** JetBrains Mono 400/500 — tabular-nums対応。端末感を演出
- **Code:** JetBrains Mono
- **Loading:** Google Fonts CDN
  - `https://fonts.googleapis.com/css2?family=Cabinet+Grotesk:wght@700;800`
  - `https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700`
  - Geist: `https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700`
- **Scale:**
  - 3xl: 3rem (48px) — ページタイトル
  - 2xl: 1.5rem (24px) — セクション見出し
  - xl: 1.1rem (17.6px) — サブ見出し
  - lg: 1rem (16px) — 本文
  - md: 0.85rem (13.6px) — UI ラベル、ボタン
  - sm: 0.75rem (12px) — キャプション、タイムスタンプ
  - xs: 0.7rem (11.2px) — バッジ、ステータスラベル

## Color
- **Approach:** restrained（1アクセント + ニュートラル + セマンティック）
- **Accent:** `#06b6d4` (Cyan 500) — SFコクピット感。SlimeVR (#6366f1 indigo) と差別化
- **Accent dim:** `#0891b2` (Cyan 600) — hover/pressed
- **Accent glow:** `rgba(6, 182, 212, 0.15)` — focus ring, subtle highlight
- **Neutrals (cool gray with blue undertone):**
  - Base: `#0a0a0f` — 最深背景
  - Surface: `#12121a` — カード、パネル
  - Elevated: `#1a1a26` — ヘッダー、ポップアップ
  - Hover: `#22222e` — インタラクティブ要素のhover
  - Border: `#2a2a38` — 境界線
  - Text primary: `#e8e8ed`
  - Text secondary: `#9898a8`
  - Text muted: `#5a5a6e`
- **Semantic:**
  - Success: `#22c55e` (Green 500) — GOOD, VISIBLE, connected
  - Warning: `#eab308` (Yellow 500) — WARN, PARTIAL_OCCLUSION, degraded
  - Error: `#ef4444` (Red 500) — ERROR, FULL_OCCLUSION, disconnected
  - Info: `#06b6d4` (= accent) — neutral info messages
- **Dark mode:** これがデフォルトかつ唯一のモード。VRユーザーは暗い部屋で使用

## Spacing
- **Base unit:** 4px
- **Density:** comfortable
- **Scale:**
  - 2xs: 2px
  - xs: 4px
  - sm: 8px
  - md: 16px
  - lg: 24px
  - xl: 32px
  - 2xl: 48px
  - 3xl: 64px

## Layout
- **Approach:** grid-disciplined（データ密度が高いモニタリングツール）
- **Grid:** stat cards は 3カラム、joint list は 1カラム
- **Max content width:** 960px（ダッシュボード）、800px（設定パネル）
- **Border radius:**
  - sm: 4px — input、small badges
  - md: 8px — cards、panels
  - lg: 12px — main containers

## Motion
- **Approach:** minimal-functional
- **Easing:** enter(ease-out), exit(ease-in), move(ease-in-out)
- **Duration:**
  - micro: 50-100ms — hover state
  - short: 150ms — toggle, button press
  - medium: 300ms — confidence bar transition, mode change
  - long: 500ms — page transition (rarely used)
- **Rule:** データ更新のtransitionのみ。装飾的なアニメーションは不要

## Decoration
- **Grid overlay:** `rgba(6, 182, 212, 0.03)` の48pxグリッド。body::before で固定
- **Glow effect:** アクセントカラーの `box-shadow: 0 0 8px` をステータスインジケータに
- **Border style:** solid 1px `var(--border)` が基本。アクセント時は `var(--border-accent)`

## Colorblind Accessibility
- 全てのカラーステータス表示にテキストラベルを併記
  - 緑 → "GOOD"、黄 → "WARN"、赤 → "LOW" / "ERROR"
  - トレイアイコンのツールチップにも "GOOD: VISIBLE (30 fps)" のようにテキスト含む
- font-variant-numeric: tabular-nums を数値表示に使用

## Decisions Log
| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-04-08 | Initial design system | Created by /design-consultation. Retro-Futuristic + Industrial direction. |
| 2026-04-08 | Purple → Cyan accent | SlimeVR (#6366f1) との差別化。SF/サイバー感の強化。 |
| 2026-04-08 | Cabinet Grotesk + Geist + JetBrains Mono | Display/body/data の3層構造。端末感とモダンさのバランス。 |
| 2026-04-08 | Dark-only mode | VRユーザーは暗い部屋で使用。ライトモードは不要。 |
| 2026-04-08 | Grid overlay decoration | 微妙なグリッドラインで「コクピット」感を演出。視認性を妨げない透明度。 |

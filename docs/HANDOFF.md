# 引き継ぎメモ（PPT2 Stats Overlay）

新しいセッションはまずこのファイルを読むこと。最終更新: 2026-10-29

## このプロジェクト
ぷよぷよテトリス2（PC版）の対戦画面を**画面認識だけ**で読み取り、APM / PPS / APP、消去・T-SPIN・REN・パフェ、
試合の開始/終了、開幕テンプレなどを HUD（デスクトップ上の透明ウインドウ）と OBS オーバーレイに表示するツール。

### 守ること（ユーザーとの約束）
- **返答は日本語**。短く、結論から。専門用語を減らす。
- **メモリ読み取り・入力フックは使わない**（ゲームの規約）。画面キャプチャのみ。
- **推測した数値を表示しない**。確認できないものは出さない（「--」や非表示にする）。
- 新しい認識は**録画（burst）で検証してから**入れる。ユーザーは実戦でも試してくれる。
- ユーザーは作業中に追加の依頼を送ってくることが多い。途中の作業も最後まで片付ける。

## 動かし方
- 起動: `start.bat`（ダブルクリック。サーバーとHUDが一緒に起動、黒い画面なし）。中身は `launch.py`。
- 終了: タスクトレイのアイコン →「終了」（サーバーも止まる）。
- 設定画面: 起動時に自動で開く／トレイアイコンをダブルクリック。設定は `config/overlay_settings.json`（gitに入れない。初期値は `scripts/config_store.py`）。
- サーバーログ: `logs/server.log`
- テスト: `.venv\Scripts\python.exe -m pytest tests -q`（現在 169 件すべて成功）
- 再起動の仕方（作業後）: data_server / launch.py の python プロセスを止めて `start.bat` を実行。
- git: リポジトリあり（main）。コミットには `Co-Authored-By: Claude ...` を付けてきた。

## 構成（主なファイル）
- `scripts/data_server.py` 認識サーバー（WebSocket 127.0.0.1:8765、10Hz で状態を配信、設定ファイルの変更も配信）
- `scripts/live_pipeline.py` 認識の中心。`MatchPipeline`（試合の区切り・ポーズ・時計）と `PlayerPipeline`（片側の消去/REN/パフェ/開幕など）
- `scripts/live_capture.py` ゲームウインドウの取り込み（mss、クライアント領域）
- `scripts/capture_profile.py` 解像度対応（16:9、0.5〜3倍）
- `scripts/banner_detect.py` テンプレ照合（TETRIS / T-SPIN / B2B / PERFECT CLEAR）。画像は `assets/templates/`
- `scripts/flash_clear_detector.py` 消去の白い光と段数
- `scripts/queue_tracker.py` NEXT の動きで設置数（PPS・REN途切れ）
- `scripts/match_boundary.py` 勝利「やった!」と「ゴー!」
- `scripts/gameplay_gate.py` 試合画面かどうか（NEXT ラベル）とポーズ（NEXT が空）
- `scripts/board_read.py` 盤面。`board_is_clear` は明るいマスだけ数える（ステージの背景絵対策）
- `scripts/opener_detect.py` + `scripts/fumen.py` + `assets/openers.json` 開幕テンプレ判定
- `scripts/i18n.py` 英語の文言（イベント・エラー）
- `hud/overlay.py` HUD（5デザイン: band/pop/gauge/text/versus、試合時間、イベント履歴、試合結果まとめ、開幕ポップアップ、ドラッグ位置調整）
- `hud/settings_window.py` 設定画面（日本語/英語）
- `obs/overlay.html` OBS ブラウザソース用（HUD と同じ配置・設定）
- `tools/validation/` 録画での検証・プレビュー用スクリプト（下記）

## 検証用の録画（gitに入っていない: `debug_frames/`）
`debug_frames/burst*` は 約10fps の連番画像（ファイル名 `f_NNNN_tT.png`）。
- `burst`（ポーズ48秒を含む）、`burst2`（1→2→3→4段消し）、`burst_ren`（12連続消し）、`burst_break`（REN途切れ）、
  `burst_boundary`（試合の区切り4回・TETRISパフェ・合掌TSD・りねパフェ(左凸)を含む）、`burst_pc`（2段パフェ・パフェ積み）
- 再生して結果を見る: `tools/validation/validate_burst_*.py`（`.venv\Scripts\python.exe tools\validation\validate_burst_boundary.py`）
- サイズ違いの検証: `tools/validation/size_check.py burst_boundary 1920 1080`
- 開幕判定の瞬間の画像を保存: `tools/validation/opener_frames.py burst_pc`
- 新しく録画: `scripts\capture_burst.py 300 burst_名前`（秒数、フォルダ名）
- `debug_frames/` 直下の調査用画像は約14GB たまっている。**消す許可はまだもらっていない**（burst系は残すこと）。
- 調査用画像の保存は設定 `debug.save_frames`（配布向け初期値は off、このPCでは on・1回の起動で最大2000枚）。

## これまでに確定した主な仕様（詳しくはコードのコメント）
- 試合開始は「ゴー!」が消えた瞬間。ただし直前4秒以内に両方の盤面が空（明るいマスなし）だった場合のみ（セット終了演出の誤検出対策）。
- 起動直後は試合が確認できるまで数えない（メニュー画面での誤カウント対策）。
- ポーズ中は数値と時計を止める。
- 消去はフラッシュの段数で確定し、バナー（TETRIS/T-SPIN）は同じ段数のフラッシュがある時だけ採用。
- パフェはバナー検出→直前の消去を10段に置き換え。
- 開幕判定: 試合開始から12秒 or 10個設置まで毎フレーム、盤面下部がwikiの形と完全一致＋すぐ上2段が空なら確定。
  形は テトリステンプレ整理Wiki の各テンプレページの「タグ」（テト譜）。今は 迷走砲 / 合掌TSD / パフェ積み(中あけ・端あけ) / りねパフェ(右凸・左凸・Oホールド・T土台)。
  表示名は `display`（短い名前）。追加はそのページのタグのテト譜を `assets/openers.json` に足すだけ（tests/test_opener.py が重複や1マスずれを検査）。
- HUD・設定画面・調査用ウインドウは `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)` で認識の取り込みに映らない。
  **他のウインドウがゲームに重なると誤認識する**（PPS が数えられなかった実例あり）。

## 未完了・次にやること
1. **開幕テンプレの表示位置の決定待ち**。案の画像: `docs/opener_position_ideas.png`
   - A 盤面の上に大きく（数秒） / B HOLDの下に小さく / C 名前の帯の上（ずっと） / D 上中央に両者まとめて（ずっと）
   - こちらのおすすめは A＋C。決まったら HUD（`OpenerPopup` と `_place` 内の配置）と OBS を合わせて実装。
2. **OBS 側の開幕表示がまだ古いまま**：HUD は「4秒のポップアップ」に変えたが、`obs/overlay.html` はまだ統計の上に小さい行（`.opener` / VSバーの `.vop`）を常に出している。位置決定後に HUD と同じ見た目に作り直す。
3. **Switch版・他の端末への対応（OBS上だけでも可）**：方針案はユーザーに説明済み、返事待ち。
   - 案: OBS の仮想カメラでキャプチャーボードの映像だけを出し、サーバーが `cv2.VideoCapture` で読む（または OBS のウインドウプロジェクターを窓キャプチャ）。HUDは使わず OBS 表示のみ。
   - 要確認: キャプチャーボードの有無、OBS のバージョン。キャプチャーボード経由の色・画質で認識が変わるので Switch の録画で検証が必要。
4. 配布準備の残り: exe 化（PyInstaller 等）、説明書、英語版ゲームの「やった!」対応（録画が必要）、フルスクリーン/1080p実機の確認。
5. 細かい既知の点: HOLD が空の時の最初のHOLDで NEXT が進み、1個多く数える（PPS がわずかに多め）。
6. 実戦で未確認: パフェ積み(端あけ)、りねパフェの判定、APP と試合結果まとめの実戦表示。

## ユーザーへの連絡でよく使うこと
- 録画を頼むとき: 「録画して」と言ってもらえれば `capture_burst.py` で始める。
- 画像を見せるときは SendUserFile（リモート操作中のことがある）。

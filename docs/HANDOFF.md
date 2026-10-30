# 引き継ぎメモ（PPT2 Stats Overlay）

新しいセッションはまずこのファイルを読むこと。最終更新: 2026-10-30

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
- テスト: `.venv\Scripts\python.exe -m pytest tests -q`（現在 192 件すべて成功）
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
  `burst_boundary`（試合の区切り4回・TETRISパフェ・合掌TSD・りねパフェ(左凸)を含む）、`burst_pc`（2段パフェ・パフェ積み）、
  `burst_hold`（新しい試合の最初のHOLD使用を両サイド含む。HOLD誤カウント修正の検証に使用）
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
1. 開幕テンプレの表示は設定 `display.opener_display` で4種類から選べるようにした（HUD・OBS・設定画面すべて対応済み）:
   board=A 盤面の上に大きく4秒 / hold=B HOLDの下 / namebar=C スコアと名前の帯の間 / top=D 上中央に両者。案の画像: `docs/opener_position_ideas.png`
   実戦での見た目はまだユーザー未確認。
2. **Switch版・他の端末への対応（OBS上だけでも可）**：方針案はユーザーに説明済み、返事待ち。
   - 案: OBS の仮想カメラでキャプチャーボードの映像だけを出し、サーバーが `cv2.VideoCapture` で読む（または OBS のウインドウプロジェクターを窓キャプチャ）。HUDは使わず OBS 表示のみ。
   - 要確認: キャプチャーボードの有無、OBS のバージョン。キャプチャーボード経由の色・画質で認識が変わるので Switch の録画で検証が必要。
3. 配布準備の残り: exe 化（PyInstaller 等）、説明書（フルスクリーン非対応を明記）、英語版ゲームの「やった!」対応（録画が必要）、1080p実機の確認。
4. ~~HOLD が空の時の最初のHOLDで NEXT が進み、1個多く数える~~ → 修正済み（`scripts/hold_tracker.py` 新規、`live_pipeline.py` の `PlayerPipeline._discard_hold_advance`）。
   HOLD枠の塗りつぶし判定で「空→埋まった」瞬間を検出し、その瞬間と重なるNEXT進みを1個だけ取り消す（PPS・REN途切れ判定の両方に影響していた）。
   `burst_hold` の実録画で検証済み（左右とも狙った1個だけ減ることを確認、テストは `tests/test_hold_tracker.py` / `tests/test_hold_pps_fix.py`）。実戦での最終確認はまだ。
   HOLDが「一度も空に見えていない」（途中から認識開始）場合は何もしない（誤って本物の設置を消していた不具合を修正済み）。
   **試合開始直後の1個目も誤カウントしていた**（ゴー!が消えて0.16〜0.27秒で必ずNEXTが1つ進む＝最初のミノの出現。burst_boundaryの4試合×両側すべて）
   → `NextQueueTracker(discard_first_shift=True)` で最初の1回だけ数えない。ゴー!で試合開始した時だけ有効（起動直後・ウインドウサイズ変更・ゴー!が見えない時の代替経路では無効）。
5. 実戦で未確認: パフェ積み(端あけ)、りねパフェの判定、APP と試合結果まとめの実戦表示。
6. 文字の設定: `display.text_weight`（normal / bold、初期値 bold）と `display.text_outline`（文字に黒い縁、初期値 on）。
   フォント（Yu Gothic UI）は Bold までしかなく 800/900 を指定しても変わらなかったので、bold は「同じ色の縁取り（文字サイズの5%）」で太らせる。
   「とても太い」はユーザーが不要とのことで削除。縁は黒・文字サイズの10%（紺だと帯や試合結果の箱の色と同じで見えなかった）。HUD は `hud/overlay.py` の `TEXT_WEIGHT_PRESETS`/`set_text_style`、
   OBS は `--fw-*` 変数と `body.outlined`、設定画面に「文字の太さ」「文字に縁をつける」。
   ミニゲージ(gauge)の文字（ラベルと数値）を盤面側の80の範囲に寄せ、始まりを帯(band)と揃えた（ユーザー要望）。ゲージのバーは元の長さ(104)のまま（`GAUGE_TEXT_W`）。
   数値の幅を固定（APM 888.8 / PPS・APP 8.88 ぶん、`VALUE_TEMPLATES`・OBSは `.v-*` の min-width）して、数値が変わってもラベルが動かないようにした。
   ポップ(pop)のフォントをゲームに寄せる件: M PLUS Rounded 1c / Mochiy Pop One を比較したが、ユーザーは「今のままでいい」。変更なし。
   帯のグラデーションを濃くする案は試したが、ユーザーが元のほうが良いとのことで戻した。
7. **フルスクリーンは非対応（調査済み・ユーザー了承済み）**。フルスクリーンを検出したら
   「フルスクリーンでは認識できません (ゲームをウインドウモードにしてください)」を返す（`live_capture.FULLSCREEN_REASON`、HUD/OBSに表示）。
   調べたこと（2026-10-30、2560x1440）: ゲームの窓は画面全体・タイトルなし・最前面固定、解像度は変わらない。
   - mss / PrintWindow は真っ黒（明るさ0）。Desktop Duplication（dxcam）はほぼ毎回「アクセス喪失」で、試合画面は一度も取れず。
   - ゲームの上に窓を出すと（フォーカスを奪わなくても）ゲームがフルスクリーンから外れて最小化される。透過クリック素通しのHUDは重なり順では上でも描画されない。
   - 抜け道はゲーム描画への割り込み（Discordオーバーレイ/OBSゲームキャプチャ方式）だけで、プロジェクトの約束で不可。dxcam は入れて試したあと削除済み。
   - ついでに入れたもの: ウインドウサイズが変わっても0.5秒続くまで使わない（`live_capture.SizeSettler`）。一瞬のサイズぶれで試合の数値がリセットされていたため。

## 今後やりたいこと（ユーザーのリスト、2026-10-30。順番は未定）
ユーザーの言葉のまま＋確認した内容と必要なもの。
1. **T-SPIN Mini の実装** — バナーのテンプレ画像が要る → T-SPIN Mini が出る場面の録画が必要。
2. **開幕テンプレを全部** — テトリステンプレ整理Wiki の全テンプレのタグ（テト譜）を `assets/openers.json` に追加。数が多いので重複・似た形の確認（tests/test_opener.py）が重要。
3. **他言語** = 英語版のぷよテト2に対応（表示の言語ではなく、ゲーム側が英語のとき）。「やった!」「ゴー!」等のテンプレが英語表記で違うはず → 英語版での録画が必要（配布準備の「英語版ゲームの『やった!』対応」と同じ件）。
4. ~~**縁あり（文字に縁をつける）を初期値に**~~ → 済（`DISPLAY_DEFAULTS["text_outline"] = True`、OBS の DEFAULTS も）。
5. **キャラ選択後から表示、ホームに戻ったら非表示**（常に表示する設定項目も追加） — キャラ選択画面・ホーム画面の判定が必要 → それぞれの画面の録画が必要（キャラ選択は 2026-10-30 の調査で1枚取れている）。
6. ~~**開幕テンプレ名のカッコ部分はいらない**~~ → 済（`opener_detect.screen_name` が（）/() 部分を外す。openers.json の名前はWikiのまま）。
7. **たいぷよ（相手がぷよ）や自分がぷよを使う時は非表示** — ぷよ側の盤面の判定が必要 → ぷよを使った試合の録画が必要。
8. ~~**試合結果の数値や文字は中央揃えに**~~ → 済（両者の列を幅の20%/80%を中心に中央揃え。HUD `SummaryBlock.COL_X`、OBS は3列グリッド）。
9. **試合結果の背景などをかっこよく** — デザイン案を作って見てもらう。
10. **デザイン「ネコ」** = 猫の実写素材を使ったネタデザイン。ライン消去のたびに猫の鳴き声が鳴る。
    → 写真・音声は使ってよいライセンスの素材が必要（フリー素材の候補を探してユーザーに確認）。音を鳴らす仕組みは HUD/OBS に新規。

## ユーザーへの連絡でよく使うこと
- 録画を頼むとき: 「録画して」と言ってもらえれば `capture_burst.py` で始める。
- 画像を見せるときは SendUserFile（リモート操作中のことがある）。

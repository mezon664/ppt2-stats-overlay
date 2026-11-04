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
- テスト: `.venv\Scripts\python.exe -m pytest tests -q`（現在 218 件すべて成功）
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
  `burst_hold`（新しい試合の最初のHOLD使用を両サイド含む。HOLD誤カウント修正の検証に使用）、`burst_tsm`（T-SPIN Mini：ライン消去あり2回・なし1回、左。後半はポーズ画面）
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
6. 文字の設定: `display.text_weight`（設定画面のスライダーで 0〜100、初期値 65＝以前の「太い」。0〜30 は Regular を少し太らせ、30〜100 は Bold をさらに太らせる: HUD `weight_style`／OBS `weightStyle`。古い "normal"/"bold" は 30/65 として読む）と `display.text_outline`（文字に黒い縁、初期値 on）。
   フォント（Yu Gothic UI）は Bold までしかなく 800/900 を指定しても変わらなかったので、bold は「同じ色の縁取り（文字サイズの5%）」で太らせる。
   「とても太い」はユーザーが不要とのことで削除。縁は黒・文字サイズの10%（紺だと帯や試合結果の箱の色と同じで見えなかった）。HUD は `hud/overlay.py` の `TEXT_WEIGHT_PRESETS`/`set_text_style`、
   OBS は `--fw-*` 変数と `body.outlined`、設定画面に「文字の太さ」「文字に縁をつける」。
   ミニゲージ(gauge)の文字（ラベルと数値）を盤面側の86の範囲に寄せた（帯(band)の文字の始まりより少し左。ユーザー要望で80→86）。ゲージのバーは元の長さ(104)のまま（`GAUGE_TEXT_W`）。
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

## 開幕名の表示時間
- どの位置（盤面の上/HOLDの下/名前の帯/上の中央）でも4秒で消える（ユーザー要望）。出るとき0.25秒・消えるとき1.2秒のなめらかなフェード（`popup_alpha`）。
  HUD は状態受信からの経過を足して約60fpsで更新、OBS は CSS の opacity transition でつなぐ。

## 見た目のカスタマイズ（2026-10-30）
- デザイン「シンプル（四角）」(`style: simple`)：数値・イベント・試合時間・試合結果・開幕名を角なしの単色の四角で。
- 追加デザイン7種（2026-10-30。22案の見本からユーザーが選んだ。アーケード・電光掲示板は試作したが不要とのことで外した）:
  `frame`「カラー枠」（枠線が各プレイヤーの色／共通部品は文字色。最初は光る「ネオン」だったが、光は不要・名前を変えてとのことで変更。古い設定の `neon` は `frame` として読む: `config_store.STYLE_RENAMES`）、`slash`（行ごとの斜めの箱を階段状に）、`hex`（六角形のハチの巣。横は最大2列で、それ以上は下に伸びる: `hex_cells`）、
  `meter`（一番上の数値を円弧メーター、残りはその下に文字。横幅を帯くらいに抑えるため下に並べる）、`tower`（数値ごとの縦ゲージ）、`minimal`（背景なし・数字の下に線。線がこのデザインの「背景」扱い: 濃さは背景の濃さ、色は専用の `line_color`（初期値は白、部品ごとにも設定可）。設定画面ではミニマル線のとき「背景の色」の行が「背景（線）の色」になり line_color を変える）、
  `trend`（数値ごとに直近1分の推移の折れ線。1秒に1回記録、試合時間が戻ったら＝新しい試合で消す。HUD は `StatBlock.history`、OBS は `recordHistory`）。
  HUD は `hud/overlay.py` の `NEW_STYLES` / `FRAMES`（他の部品の箱の種類）/ `paint_frame` / `StatBlock._paint_new`、OBS は `.st-<名前>` と `body.style-<名前>` の CSS。
  新デザインの数値は盤面から 6px（基準）離す（`NEW_STYLE_GAP`。盤面のふちに張り付いて「右にずれている」と言われた）。
  設定画面のデザイン一覧はシンプルな順（`settings_window.STYLE_ORDER`）: 文字だけ→ミニマル線→シンプル→帯→カラー枠→スラッシュ→ポップ→ミニゲージ→推移グラフ→縦メーター→円形メーター→六角形→中央VSバー。
  六角形・縦メーターは表示する数値が多いと横に長くなる。
- 色: `display.bg_color` / `text_color`（#rrggbb）。ラベル・イベント・ポップの時計・縁取りの色はこの2色から混ぜて作る（HUD `set_colors`、OBS `setColors`）。
  背景の初期値は黒 `#000000`（2026-10-30 ユーザー指定。以前は紺 `#0c163c`）。
- 開幕名（テンプレ名）だけ文字を少し細く: 太さの上乗せを他の文字の0.4倍（HUD `OPENER_NAME_THICKEN`、OBS `.oname` の text-stroke）。
  「文字に縁」の縁は文字が明るければ黒、暗ければ白（暗い文字に黒い縁でつぶれたため）。プレイヤー色（青・赤）の部分は変えない。
- フォント: `display.font_family`（初期値 Meiryo＝ユーザー指定、空＝Windows の標準 Yu Gothic UI）、ファイルから読み込むと `assets/user_fonts/` にコピーして `font_file` に記録（gitには入れない）。
  OBS は `../assets/user_fonts/...` を FontFace で読む。`font_file` は `user_fonts/<名前>.(ttf|otf|ttc)` 以外は受け付けない。
- 帯・ミニゲージの試合時間・試合結果は角なしの四角（グラデーションは試したがユーザー判断で四角に）。
- APM/PPS/APP は表のように揃える（ラベル左端・数値右端、`StatBlock._columns`、OBS は `alignStatColumns`）。

- 設定画面はタブ4つ（デザイン / 表示 / 位置 / OBSに映す）。開くとデザインタブ。デザインは見本付きカード（HUDと同じ描画で今の色・フォント・項目を反映、`render_style_preview`）。
  OBSタブ: 手順、overlay.html の場所のコピー、ブラウザで確認。`hud/settings_window.py`。
- 表示する数値: `display.stat_items`（並び順つき。apm/pps/app/attack/pieces/ren/b2b）。旧 show_apm/pps/app は読み込み時に引き継ぐ。
  attack=送った段数、pieces=置いたミノ数、ren=今のREN、b2b=B2Bが続いた回数（ストリーク-1、0は「--」）。サーバーのスナップショットに追加済み。
  数値の箱はラベルと数値の最大幅に合わせて広がる（`StatBlock._needed_width`）。
- ラベルの文言: `display.labels`（例 {"apm": "火力/分"}、12文字まで）。
- プレイヤー色: `display.player_color_left/right`（文字用の淡い色は自動）。
- 設定画面ではマウスホイールで値が変わらない（プルダウン・数値欄・スライダーの上でもページのスクロールだけ。`SettingsWindow.eventFilter`）。
- 設定画面の色（背景・文字）には「元に戻す」: 全体なら初期値へ、部品なら全体と同じに戻す。部品の状態表示（この部品だけ／全体と同じ）はユーザーの希望で削除。「全体」で値を変えると、その項目の部品ごとの値も消えて全部の部品に効く（部品に残った黒の背景が優先されて「全体で色が変わらない」と言われた）。ボタンは「全体をこの色に合わせる」1つだけ（ユーザー指定）: 選んでいる部分の色（背景・文字・ミニマル線の線）を全体の色にして、全部の部分の個別の色を消す。大きさと背景の濃さはそのまま。「全体」を選んでいるときは押せない。
- 部品ごとの設定: `display.parts.{stats,clock,events,summary,opener}` に scale / background_opacity / bg_color / text_color。
  書いていない値は全体の値に従う（`config_store.part_value`）。設定画面の「対象」で全体／部品を選ぶ。HUD は部品ごとに描く直前に色を切り替え（`use_colors`）、OBS は要素ごとに CSS 変数。
- プリセット: 設定ファイルの `presets`（言語以外の見た目一式）。書き出しは `{"format": "ppt2-stats-overlay-preset", ...}` の JSON。

## 試合の区切り
- 画面が暗転（64x36に縮めた平均の明るさ < 2）したら数値と試合結果を消す（`MatchPipeline._blackout_reset`）。暗転は試合の区切りごとに毎回起きる（全録画で確認）。
- 「ゴー!」を取りこぼして8秒の予備判定で始まったときは、待っていた間の「ゴー!」の場所の画像を `debug_frames/go_miss_t*.png` に保存し、ログにオレンジ量を出す。
  2026-10-30 19:18 に実戦で1回取りこぼし（原因未特定）。次に起きたらこの画像で調べる。

## 今後やりたいこと（ユーザーのリスト、2026-10-30。順番は未定）
ユーザーの言葉のまま＋確認した内容と必要なもの。
1. ~~**T-SPIN Mini の実装**~~ → 済（2026-10-30、録画 `burst_tsm`）。バナーは2種類: ライン消去なし「Mini T-SPIN」、あり「Mini T-SPIN Single」。
   - 判定: 左の紺タブの黄色い「Mini」（`t_tspin_mini_word.png`）。出始めた瞬間に小さい「Single」（`t_tspin_mini_single.png`）が 0.5 以上ならライン消去あり。
     実測: Mini 0.76〜0.96（本物4回、うち1回は burst_boundary の2P CPU）／それ以外の全録画で最高0.52。Single はあり0.64〜0.88／なし0.33〜0.36。
   - ライン消去あり = `tspin_mini`（表示「T-SPIN Mini Single」、攻撃0段・B2B対象、1段の光が必要）。なし = 攻撃でもクリアでもない、イベント履歴に「T-SPIN Mini」だけ出す（`mini_no_line_events`）。
   - 実戦（2026-10-30 19:10頃、ユーザー操作）: Mini Single 4回（うち2回はB2Bで+1）、ライン消去なし1回を認識。誤って捨てたバナーなし。
   - 注意: 盤面の一番上の段を消したとき（burst_boundary 右 t=107.5、負け直前）、光の段数を2段と測り、Miniバナーが段数不一致で捨てられた。光の測り方の既知の弱点（Mini に限らない）。
2. ~~**開幕テンプレを全部**~~ → 済（2026-10-31、v0.2.0）。テトリステンプレ整理Wiki のテンプレ一覧の全1455開幕・4409形（`tools/opener_import/`、経緯は `docs/opener_import_progress.md`）。
   - 1巡目で段を消す開幕（タグに埋まった行がある 1269 形）は、ゲームでは埋まった行がすぐ消えるので、「T を入れる直前の盤面」で判定（`opener_detect._before_the_t_spin`）。消えたあとの残りは14マス以上のときだけ使い、置いた数が足りるまで待つ（`MIN_LEFTOVER_CELLS`、`PLACEMENT_SLACK`）。
   - 形はおよそ1万8千の盤面になるので、表引き（`OpenerIndex`）。同じ盤面が複数の開幕にあるときは名前2つまで＋「ほか」（`shown_name`）。
   - Wiki は Cloudflare で curl 不可（回避はしない）。内蔵ブラウザで開いてページ内の fetch で集めた。データを作り直すときも同じやり方で。
3. **他言語** = 英語版のぷよテト2に対応（表示の言語ではなく、ゲーム側が英語のとき）。「やった!」「ゴー!」等のテンプレが英語表記で違うはず → 英語版での録画が必要（配布準備の「英語版ゲームの『やった!』対応」と同じ件）。
4. ~~**縁あり（文字に縁をつける）を初期値に**~~ → 済（`DISPLAY_DEFAULTS["text_outline"] = True`、OBS の DEFAULTS も）。
5. ~~**キャラ選択後から表示、ホームに戻ったら非表示**~~ → 済（2026-10-31）。画面の種類を個別に見分けるのではなく「試合画面（NEXT 枠が見える／ポーズ中）が出ている間だけ表示」にした: 試合画面が `live_pipeline.MATCH_SCREEN_HIDE_S`（3秒）見えなければ隠す（試合と試合の間に試合画面から外れるのは全録画で最長0.65秒）。snapshot の `match_screen`、設定 `display.always_show`（「ホーム画面やメニューでも常に表示する」、初期値オフ）。HUD `_away_from_match`、OBS `body.away`。
6. ~~**開幕テンプレ名のカッコ部分はいらない**~~ → 済（`opener_detect.screen_name` が（）/() 部分を外す。openers.json の名前はWikiのまま）。
7. ~~**たいぷよ（相手がぷよ）や自分がぷよを使う時は非表示**~~ → 済（2026-10-30、録画 `burst_vs_puyo`=右ぷよ、`burst_self_puyo`=左ぷよ）。
   - 判定: ぷよ側には NEXT の枠（ラベル）がない。試合画面での一致度: ぷよ側 0.24〜0.37／テトリス側 0.86〜0.97（ただしテトリス側が一瞬 0.19 に落ちたことが1回）。
     → 2秒続けて見えなければ「ぷよ」、1秒続けて見えれば「テトリス」に戻す（`live_pipeline.PUYO_LABEL_MISSING_S` / `TETRIS_LABEL_SEEN_S`）。試合画面以外ではリセット。
   - ぷよ側は認識そのものを止める（ぷよの連鎖の光や落下を数えない）。切り替わったときその側は数え直し。snapshot の各側に `"puyo": true`。
   - HUD・OBS とも、ぷよ側の数値・イベント履歴・開幕名を隠し、試合結果のその列は空欄、versus は数字なし＋バーは中立。
   - 録画での確認: ぷよ側だけ正しく判定（12.8秒・8.5秒時点）、テトリス同士の録画8本では一度も誤判定なし。テスト画像 `tests/fixtures/puyo_left.jpg` / `puyo_right.jpg`。
   - 両方ぷよ（ぷよ同士）は NEXT 枠が両方ないので試合画面と判定されず、何も数えない（表示は止まったまま）。
8. ~~**試合結果の数値や文字は中央揃えに**~~ → 済（両者の列を幅の20%/80%を中心に中央揃え。HUD `SummaryBlock.COL_X`、OBS は3列グリッド）。
9. **試合結果の背景などをかっこよく** — デザイン案を作って見てもらう。
10. **デザイン「ネコ」** = 猫の実写素材を使ったネタデザイン。ライン消去のたびに猫の鳴き声が鳴る。
    → 写真・音声は使ってよいライセンスの素材が必要（フリー素材の候補を探してユーザーに確認）。音を鳴らす仕組みは HUD/OBS に新規。

## 2026-10-31 後半に入れたもの
- **開幕名の表示「猫」**（`opener_display: "cat"`、設定では「E 猫」）: ユーザー提供のグリーンバック動画（10秒・猫が右から来て白い紙を掲げて左へ去る）を `tools/cat/make_cat.py` で切り抜き → `assets/cat/`（24fps・半分の大きさ・WebP 207枚 1.3MB。12fps はカクカクするとのことで全コマに、`cat.json` に各コマの位置と紙の四隅、OBS 用に同じものを `cat.js`）。
  1P は左右反転して左の画面端から、2P は右端から、盤面の上に重なる（ユーザー「猫が盤面の邪魔をしてくる」）。紙に開幕名（英語表示なら英語名）を、紙の四隅に合わせて変形して描く。紙を持つ時間は「開幕テンプレ名を出しておく時間」、長いときは持っているコマを往復。
  HUD `CatPopup`/`cat_pos`、OBS `catTick`（canvas）。
  なめらかさ（ユーザー「もっと滑らかに」）: ①猫は出始めからこの PC の時計だけで進める（サーバーから毎秒10回来る経過時間は数十ms揺れ、追いかけるとカクついた。0.35秒以上ずれたときだけ合わせ直す）②コマとコマの間を重みづけで混ぜて60fps相当に（Qt の加算モードは不透明度を無視して半透明になったので numpy で合成、OBS は canvas の lighter）③拡大済みのコマを「猫」を選んだ時点で全部用意（初回の拡大で引っかかった）④HUD のタイマーを PreciseTimer に。1回の描画は約7.5ms。紙の検出が抜けた4コマは前後から補間。動画はユーザーが Gemini で生成したもの（配布可）。
- **オン／オフ**（ユーザー希望、わかりやすい場所に）: 設定画面のいちばん上の大きなボタン（緑＝オン）と、トレイ右クリックメニューのいちばん上「表示する（オン／オフ）」。
  `display.enabled`。オフで HUD・OBS とも全部消える（認識は動いたまま）。トレイのアイコンもオフで灰色。
  トレイからの切り替えは、設定画面を一度も開いていなくても保存済みの設定を読んでから on/off だけ変える（`SettingsWindow.set_enabled`。開いていない画面の初期値で上書きしないため）。
- **英語の開幕名**（表示言語が English のとき）: ユーザーのルール「Hard Drop の名前、なければ日本語」。1455 中 410 に英語名（Hard Drop の綴り 78、Wiki ページ冒頭の「日本語 / English」の英語名 332）、残りは日本語のまま。
  `assets/openers.json` の `name_en`（`tools/opener_import/build_openers.py`、元データ `wiki_heads.json`・`harddrop.json`）。検出は日英両方を持つ（`OpenerDetector.name_en`、snapshot `opener_en`、イベント `text_en`）。
  Hard Drop の日本語での一致は「そのページに日本語が4語以下」のときだけ（たくさん並べたページで SDパフェ→Mini Triple Double のような誤対応が出たため）。
- **Python なしで動く完全版**: `tools/build_full.py` → `dist/PPTetrics-full-v<版>.zip`（約150MB、Windows の組み込み用 Python と必要なライブラリを `runtime/` に同梱）。`start.bat` は runtime → .venv → PATH の順に使う。
  更新はふだん小さいコードだけの zip（runtime はそのまま。`updater.PRESERVE`）。requirements.txt を変えたら `version.RUNTIME` を上げる → 古い runtime の人には「完全版を入れ直して」と出す（`updater.NEEDS_FULL`）。
  組み込み Python は スクリプトの置き場所を import パスに入れないので、`data_server.py` は自分で入れる。完全版を空のフォルダに展開して、同梱 Python だけでサーバーが起動し実画面を読めることを確認済み。
  リリースの自動作業は `build_full.py` を実行するので、公開すると完全版も一緒に出る。
- **配布 zip の不具合を修正**: v0.1.0 の zip に `config/attack_table.json` が入っておらず、起動できなかった（`make_release.INCLUDE` に追加。zip を展開して起動まで試すテスト `test_the_release_zip_runs`）。
- ぷよ相手でポーズすると試合終了になる件: ぷよ側がいるときは「両方の盤面が空」で終了にしない（ぷよ側はいつも空に見えるため、ポーズ直前にテトリス側が一瞬消えるだけで終了していた）。

## アプリ名: PPTetrics（2026-10-31 ユーザー決定）
- 表示名（トレイ・設定画面・OBS ページ・README）は PPTetrics。README と設定の「アップデート」タブに「非公式のファンツール。セガ・The Tetris Company とは無関係」と、開幕データの出典（テトリステンプレ整理Wiki）を明記。
  「Tetrics」は Tetris に綴りが近く、The Tetris Company が問題にしやすいことはユーザーに伝えたうえでの決定。
- 中身の識別子（フォルダ名、プリセット形式 `ppt2-stats-overlay-preset`、GitHub リポジトリ名）は変えていない。リリースの zip は `PPTetrics-v<版>.zip` と、v0.1.0 の更新確認が探す旧名 `ppt2-stats-overlay-v<版>.zip` の2つ（`tools/make_release.py`）。
- GitHub のリポジトリ名を変えるなら（ユーザーが GitHub の Settings で）、旧名からは自動で転送されるので古い版の更新確認も届く。そのあと `updater.UPDATE_REPO` と git remote を新しい名前に。
- 開幕データ（v0.2.0 の全テンプレ）の公開は、Wiki 管理者さんへの相談（ユーザーが X の DM で送る）の返事待ち。

## 2026-10-31 に入れたもの・残り
- **勝手にポーズされる件**: このゲームはフォーカスを失うと自動でポーズする。アプリ起動時に HUD・設定画面がフォーカスを奪っていた（作業中の再起動のたびに起きていた）。
  HUD は `WindowDoesNotAcceptFocus`＋`WA_ShowWithoutActivating`＋`WS_EX_NOACTIVATE`。設定画面は「ゲームが起動中なら開かず、トレイ通知で場所を知らせる」（WA_ShowWithoutActivating だけでは設定画面がフォーカスを取った）。
  ゲーム起動中の再起動で前面ウィンドウが変わらないことを確認済み。再起動は start.bat ではなく `.venv\Scripts\pythonw.exe launch.py` を CREATE_NO_WINDOW で（cmd の黒い窓を出さない）。
- ぷよ判定を 2秒→0.5秒に（`PUYO_LABEL_MISSING_S`。テトリス側で NEXT 枠が消えた最長は全録画で0.08秒）。録画でぷよ側は出てから約0.5秒で非表示、テトリス録画で誤判定なし。
- 初期デザインはミニゲージ（`style: gauge`）。PIECE の初期ラベルは PIECES。イベント履歴の件数は最大10。
- 試合結果に出す項目を選べる（`display.summary_items`、`config_store.SUMMARY_ITEMS` の順で固定）。T-SPIN は全部まとめて／Single／Double／Triple／Mini を別々に選べる（`match_stats` に `tspin_single` などを追加）。
- 縦メーターを詰めた（細く短いバー、列の間隔2）。スラッシュと六角形の背景は背景の濃さどおりに（以前は最低0.7/0.6で下げても変わらなかった）。
- **ライン消去なしの T-SPIN**（録画 `burst_tspin_zero`、左で2回）: バナーは短い帯に「T-SPIN」だけ。テンプレ `t_tspin_zero_word.png`（「-SPIN」の文字）。
  実測: 本物 0.94〜0.97（最初のフェードイン1枚だけ0.65）、他の全録画の全フレーム（Single/Double/Triple/Mini のバナー含む）で最高0.66 → 入りのしきい値 0.85。
  さらに Single/Double/Triple/Mini の文字が 0.6 未満のときだけ（`TSPIN_ZERO_WORD_MAX`）。攻撃にもクリアにも数えず、イベント履歴に「T-SPIN」とだけ出す（`tspin_no_line_events`）。右側の実物はまだ録画にない。
- **イベント表示の遅れを短縮**: 普通のライン消去は「後から T-SPIN/TETRIS のバナーが来ないか」1.5秒待っていた。全録画の実測（バナーが光の何秒後に来るか）: T-SPIN S/D/T 0.08〜0.26秒、Mini 0.14/0.95秒、TETRIS 0.55〜1.14秒。
  → 光で測った段数ごとに待ち時間を変えた（`FLASH_GRACE_BY_LINES_S`: 1段 1.1秒、2〜3段 0.6秒）。4段は TETRIS しかないので光の時点ですぐ数え、後から来る TETRIS バナーは数えない（`BannerTracker.expect_banner`）。
  4段の光25回すべてが TETRIS バナーと対応していたのを確認済み。おまけで burst2 の最後、バナーが出なかった本物の TETRIS（点数 17818→21442）を拾えるようになった。待っている古い消去があるときは順番を守る（REN の数え順）。
- 開幕テンプレ名を出しておく時間を選べる（`display.opener_seconds`: 2/3/4/6/8/10秒・試合が終わるまで(0)、初期4秒）。
- 1P だけ／2P だけ表示（`display.players`: both/left/right）。表示しない側はぷよ側と同じ扱い（`mark_hidden_sides`、OBS は render で `hidden`）。
- **お邪魔を受けても開幕テンプレを判定**: 盤面の一番下から「ちょうど1マスだけ空いていて、ブロックが全部灰色」の行をお邪魔として数え、その上に形がぴったり乗っているかを見る（`opener_detect.garbage_rows`）。
  お邪魔のブロックは彩度0、ミノは120〜255 → `GARBAGE_SAT_MAX` 30。全録画の全フレーム・両側で「お邪魔を除いたら開幕に一致」は0件（誤検知なし）。本物（お邪魔の上の開幕）の録画はまだない → 合成した画像でテスト。
- **アップデートの仕組み**（ユーザー希望。開発は続けるので、新しい版を出し続ける前提）:
  - 版番号は `scripts/version.py` の VERSION（今 0.1.0）。配布先は GitHub `mezon664/ppt2-stats-overlay` のリリース（`updater.UPDATE_REPO`）。リポジトリは作成済み（Public）。
  - アプリ: 起動時に最新リリースを確認（設定「アップデート」タブ、`update.check_on_start`）→ 新しければトレイ通知 → 「更新して再起動」で zip を GitHub からだけダウンロード（`ALLOWED_HOSTS`）→ 展開（外へ出るパスは拒否）→ PowerShell の後始末スクリプトがアプリ終了を待って robocopy で上書き（削除はしない）→ 再起動。勝手には更新しない。
    ユーザーのもの（`config/overlay_settings.json`、`assets/user_fonts/`、logs、debug_frames など）は zip に入れず、入っていても消してから写す（`PRESERVE`）。
  - **新しい版の出し方**: `scripts/version.py` を上げる → コミット → タグ `v<版>` を push。`.github/workflows/release.yml` が版とタグの一致確認・テスト・`tools/make_release.py` で zip 作成・リリース公開まで自動。変更点は `docs/release-notes/v<版>.md` に書いておくとリリースの説明になる（アプリの「この版の変更点」に出る）。
  - コミットの作者アドレスは GitHub の非公開用 `325367006+mezon664@users.noreply.github.com`（このリポジトリの git config に設定済み。過去9件も書き換え済み）。Gmail を絶対に載せないこと。
  - 利用者向け `README.md`、`requirements.txt` を追加。Python なしで動く形（exe 化など）はまだ。
  - **2026-10-31 公開済み**: https://github.com/mezon664/ppt2-stats-overlay （アカウント名は mezon664 に変更済み。旧名・Windows のユーザー名入りのパスは履歴からも消してから公開）。
    v0.1.0 のリリースを自動作業で作成済み（zip 約283KB）。アプリの更新確認で v0.1.0 が見え、古い版なら更新を出す・ダウンロード・展開まで実物で確認済み。
    push のサインインは Git Credential Manager に保存済み（ユーザーがブラウザでサインイン）。

## ユーザーへの連絡でよく使うこと
- 録画を頼むとき: 「録画して」と言ってもらえれば `capture_burst.py` で始める。
- 画像を見せるときは SendUserFile（リモート操作中のことがある）。

### 二重起動防止（2026-10-31）
- デスクトップのショートカット `PPTetrics.lnk`（`.venv\Scripts\pythonw.exe launch.py`、アイコン `assets/app.ico`）。
- `hud/overlay.py` の `already_running()`: QLocalServer `PPTetrics-hud` が既にあれば "show" を送って即終了 → 起動中のアプリが設定画面を開く。

### 猫の切り抜き改善（2026-10-31）
- `tools/cat/make_cat.py` `key()`: 緑の度合いで柔らかい透明度、縁の色を背景から逆算（緑/ピンクのフチ除去）、原寸でキーしてから半分に縮小。素材 1.3→1.8 MB。
- 紙の判定の閾値を 0.75→0.72（縁が削れた分）。紙を掲げる区間は 21–182（旧 22–182）。
- 帰りのコマ飛び修正: 紙の表示時間に合わせるのは「猫が止まっている区間」(`still_start`–`still_end`、make_cat.py が自動検出、今は 56–174) だけ。短ければ早送り、長ければ奇数回往復して still_end で終わる → 退場は撮影どおり連続。`cat_pos`（HUD）/`catPos`（OBS）同じ計算。`CAT_MIN_STILL_S = 0.5`。

### 英語版のぷよテト2（2026-10-31、録画 debug_frames/burst_english）
- 確認できたもの（変更なしで動く）: 「Ready?」「START!」（色で GO! 判定）、T-SPIN Double/Triple/Mini Single、BACK-to-BACK、PERFECT CLEAR、テトリス（フラッシュ）、NEXT 表示（ぷよ側判定・試合画面判定）、メインメニューで非表示。
- 直したもの: 勝利の「Yeah!」→ `assets/templates/t_yeah_live.png`（match_boundary.py で「やった!」と並べて照合。英語 0.88–1.00、日本語の録画では最大 0.45）。これがないと試合終了が約 3 秒遅れ、その間に偽のテトリスが 1 回出ていた。
- REN は英語だと「1 Combo」表示で、REN バッジの見本は合わない。ただし REN 数は連続消去から数えているので表示は正しい（録画で 1REN・2REN を確認）。
- 追加録画 debug_frames/burst_english2 で確認（変更なしで正しい）: T-SPIN Single、ライン消去なし T-SPIN、相手がぷよ（右をぷよと判定して非表示）、TSD→テトリスの 1REN（画面の「1 Combo」と一致）、「Yeah!」で試合終了。

### 2026-10-31 追加
- 英語の REN → Combo: イベント「2 Combo」「Combo ended (no clear)」、結果「Max combo」、項目「Current combo」、英語のときの標準ラベル `COMBO`（`DEFAULT_LABELS_EN`、HUD/OBS/設定画面）。日本語は REN のまま。
- 開幕テンプレ名の言語 `display.opener_language`: auto（表示の言語と同じ・初期値）/ ja / en。`config_store.opener_language(d)`。バッジ・猫・試合結果・イベント履歴（開幕の行は prefix が表示言語、名前がこの設定）。イベントに `opener_en` を追加。
- 猫の紙: 名前は 1 行、40px（紙 200x140 基準）まで縮めて、それより長いと紙の外へはみ出す（ユーザー了承）。
- 開幕名の位置: 1P/2P 別 `opener_left_offset_x/y`, `opener_right_offset_x/y`。設定「位置」タブの対象に「1P のテンプレ名」「2P のテンプレ名」、位置調整モードで見本の名前（猫なら紙を持った猫）が出てドラッグ可。上中央にまとめる表示は 1P の値で動く。
- 英語の開幕名も（…）部分を外す（`load_english` で `screen_name`、同じ英語名は1つにまとめる）。
- 英語版で相手がぷよのときのポーズ: メニューが自分の NEXT 欄にかぶって「ミノあり」と読んでいた → ポーズメニューの「Start Over」「Quit Game」ボタンの見本（`t_pause_en_*.png`、gameplay_gate `PAUSE_WINDOW`）。ポーズ中 1.0、他の全録画 0.46 以下。日本語版で相手ぷよのポーズは録画がなく未確認。
- 位置: 数値も 1P/2P 別（`stats_left/right_offset_*`、`offset_x/y` が両方）。テンプレ名は `opener_offset_*`（両方）＋ 1P/2P。設定の「動かすもの」はプルダウン 9 項目、「ドラッグで 1P と 2P を別々に動かす」(`drag_each_side`)。位置調整中は枠の上でホイール → その部分の大きさ（`wheel_resize`、`part_resized` → 設定画面が保存）。
- 表示オンのボタン: オン中に試合画面の外で隠れているときは「◐ … クリックで表示」→ `force_show`（次に試合画面になったら自動で解除）。トレイでオンにしたときも、その場で見えるようにする。
- 相手がぷよのとき、テトリス側の盤面の枠が外側に 12px 広い（白線 1P x=173 / 2P x=778、通常 186 / 791）→ 数値が枠に乗って右にずれて見えた。`VS_PUYO_SHIFT_X`（左下モードのみ -12、HUD/OBS）。あわせて左下の基準を 186/790 → 184/788（テトリス同士でも白線の 1 列目にかかっていた。実画面で線の手前 2px に止まるのを確認）。
- 中央: 盤面の白線（185.9 / 439.9 / 791.3 / 1045.4、3 録画で一致）の中点は 615.6。`CLOCK_CENTER_X` / `OPENER_TOP_CENTER_X` を 617 → 615.6（試合時間・試合結果・数値の対戦表示・上中央の開幕名、HUD/OBS）。2P 左下の基準 788 → 789.2 で 1P/2P とも白線まで 2px。初回コミットからの値で、急にずれたのではなく、ぷよ相手で 12px かぶって目立った。

### アイコン（2026-10-31）
- ユーザーが選んだ案: 左下に紫の T ミノ、右上に棒グラフ（白・青・赤）、暗い角丸。`hud/overlay.py` `draw_app_icon` / `icon_image` / `make_tray_icon`（16〜256px を描き分け、オフ時は灰色）。`app.setWindowIcon` で設定画面のタイトルバー・タスクバーも同じ。
- `assets/app.ico` は `python tools/make_icon.py` で同じ絵から書き出す（PNG 入り ico、9 サイズ）。デスクトップのショートカットはこれを参照。
- 猫の動画を差し替え（2026-10-31、ユーザーの 2 本目 `cattt.mov`、DNxHR・1920x1080・黒背景。透明度付きだが ffmpeg 9 が DNxHR のアルファを読めない）。`make_cat.py` が四隅の色で黒背景／緑背景を自動判別し、黒は `key_black`（明るさで透明度、輪郭の内側の小さい穴（目・鼻、1500px 以下）だけ塗りつぶし — 足のあいだ等の大きいすき間まで塗ると黒いかたまりになった、灰色の床の影は背景扱い）。出力幅は常に 640。動画が猫の退場途中で終わるので、最後の 12 コマをくり返して画面外まで歩かせる（`finish_walking_off`、画像は増やさず位置だけ）。244 コマ、紙 39–206、止まる区間 62–171。
- 猫の動画をさらに差し替え（ユーザーの 3 本目 `catcat.mov`、緑背景・1920x1080・225 コマ）。緑は動画ごとに `calibrate_green`（最初のコマで緑の色と度合いを測り、いちばん暗い緑より 6 下を基準に。この動画は 26–81。固定値 30–95 だと背景がうっすら残る）。239 コマ（最後 14 コマは歩き去り）、紙 39–201、止まる区間 67–166。
- 「Start Over」でのやり直し（2026-10-31）: カウントダウン中は NEXT が空で画面が読めない区間が GO! の約 2.4 秒前まで続く（全 13 録画）。1 秒以上読めなかった直後の GO! を、凍結中でも試合中でも試合開始として扱う（`GO_CLOSED_MIN_S`、`_last_closed_span`）。以前は凍結中しか GO! を見ず、盤面が空に見えた直後しか受け付けなかったので、やり直しで開幕を見逃していた。
- 猫を 1.25 倍（`CAT_SCALE`）、置き方を「クリップの真ん中を盤面の真ん中（`CAT_CENTER_X` 320 / 912）」に変更（大きくしても盤面の中央に立つ）。HUD/OBS。
- HUD の Python 例外で PyQt6 がアプリごと落ちていた（Windows ログ: Qt6Core fail-fast 0xc0000409、猫の表示が出た直後に 2 回）。`log_errors()` で `sys.excepthook` を差し替え → 落ちずに `logs/hud.log` に記録。ネイティブの落ち方は `logs/hud_crash.log`。原因の例外自体はオフスクリーン・試験用 HUD・録画再生では再現せず未特定 → 次に起きたら hud.log を見る。
- ライセンス GPL-3.0（`LICENSE`、配布 zip にも入る。PyQt6 が GPL のため）。
- v0.2.0 を公開（2026-10-31 16:45、GitHub Actions 成功。full 版をダウンロードして Python なしで読み込めることを確認）。
- 紙の文字を小さく（`PAPER_MAX_PX` 54→40、1 行の最小 30、2 行の最小 22。HUD/OBS）。
- OBS のページは読み込んだ時点のまま（猫を入れる前のページで猫が出なかった）→ サーバーが `page_rev`（overlay.html と cat.js の更新時刻）を送り、ページは変わったら自動で読み込み直す。v0.2.1 として用意。
- 猫の画質: 素材を幅 1280 で保存（`OUT_W`、WebP 品質 88、約 4.5MB）、`CAT_SCALE` 0.625（表示の大きさは同じ）。幅 640 を 1.8 倍に引き伸ばしてぼやけていた。v0.2.1 に含める。
- HUD が落ちた原因が判明（hud.log）: サーバーの opener_age_s が認識直後にわずかにマイナス → cat_pos の frac がマイナス → 合成の重みが負で OverflowError（以前は PyQt6 が強制終了）。`cat_pos` で age を 0 未満にしない＋重みを 0〜1 に制限（HUD/OBS）。
- 相手がぷよのとき GO! を無視していた（ぷよの盤面は「空」と読めない → 「両方の盤面が空」が成り立たない）。GO! 用の「空」はテトリス側の盤面だけで見る（`tetris_sides`）。
- 紙の検出: 傾いた紙を「回転した長方形への埋まり具合 ≥0.77 ＋縦横比 1.0〜1.8」で判定（前は直立の外接枠で、持ち上げ途中の紙が白紙だった）。紙 33–201。

### 2026-11-04（Codex が v0.2.2〜v0.2.5 を公開したあと、ユーザーからの報告への対応 → v0.2.6）
- Codex の主な変更: 日本語・スペース入りフォルダで画像を読めない問題（`image_io.read_image`）、ランチャーとサーバーの起動・終了の管理（`server_control`、制御ポート 8766）、暗転時に試合結果を消さない、GO! を見逃したときの開始を早く（次の試合ならキュー 1 回の動きで開始）、更新確認の代替フィード。
- 認識を基準の幅（1232）に縮めてから行う（`live_capture.shrink_for_recognition`）。2155 幅のユーザーで T-SPIN・消去の見逃し、REN のずれ。13 録画で 12 本は結果が同一、1 本は縮めた方が正しい（T-SPIN Mini Single を拾う）。1756 幅で 1 コマ 49ms → 22ms。
- 試合結果を表示中（勝利バナー〜次の試合の準備）はぷよ判定を変えない（`_result_held`）。セット終了のセリフでキャラが NEXT を隠し「ぷよ」と誤判定 → その側を作り直して数値が消えていた。
- サーバーは起動したランチャーが消えたら自分で終わる（`--parent-pid`、`watch_parent`）。異常終了時に pythonw.exe が残り、次の起動がその古いサーバーにつながって何も表示されなかった。
- 診断ファイル: サーバーが 5 秒ごとに `logs/last_seen.jpg`（認識に見えている画面＋状態）と `logs/last_status.txt` を書く（`scripts/diagnostic.py`）。トレイの「うまく認識しないとき：診断ファイルを開く」で logs フォルダ。
- .venv から起動すると Codex のランチャーが「別のサーバー」と判断して起動を止めていた（venv の pythonw は中継役→本体の 2 段で pid が違う）→ `server_control.server_pid_is_ours`。配布版（同梱 Python）には影響なし。
- 暗転は仕様どおり「数値も試合結果も消す」に戻した（v0.2.2 の Codex 変更で、試合後の暗転では結果を残していた）。`BLACK_MEAN` 2 → 8（暗転は 0〜0.4 が 1〜2 コマだけで、遅い環境は通り過ぎる。前後のフェードが 2〜12、試合・メニュー画面は最低 18）。
- 開幕名のポップアップの軽量化: 猫は 2 コマの合成を numpy から QPainter（下を不透明、上を途中の不透明度）に、描き直しを猫と紙のまわりだけ（`_area`）、コマの読み込み・縮小は 15ms ごとに 2 コマずつ裏で（`prepare`、`cat_image` で遅延読み込み）。板の表示は変化があるときだけ描き直す。2560 幅で猫 14.7 → 7.9ms、切り替え直後の停止 0.5〜0.9 秒 → 0.015 秒。

### 2026-11-04 後半（OBS を HUD と同じ見た目に・軽量化 → v0.2.6 に含める）
- OBS のページ（`obs/overlay.html`）を書き直し: HTML/CSS の箱ではなく、1 枚の canvas に HUD の各部品の `paintEvent` と `HudWindow._place` を同じ手順で移した（ユーザー: HUD と OBS の見た目の差をなくしたい。HUD の画面を画像で送る案は重いので不採用）。HUD 側を変えたら OBS 側の同じ関数も合わせる。
  - Qt は文字幅を 1 文字ずつ整数に丸めて並べる → ページも同じ（`charWidth` / `eachChar`）。丸めないと箱が 1〜2px 広かった。
  - ブラウザは文字をピクセルに合わせて太めに描く（ユーザー: OBS の文字が少し太くつぶれて見える）→ 部品ごとに 4 倍で描いて縮小（`SUPERSAMPLE`、2 倍では文字の量が HUD の約 1.15 倍）、さらに太らせる線を細く（太字: 0.4+4×THICKEN 倍、通常: 0.3 倍。文字の太さ 15/40/65/100 で HUD との差 ±6%）。1920 幅で 1 フレーム約 1.5ms。
  - 比べる道具: `python tools/validation/hud_vs_obs.py 出力フォルダ [デザイン...]`（同じ状態を HUD と Edge（画面なし）で描いて 1px ずつ比較、部品ごとに HUD｜OBS｜差（赤）の画像）。全 13 デザイン＋開幕表示 4 種で差 0.15〜0.4%（文字のふちだけ）。
  - 同じ状態が続くとき（メニュー・結果画面）は描き直さない。1 回の描画は約 1ms。
- 猫のメモリ: 2 人分の左右反転したコマ＋読み込んだ元画像を全部持っていた（1756 幅で +380MB、2560 幅で +655MB、ほかの表示に切り替えても残る）→ 縮小済みのコマ 1 組を 1P/2P で共有（1P は描くときに反転、`CatFrames` / `CAT_FRAMES`）、元画像は持たない、猫以外の表示にしたら手放す。+127MB / +253MB、切り替えると +11MB。
- サーバーの CPU:
  - OpenCV の並列処理をやめた（`cv2.setNumThreads(1)`、data_server.py）。1 コマの CPU 46 → 29ms（処理時間は 24 → 29ms で 15fps の 67ms に余裕）。13 録画で認識結果は完全一致。
  - 試合画面の外（`no_match_ui`）が 3 秒続いたら毎秒 5 回だけ読む（`IDLE_FPS` / `idle_period`）。メニューでも画面の取り込み（BitBlt 11ms＋縮小 4.5ms）だけで 1 コアの 28% 使っていた → 実機で 6〜14%。暗転はどれも試合画面から出た直後（13 録画）なので取りこぼさない。間引いた再生（188 コマ）でも結果は一致。
- HUD: サーバーから同じ状態が来たら何もしない（`_last_raw_state`）。メニュー中 3〜8% → 0.1〜0.2%。
- 試合中の残りの重さはバナーのテンプレート照合（1 コマ約 17 回）。半分の大きさでのふるい分けは、本物のバナーが 0.32 まで下がるので見送り。
- ぷよとの対戦中は試合時間を出さない（ユーザー: マージンタイムの進み具合が分かると片側が有利で公平でない）。`puyo_in_match`（本当にぷよの側があるとき。1P/2P のみ表示で隠した側は対象外）、`ClockBlock.set_hide_time`。状態・キャプチャの行は出す（何もなければ時計の箱ごと出さない）。位置調整中は出す。試合結果の見出しの時間は試合後なので残す。OBS も同じ（`clock.hideTime`）。
- HUD と OBS で別々にオン・オフ（ユーザー）: `display.show_on_hud` / `show_on_obs`（初期値 True）。`enabled` は両方まとめてのスイッチのまま。設定画面の大きなボタンの下にチェック 2 つ（オフ中は灰色）、トレイにも 2 項目（`set_shown_on`、保存済みの値に重ねて 1 項目だけ変える）。HUD は `show_on_hud` オフでも位置調整中は出す。
- 開幕の統計（ユーザー: 使用率を円グラフで、直近 N 試合の集計で自動更新／テンプレごとの勝率／対テトリス・対ぷよで分けて）:
  - 勝者: 「やった!/Yeah!」が出た側（`MatchBoundaryDetector.winner`、`last_yatta_side_conf`）→ サーバーの状態 `winner`。13 録画で勝った側 0.83 以上・反対側 0.45 以下、左勝ちを画像で確認。
  - 記録: HUD が凍結した瞬間（`_record_finished_match`）に `opener_stats.match_record` → `config/opener_history.json`（gitignore、直近 500 試合）。勝者のない終わり（途中でやめた・暗転で消えた）は数えない。
  - 集計: `opener_stats.tally(matches, N, 1P/2P/両方, 英語名, 相手 tetris/puyo/all)`。相手で絞ってから直近 N 試合。
  - 設定画面「試合の統計」: 対象（1P か 2P。合計はユーザーの希望で外した）・相手・直近 N（10/20/50/100/200/500 のボタン、`LAST_N_CHOICES`、`ui.opener_stats` に保存）、ドーナツ円グラフ（上位 7 色＋その他＋認識なし、ホバーで件数・勝率）、全テンプレの表、記録を消すボタン。HUD の `opener_recorded` で自動更新。
  - 平均（ユーザー: 直近の平均 APM・PPS も）: 記録に各側の `stats`（apm/pps/app と match_stats、`opener_stats.match_numbers`）、`opener_stats.averages` が同じ試合で平均（数値のない古い記録は除く）。タブ名は「試合の統計」に。
- OBS の背景の濃さ（ユーザー: 中間の濃さだけ HUD と違う）: OBS のブラウザソースは `SrgbDecompress` で色をリニアにしてから重ねる（Windows の HUD は sRGB のまま）→ 半透明の黒が OBS では薄い（濃さ 50% で HUD 45 / OBS 64）。ページの `rgba()` が `obsAlpha()` で透明度を補正（中間の灰色の背景で HUD と同じ結果になる値、黒は正確）。比較ツールも OBS の重ね方を再現（`over_bg_obs`）。
- 文字の縁の太さ: `display.text_outline_width`（文字の大きさの %、2〜30、初期 10）。HUD `set_text_style(..., width_pct)`、OBS も同じ。
- 設定画面の作り直し（ユーザーがモックアップ https://claude.ai/artifact/3Fzq4GAsrKc258NjxwAuv7 を承認）: `hud/ui_kit.py`（スタイル、`Card`・`Switch`・`Segmented`（QComboBox と同じ呼び方）・`SideNav`（QTabWidget と同じ呼び方）・メニューのアイコン）。ページはホーム（オン・オフ、一緒に起動）／表示する項目／見た目（デザイン・プリセットもここ）／位置／試合の統計／OBS／その他。値の読み書き（`values` / `_show_values`）は前のまま。
- ぷよテト2と一緒に起動（ユーザー、設定のホーム）: `scripts/autostart.py` が HKCU の Run に `scripts/game_watch.py` を登録（管理者権限なし）。見張りは 3 秒ごとに `PuyoPuyoTetris2.exe` を探し、ゲームが起動した瞬間に（アプリが動いていなければ）アプリを起動。1 回のゲームにつき 1 回だけ。二重に動かない（ミューテックス）。オフで登録を消して見張りを止める。
- レートの推移（ユーザー、録画 debug_frames/burst_rating、パズルリーグ 2 試合）: `scripts/rating.py`。
  - レートが出る画面: 対戦前の「まちうけ」（両者のカード、自分のカードに「You」。1P なら左、2P なら右）と、パズルリーグのメニュー（自分のカード、「レート」の横）。対戦後の画面には出ない。
  - 場所は 1320 幅の座標（`YOU`、`MENU`）を画面の幅で拡大縮小。「You」・メニューの「レート」をテンプレートで探し、その箱の数字を Windows の文字認識（`Windows.Media.Ocr`、winrt）で読む（2 値化して白地に黒、3 倍）。録画の数字に 3 と 9 が出てこなかったのでテンプレートでは全部の数字を作れなかった。61 コマ全部正しく読めた（2610→2615）。1 回約 67ms、試合画面の外で 1 秒に 1 回だけ（`data_server.read_rating`）。同じ値が 2 回続いたら採用、リーグの前回と違うときだけ `config/rating_history.json` に追加（リーグごと直近 1000）。
  - リーグ: まちうけ画面にリーグ名が無いので、最後に見たリーグのメニューのタイトル（左上、`assets/templates/rating_league_<league>.png`）で決める。タイトルを知らないリーグのメニューでは「不明」にして記録しない（前のリーグとして記録しないため）。同じリーグの前回と同じ値は記録しない（まちうけ→戻る→まちうけで二重にならない）、別リーグの同じ値は記録する（ユーザー）。4 リーグともテンプレートあり（debug_frames/burst_leagues: パズル 2618・ぷよぷよ 984・テトリス 2504・スキルバトル 985 を正しく記録。自分のリーグ 1.0、他リーグ 0.56 以下）。
  - 設定画面「レートの推移」: リーグ・期間（直近 20/50/100/200/すべて）、今・変化・最高・最低、折れ線（ホバーで値と日時）、3 秒ごとに読み直し。
  - requirements.txt に winrt-* を追加 → `RUNTIME = 2`（このあとの更新はフル版を取り直すよう案内される）。

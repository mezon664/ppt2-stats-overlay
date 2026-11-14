"""縛りプレイ: comments flowing across the game screen, Niconico style, as
your play goes (user's request): each kind of clear (T-SPIN by kind), the
opener, your APM / PPS / BtB / REN, the match time, the other player's good
moves, the start of a match, the win or the loss, and now and then all
through the set.

The server decides the comments (CommentStream, from the state it sends) and
sends the live ones as state["comments"]; the HUD and the OBS page only draw
them flowing right to left, each from its age, so both show the same ones.
display.challenge_comments: "off" / "few" / "normal" / "many".
docs/comments.md lists them all (python scripts/comments.py writes it).
"""
import random
import re

import midgame

FLOW_S = 6.0      # a comment takes this long to cross the screen
LANES = 11        # rows a comment can run in, over the screen's height
# no two comments in a row ever touch (user: in a crowd — a loss, a win — they
# ran into each other and read as one, "くやしいうわあああ"). Each comment
# crosses SCREEN_W + its width in FLOW_S (a longer one runs faster), so one
# behind another can catch it up: a row is only taken when the one before is
# fully in and won't be caught before it's gone. No row like that now: it
# waits up to WAIT_S for one, else it's left out.
SCREEN_W = 1232          # reference px (hud/challenge.py, obs/overlay.html)
COMMENT_PX = 34          # (challenge.COMMENT_PX)
LANE_GAP = 24            # px kept between two comments in a row
WAIT_S, WAIT_STEP_S = 2.0, 0.1
AMOUNT = {"few": 0.5, "normal": 1.0, "many": 1.8}

# what's said, per kind: (when, Japanese, English). {n}: a number, {name}: an opener's name
POOL = {
    "start": ("試合の始まり",
              ["きたああああ", "わこつ", "がんばれー", "はじまった", "うぽつ", "待ってた", "今日も見に来た",
               "いけるいける", "勝てるぞ", "期待",
                "初見です", "こんにちは", "手元カメラください",
             "{me}がんばれ", "{me}見に来た", "{rival}も強そう", "{me}今日も頼む", "{me}いけー"],
              ["here we go", "gl hf", "let's go", "hype", "good luck!", "it's starting",
             "go {me}!", "gl {me}", "{rival} looks strong"]),
    "tetris": ("自分の TETRIS",
               ["TETRIS!!!", "うおおおおお", "4段きた", "気持ちいいいい", "テトリスたすかる", "ナイステトリス",
                "きもちええ", "うまい", "さすが", "でかい",
                "天才やん",
             "{me}ナイス", "さすが{me}", "{me}テトリスうまい", "{me}のくせにやるな"],
               ["TETRIS!!!", "nice tetris", "clean", "so satisfying", "4 lines!", "wow",
             "nice {me}", "{me}!!"]),
    "tss": ("自分の T-SPIN Single",
            ["TSS!", "T-SPIN Single", "回った", "シングルでも偉い", "ナイスT", "細かい"],
            ["TSS!", "T-spin single", "nice T", "every bit counts"]),
    "tsd": ("自分の T-SPIN Double",
            ["TSD!!", "TSDきもちいい", "T職人", "回った", "これがTSD", "ナイスT", "美しい", "Tスピンたすかる",
                "紫のブロック頑張りすぎだろ", "紫のやつたまに液体みたいになるのなに？",
             "{me}うまい", "{me}のTスピン気持ちいい", "{me}のくせにやるな"],
            ["TSD!!", "clean TSD", "T-spin double!", "beautiful", "nice T",
             "clean, {me}"]),
    "tst": ("自分の T-SPIN Triple",
            ["TST!!!", "トリプルきたあああ", "6段!!", "えぐい", "TSTはずるい", "うますぎ", "神",
                "紫のブロック頑張りすぎだろ", "人間やめてる",
             "{me}天才か", "{me}えぐい", "{me}のくせにやるな",
             "どんだけテトリスに時間費やしたんや…", "テトリスやりこみすぎw"],
            ["TST!!!", "T-spin triple!!", "6 lines!!", "insane", "huge",
             "{me} is insane"]),
    "tsm": ("自分の T-SPIN Mini",
            ["ミニ", "Mini", "小技", "細かい", "器用"],
            ["mini", "small but nice", "tricky"]),
    "tsmd": ("自分の T-SPIN Mini Double",
             ["ミニダブル!?", "NEOだ", "TSMD", "レア技", "テクい", "なにそれ", "知ってる人だ"],
             ["mini double!?", "NEO!", "TSMD", "rare one", "technical"]),
    "tspin0": ("自分のライン消しなし T-SPIN",
               ["回しただけ", "T-SPIN(0)", "空振り", "仕込み?", "w"],
               ["just a spin", "T-spin zero", "setting up?"]),
    "pc": ("自分のパフェ",
           ["パフェ!!!", "神", "888888", "全消しきたあああ", "ファッ!?", "うますぎて草", "えぐい", "天才か",
            "パフェたすかる", "伝説",
                "天才やん", "人間やめてる", "上手すぎワロタ",
             "{me}天才", "{me}!!!!!", "{me}パフェうますぎ", "{me}のくせにやるな", "パフェきたあああああ", "うおおおおおおお", "全消し!!!", "きれいすぎる", "88888888", "8888", "神業", "鳥肌立った", "えぐすぎ", "これは天才", "盤面まっさら",
             "どんだけテトリスに時間費やしたんや…", "テトリスやりこみすぎw"],
           ["PERFECT CLEAR!!!", "insane", "8888888", "what", "genius", "legendary",
             "{me} PC!!", "{me} genius", "PERFECT CLEAR!!!", "88888", "clean board!!", "unreal"]),
    "ren": ("自分の 4REN 以上",
            ["{n}REN!!", "REN続くなあ", "連打連打", "止まらない", "まだ続く", "RENえぐい"],
            ["{n} combo!!", "combo keeps going", "can't stop", "still going"]),
    "ren_break": ("自分の長い REN（4REN 以上）が途切れたとき",
                  ["あー切れた", "惜しい", "おつかれREN", "よく続いた"],
                  ["combo over", "so close", "nice combo"]),
    "b2b": ("自分の BtB が 2・4・6…回続いたとき",
            ["BtB{n}", "BtB継続中", "つよい", "BtB切らさない", "安定してる", "BtB{n}えらい",
             "BTBやば", "無駄消し全然しないやん", "火力すげえ", "BtB途切れないな", "まだBtB続くの？", "無駄消しゼロ", "BtB{n}はえぐい", "丁寧すぎる", "BtB職人", "火力落ちないな", "ずっとBtB乗ってる",
             "どんだけテトリスに時間費やしたんや…", "テトリスやりこみすぎw"],
            ["B2B x{n}", "back to back", "so consistent", "strong",
             "B2B is crazy", "no wasted clears", "so much damage", "B2B x{n}, insane"]),
    "opener": ("自分の開幕テンプレが分かったとき",
               ["{name}だ!", "{name}きた", "{name}助かる", "テンプレ通り", "定石だ", "{name}好き", "開幕きれい",
                "{name}組んでる", ["このテンプレ何？", "↑{name}"]],
               ["{name}!", "it's {name}", "by the book", "clean opener", "{name} nice"]),
    "midgame": ("自分が途中テンプレ（STSD・DT砲・TDアタックなど 36 種類、assets/midgame_setups.json）を決めたとき",
                ["{name}きたあああああああ", "{name}きたああああああ", "{name}!!", "うおお{name}", "{name}決まった",
                 "きれいな{name}", "{name}かっこよすぎ", "出た{name}", "{name}うますぎ", ["このテンプレ何？", "↑{name}"], ["今の何？", "↑{name}"],
             "{name}うおおおおおおおお", "{name}きたあああああああああ", "うおおおおお{name}!!", "{name}決めたあああ", "出たあああ{name}", "{name}えぐいって", "{name}かっこよすぎる", "どんだけテトリスに時間費やしたんや…", "テトリスやりこみすぎw"],
                ["{name}!!", "{name} let's go", "clean {name}", "{name} landed", "here comes {name}"]),
    "rival_opener": ("相手の開幕テンプレが分かったとき",
                     ["相手は{name}", "相手も{name}か", "{name}対策", "相手の開幕はやい", ["このテンプレ何？", "↑{name}"]],
                     ["they went {name}", "{name} from them", "opener battle"]),
    "apm_high": ("自分の APM が普段の 1.25 倍以上のとき",
                 ["APM{n}!?", "火力やばい", "今日キレてる", "攻めてる", "火力高すぎ", "絶好調",
                "火力火力！", "火力の暴力", "勝ったな。風呂入ってくる", "APM{n}すげえ", "APM{n}やばすぎww",
             "どんだけテトリスに時間費やしたんや…", "テトリスやりこみすぎw"],
                 ["APM {n}!?", "so much attack", "on fire", "aggressive"]),
    "apm_low": ("自分の APM が普段の 6 割以下のとき（試合開始 40 秒後から）",
                ["落ち着いて", "まだいける", "ここから", "深呼吸", "がんばれ"],
                ["stay calm", "you got this", "from here"]),
    "pps_fast": ("自分の PPS が普段の 1.2 倍以上のとき",
                 ["{n}PPS はやい", "手はや", "指どうなってるの", "速すぎて見えない", "爆速",
                "はっや", "うっま", "つっよ", "へった", "はやwwwww", "なんでそんな急いでるんですか？", "PPS{n}すげえ", "PPS{n}やばすぎww"],
                 ["{n} PPS fast", "so fast", "speed!", "blink and you miss it"]),
    # the numbers as they are, now and then (a live audience reading the screen — user)
    "apm_now": ("自分の APM（普段の 9 割以上のとき、ときどき）",
                ["APM{n}", "今APM{n}", "APM{n}出てる", "APM{n}いいね", ["今APMいくつ？", "{n}"],
                 ["APMなんぼ？", "{n}出てる"], "{n}APMは普通に強い", "APM{n}維持してる", "APM{n}すげえ", "APM{n}やばすぎww"],
                ["APM {n}", "{n} APM", ["what's the APM?", "{n}"], "{n} APM is solid"]),
    "pps_now": ("自分の PPS（ときどき）",
                ["PPS{n}", "今PPS{n}", ["PPSいくつ？", "{n}"], "{n}PPS安定", "PPS{n}出てる", "手の速さ{n}PPS"],
                ["PPS {n}", "{n} PPS", ["PPS?", "{n}"]]),
    # a lot of attack sent in a short time (user: the room should get going)
    "burst": ("自分が短い間に大火力を送ったとき（6 秒で 10 ライン以上）",
              ["火力やばすぎ", "一瞬で{n}ライン", "{n}ライン一気に送った", "火力の暴力", "送りすぎ", "ラッシュきた",
               "止まらん", "容赦ない", "怒涛の攻め", "畳みかける", "相手の盤面えぐいことになってる", "相手かわいそう",
               "せり上がりやばい", "これは効く", "うおおおおおおお", "火力すげえ", "攻めっ気つよ", "殺意高すぎ",
               "やっばw", "つっよ", ["今何ライン送った？", "{n}"]],
              ["{n} lines in a flash", "what a rush", "relentless", "no mercy", "the pressure!!", "huge burst",
               "{n} lines just like that"]),
    "attack_mark": ("自分が送った火力が 20・40・60・80・100 ラインになったとき",
                    ["火力{n}ライン突破", "もう{n}ライン送ってる", "{n}ライン送った", "送った火力{n}",
                     "{n}ラインはえぐい", "相手の盤面に{n}ライン"],
                    ["{n} lines sent", "{n} lines of attack", "{n} lines already"]),
    "pieces_mark": ("自分が置いたミノが 100・200・300・500 個になったとき",
                    ["{n}ミノ目", "もう{n}ミノ置いた", "{n}ミノ突破", "{n}ミノおつ"],
                    ["piece {n}", "{n} pieces down"]),
    "spin_count": ("自分の T-SPIN が 3・5・10・15・20 回目のとき",
                   ["Tスピン{n}回目", "今試合Tスピン{n}回", "T-SPIN{n}回目きた", "Tスピン多いな", "Tスピン職人",
                    "Tスピン{n}回は多い"],
                   ["T-spin #{n}", "{n} T-spins already", "T-spin machine"]),
    "tetris_count": ("自分の TETRIS が 3・5・10 回目のとき",
                     ["{n}回目のテトリス", "テトリス{n}回目", "テトリス量産", "テトリス{n}本目", "今日テトリス多い"],
                     ["tetris #{n}", "{n} tetrises", "tetris factory"]),
    "b2b_break": ("自分の BtB（4 回以上）が途切れたとき",
                  ["BtB{n}で途切れた", "あーBtB切れた", "BtB{n}おつかれ", "BtB{n}は立派", "BtB惜しい",
                   "またBtB積もう"],
                  ["B2B x{n} over", "B2B broke", "nice B2B run"]),
    "app_high": ("自分の APP（1 ミノあたりの火力）が 0.6 以上のとき（試合開始 40 秒後から）",
                 ["APP{n}!?", "効率えぐい", "1ミノの火力高い", "APP{n}は強い", "無駄がない", "火力効率いい"],
                 ["APP {n}!?", "so efficient", "every piece counts"]),
    "apm_ahead": ("自分の APM が相手の 1.2 倍以上のとき",
                  ["火力で押してる", "火力勝ってる", "相手APM{n}なら勝てる", "火力差ある", "押せ押せ"],
                  ["out-attacking them", "more attack", "push push"]),
    "apm_behind": ("相手の APM が自分の 1.2 倍以上のとき",
                   ["相手APM{n}つよい", "火力負けてる", "相手も強い", "相手の火力やばい", "耐えて返そう"],
                   ["they're at {n} APM", "they hit hard", "hold on, hit back"]),
    "time": ("試合時間が 1・2・3・5 分になったとき",
             ["{n}分経過", "長期戦だ", "まだ続く", "体力勝負", "粘る", "{n}分たった",
                "これは熱い試合"],
             ["{n} min in", "long one", "still going", "endurance"]),
    "garbage_big": ("自分にお邪魔がまとめて来たとき（4 段以上）",
                    ["うわ、せり上がった", "痛い", "耐えて", "掘れ掘れ", "下穴そろってる", "ここから掘り", "大量に来た",
                     "まだ大丈夫"],
                    ["ouch", "that's a lot", "hang in there", "dig dig", "you can dig it"]),
    "pinch": ("自分の積みが高くなったとき（15 段以上）",
              ["やばいやばい", "天井近い", "死ぬな", "生きろ", "ギリギリ", "落ち着いて", "ここ耐えたら勝てる",
               "心臓に悪い",
             "{me}耐えて", "{me}生きろ", "{me}まだいける",
              "死ぬぞ!!", "あぶないあぶない", "お邪魔多すぎ", "耐えろおおお", "まだ死ぬな", "やばいって", "ギリギリすぎる", "上まで来てる", "うわあああ", "掘れ掘れ掘れ", "逃げてー", "ここから逆転ある？", "心臓バクバク", "ここから入れる保険ありますか？"],
              ["danger!", "so close to the top", "don't die", "survive", "hold on",
             "hang on {me}", "survive {me}",
              "oh no oh no", "so much garbage", "hold on!!", "dig dig dig", "almost topped out"]),
    "recover": ("ピンチ（15 段以上）から 9 段以下まで持ち直したとき",
                ["生き返った", "立て直した", "耐えた!!", "ここから逆転", "しぶとい", "粘り強い",
                "ゴキブリ並みの生命力"],
                ["back alive", "recovered", "survived!!", "comeback time", "tough"]),
    "quiet": ("自分が 10 秒以上ラインを消していないとき",
              ["静かだ", "嵐の前",
                "どこ見てプレイしてるんだろう…"],
              ["quiet...", "calm before the storm"]),
    "comeback": ("ピンチのあとに勝ったとき",
                 ["逆転勝ち!!", "危なかった",
             "{me}逆転!!", "{me}しぶとい"],
                 ["comeback win!!", "that was close",
             "{me} comeback!!"]),
    "rival": ("相手の TETRIS・T-SPIN・パフェ（少しだけ）",
              ["相手もうまい", "ひえっ", "やり返された", "相手つよ", "負けるな", "くるぞ",
             "{rival}もうまい", "{rival}やるな", "{rival}つよ"],
              ["the other one's good too", "uh oh", "they hit back", "watch out",
             "{rival} is good", "nice {rival}"]),
    "win": ("勝ったとき",
            ["GG", "GG", "GG", "gg", "888888888", "勝ったああああ", "うおおおおおおおおおおおおお", "つよすぎ", "おめでとう", "ナイス", "完勝", "かっこいい", "圧勝",
             "次も勝てる", "やったぜ", "上手すぎワロタ", "神",
             # (the 8s more than once: they come up more often — user: it's fine to have them several times)
             "8888", "88888", "8888888888", "８８８８８８", "88888888888888", "8888", "88888",
             "GG!!", "ないすうう", "おめ", "うおおおおお", "強すぎる", "最強", "優勝", "ｷﾀ━━━(ﾟ∀ﾟ)━━━!!", "神試合",
             "見てて楽しかった", "ナイスゲーム",
             "{me}つよすぎ", "{me}おめでとう", "{me}優勝", "{rival}もGG", "{me}最強", "{me}のくせにやるな"],
            ["GG", "GG", "GG", "gg", "88888888", "you won!!", "too strong", "congrats", "gg wp", "8888", "888888", "GG!!",
             "let's gooo", "W", "insane",
             "gg {me}!", "{me} wins!!", "gg {rival}"]),
    "lose": ("負けたとき",
             ["ドンマイ", "おつ", "次いける", "惜しい", "GG", "切り替えていこう", "どんまい", "悔しい", "次こそ",
              "あーあ", "m9(^Д^)ﾌﾟｷﾞｬｰ", "GG", "おつおつ", "いい試合だった", "8888", "惜しかった", "相手が強かった",
              "次いこう", "ドンマイドンマイ", "まだまだこれから",
             "{rival}つよい", "{me}どんまい", "次は勝てる{me}", "{rival}うまかった", "あああああああ",
             "うわあああ", "くやしいいい", "惜しいいいいい", "ドンマイ!!", "次次！", "ナイスファイト", "いい勝負だった", "あと少しだった", "今のは仕方ない", "めっちゃ惜しい", "ほぼ勝ってた", "熱かった", "おしいいい", "GG"],
             ["GG", "unlucky", "next one", "so close", "you'll get it",
             "gg {rival}", "unlucky {me}",
             "so close!!", "unlucky...", "nice fight", "next one!!", "gg wp", "almost had it"]),
    # the game paused mid-match (user: comments of its own): a few when it
    # stops, then these instead of the usual chatter while it stays paused
    "pause": ("試合中にポーズしたとき（ポーズ中もときどき）",
              ["ポーズ？", "一時停止", "トイレ？", "休憩タイム", "水分補給大事", "何かあった？", "インターホン鳴った？",
               "待ってる", "ゆっくりでいいよ", "作戦会議かな", "まさかの一時停止", "宅配便かな", "深呼吸",
               "手首休めて", "ストレッチしよ", "ポーズ長くね", "いってらっしゃい", "待機", "お茶いれてきな",
               "固まった？", "放置？", ["何があった？", "電話かな"], ["トイレ？", "たぶんそう"]],
              ["paused?", "bathroom break", "brb?", "take your time", "we'll wait", "hydrate", "stretch time",
               "still here"]),
    "resume": ("ポーズから戻ったとき",
               ["おかえり", "再開きた", "おかえりなさい", "待ってた", "さあ再開", "続きいこう", "おかえりー",
                "よし再開", "{me}おかえり"],
               ["welcome back", "we're back", "let's go", "back to it"]),
    "ambient": ("セットの間ずっと、ときどき",
                ["w", "www", "草", "がんばれー", "うまい", "つよい", "8888", "わかる", "いけるいける", "集中",
                 "すごい", "ナイス", "おお", "はやい", "見てる", "この人うまいな", "かっこいい", "きれい", "えらい",
                 "安定してる", "落ち着いて", "次も頼む",
                "これもう履歴書の特技欄にテトリスって書けるだろ", "ミスれ！", "お〜w", "置きミスしない方が強いですよ", "俺の知ってるテトリスじゃない", "寿司食べたい", "これは見応えある", "ぷよテトはいいぞ", "相手の盤面見ろ", "俺の方が上手い", "この人のプレイは見ていて安心感がある", "この速度でミスしないのが一番すごいと思う", "こういう何気ない積み方に実力が出るんだよな", "この盤面を見て何を考えてるのか聞いてみたい", "この人のテトリスは何時間見ていても飽きない", "積み木うまそう", "ヤムチャ視点", "頭の回転どうなってんだ", ["ブロックを積むのは簡単ですが人生を積み上げるのは難しい", "↑ は？"], "コントローラー何使ってますか？", "コメント読めよ", "黄色のブロックは回転しても形変わらないのか。かわいそう", "BGMいいね", "手の動きオモロ笑", "ゆうと見てるー？明日公園でマリカしよ", "もっとはやく積めよ", "くぁwせdrftgyふじこlp",
             "{me}の配信好き", "{me}今日調子いい？", "{rival}って誰？", "{me}がんばえー"],
                ["lol", "nice", "gg", "so fast", "watching", "clean", "pog", "let's go", "wow", "gl", "keep going",
             "love {me}'s streams", "who's {rival}?"]),
    "set_end": ("セットが終わったとき",
                ["おつかれさま", "GG", "楽しかった", "おつ", "また見に来る", "ナイスセット", "8888888", "おつおつ",
                 "いいセットだった", "いい試合だった", "両方うまい", "もう1セット", "名勝負",
                "乙カレー", "お茶ﾄﾞｿﾞ-(´･ω･)っ旦",
             "{me}おつ", "{rival}もおつ", "{me}おつかれさま"],
                ["GG", "good set", "that was fun", "gg wp", "see you", "88888",
             "gg {me}", "gg {rival}"]),
}
# how many for each (times the amount setting), and which come big
# (what happens in the game gets more of them than the chatter — user)
COUNT = {"start": 4, "tetris": 6, "tss": 4, "tsd": 6, "tst": 8, "tsm": 3, "tsmd": 5, "tspin0": 2, "pc": 12,
         "ren": 3, "ren_break": 2, "b2b": 4, "opener": 5, "rival_opener": 2, "apm_high": 3, "apm_low": 2,
         "pps_fast": 3, "time": 3, "rival": 2, "win": 10, "lose": 9, "midgame": 9, "ambient": 1, "set_end": 8,
         "garbage_big": 4, "pinch": 7, "recover": 4, "quiet": 2, "comeback": 4,
         "apm_now": 2, "pps_now": 2, "attack_mark": 3, "pieces_mark": 2, "spin_count": 3, "tetris_count": 3,
         "b2b_break": 3, "app_high": 2, "burst": 6, "pause": 5, "resume": 4, "apm_ahead": 2, "apm_behind": 2}
BIG = set()   # (some came in bigger letters once; all the same size now: user)
# after a match, more keep coming for this long, one every BUZZ_GAP_S (divided by the amount)
BUZZ_S = {"win": 4.0, "lose": 3.5, "pinch": 2.5, "pc": 3.0, "burst": 2.5}
BUZZ_GAP_S = {"win": (0.12, 0.28), "lose": (0.14, 0.30), "pinch": (0.16, 0.32), "pc": (0.12, 0.26), "burst": (0.14, 0.30)}
# no line is on screen twice at once (the same comment twice looks made up —
# user), but for the ones a crowd really does type over and over: 8888, GG, w
SHORT_LEN = 6
REPEATABLE = re.compile(r"^(?:[8８]+|GG!*|gg|W|[wｗ]+)$")
PAIR_GAP_S = 0.6         # the second of a pair starts this much later, in the lane under the first
AMBIENT_S = (1.0, 3.0)   # one now and then, every this many seconds (divided by the amount)
# after the set (off the match screen: the results / replay-saving screen) new
# ones come for this long only; those already out finish crossing (user)
SET_END_S = 3.0
# the numbers: looked at every STATS_EVERY_S while a match goes; each kind at
# most once in its cool-down
STATS_EVERY_S = 3.0
COOLDOWN_S = {"apm_now": 20.0, "pps_now": 30.0, "app_high": 45.0, "apm_ahead": 35.0, "apm_behind": 35.0,
              "apm_high": 25.0, "apm_low": 40.0, "pps_fast": 30.0, "garbage_big": 6.0, "pinch": 15.0,
              "quiet": 20.0, "burst": 15.0}
# your board (scripts/mosaic.board_now, read by the server each time): garbage
# coming up GARBAGE_BIG rows or more within GARBAGE_WINDOW_S; a pinch at
# PINCH_ROWS high (held PINCH_HOLD_S: not a flash), over at RECOVER_ROWS;
# no clear of yours for QUIET_S
GARBAGE_BIG, GARBAGE_WINDOW_S = 4, 1.5
PINCH_ROWS, PINCH_HOLD_S, RECOVER_ROWS = 15, 0.5, 9
QUIET_S = 10.0
# a burst: BURST_LINES or more of your attack within BURST_WINDOW_S
BURST_LINES, BURST_WINDOW_S = 10, 6.0
APM_HIGH, APM_LOW, PPS_FAST = 1.25, 0.6, 1.2   # times your usual (scripts/mosaic.usual)
DEFAULT_USUAL = {"apm": 60.0, "pps": 1.5}
TIME_MARKS_S = (60, 120, 180, 300)
# once a match each, as the count gets there
ATTACK_MARKS = (20, 40, 60, 80, 100)
PIECE_MARKS = (100, 200, 300, 500)
SPIN_MARKS = (3, 5, 10, 15, 20)
TETRIS_MARKS = (3, 5, 10)
APP_HIGH = 0.6
AHEAD = 1.2            # one APM this many times the other's
NUMBERS_GAP_S = 6.0    # number comments at least this far apart (not all at once)
B2B_BREAK_MIN = 4
TSPIN_KIND = {"T-SPIN Single": "tss", "T-SPIN Double": "tsd", "T-SPIN Triple": "tst",
              "T-SPIN Mini Single": "tsm", "T-SPIN Mini": "tspin0", "T-SPIN Mini Double": "tsmd",
              "T-SPIN": "tspin0"}


def _pool(kind, lang):
    """The lines for a kind, in that language. (Short ones once got other
    endings added — ー, 〜, w … — but that looked made up: user.)"""
    _, ja, en = POOL[kind]
    return list(en if lang == "en" else ja)


def _event_key(e):
    """An event_log entry as itself: time, what, a PERFECT CLEAR or not (hud/challenge.py event_key)."""
    return round(float(e.get("t") or 0), 3), str(e.get("label") or ""), bool(e.get("perfect_clear"))


def text_width(text):
    """A comment's width on screen, reference px (about: wide letters a full
    em, narrow ones a little over half, the edge round it)."""
    import unicodedata
    def k(c):   # (measured against hud/challenge.py comment_image, a little over)
        if "぀" <= c <= "ヿ":
            return 0.85            # kana
        return 1.0 if unicodedata.east_asian_width(c) in "WF" else 0.75
    em = sum(k(c) for c in str(text))
    return em * COMMENT_PX + 8


def _head(t0, w, t):
    """Where a comment's left edge is at time t (started at t0, w wide)."""
    return SCREEN_W - (t - t0) / FLOW_S * (SCREEN_W + w)


def apart(a, b):
    """Two comments in one row, (start, width) each: never touching?"""
    (tf, wf), (tk, wk) = sorted((a, b))
    t_end = tf + FLOW_S   # (the front one gone by then)
    if t_end <= tk:
        return True
    # (the gap between them changes steadily: enough at both ends is enough all along)
    return all(_head(tk, wk, t) - (_head(tf, wf, t) + wf) >= LANE_GAP for t in (tk, t_end))


def _fill(line, n=None, name=None):
    return line.replace("{n}", str(n if n is not None else "")).replace("{name}", name or "")


class CommentStream:
    """The live comments, worked out from each state as it's sent."""

    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.items = []         # {"id", "text", "lane", "t", "big", "kind"}
        self._next_id = 1
        self._match = None
        self._seen = {}         # side -> the event_log entries seen (_event_key)
        self._ended = False
        self._in_set = False      # on the match screen (matches, results, between matches)
        self._tail_until = None   # after the set: flowing on till then
        self._next_ambient = None
        self._openers = {}        # side -> the opener already talked about
        self._last_ren = {}       # side -> the REN of its latest clear
        self._next_stats = None
        self._cool = {}           # kind -> when it may come again
        self._marks = set()       # the match-time marks (and count milestones) already said
        self._last_b2b = 0        # your BtB chain at the last look
        self._numbers_quiet = 0.0  # no number comment before then
        self._garbage = []        # (t, garbage rows) of your board lately
        self._high_since = None   # your stack high since
        self._pinched = False     # in a pinch now (said), till it's back down
        self._had_pinch = False   # a pinch this match (a win then: a comeback)
        self._last_clear = None   # your last clear
        self._sent = []           # (time, lines) of your attacks lately (a burst)
        self._buzz = None         # after a match: (kind, until, next one)
        self._mid = midgame.Watch()   # your board: a mid-game setup being used
        self._paused = False      # the match paused (said)
        self._me = self._rival = None  # the players' names, once read (state["names"])

    def _names(self, text):
        return text.replace("{me}", self._me or "").replace("{rival}", self._rival or "")

    def _say(self, kind, now, lang, amount, n=None, name=None):
        pool = _pool(kind, lang)
        if name is None:   # (lines needing a name only when there is one)
            pool = [p for p in pool if "{name}" not in str(p)] or pool
        # the players' names (scripts/player_names.py): their lines only once read
        for key, value in (("{me}", self._me), ("{rival}", self._rival)):
            if not value:
                pool = [p for p in pool if key not in str(p)] or pool
        count = max(1, round(COUNT[kind] * amount))
        showing = {c["text"] for c in self.items if now - c["t"] < FLOW_S}
        for k in range(count):
            # not a long one already showing (nothing left: one fewer this time)
            nm = self.rng.choice(name) if isinstance(name, list) else name   # (a name with other ones it goes by)
            free = [p for p in pool if not any(not REPEATABLE.match(x) and self._names(_fill(x, n, nm)) in showing
                                               for x in (p if isinstance(p, list) else [p]))]
            if not free:
                continue
            pick = self.rng.choice(free)
            lines = pick if isinstance(pick, list) else [pick]   # a list: lines that go together (user)
            delay = k * self.rng.uniform(0.12, 0.35)   # a burst, not all at once
            texts = [self._names(_fill(line, n, nm)) for line in lines]
            spot = self._place(now + delay, [text_width(x) for x in texts])
            if spot is None:   # (every row full for a while: this one isn't said)
                continue
            lane, start = spot
            for m, text in enumerate(texts):
                showing.add(text)
                t = start + m * PAIR_GAP_S
                self.items.append({"id": self._next_id, "text": text, "lane": lane + m, "t": round(t, 3),
                                   "big": kind in BIG, "kind": kind})
                self._next_id += 1

    def _place(self, t0, widths):
        """(row, start) for a comment (a pair: the rows one under the other,
        the second PAIR_GAP_S later), touching none in its rows; from t0, up to
        WAIT_S later. None: no room."""
        by_lane = {}
        for c in self.items:
            by_lane.setdefault(c["lane"], []).append((c["t"], text_width(c["text"])))
        steps = int(round(WAIT_S / WAIT_STEP_S))
        for k in range(steps + 1):
            t = t0 + k * WAIT_STEP_S
            ok = [lane for lane in range(LANES - len(widths) + 1)
                  if all(apart((t + m * PAIR_GAP_S, w), other)
                         for m, w in enumerate(widths) for other in by_lane.get(lane + m, ()))]
            if ok:
                return self.rng.choice(ok), t
        return None

    def update(self, display, state, now, usual=None, board=None):
        """state["comments"]: {"now", "items"} (the server's clock), or None when off.
        usual: your usual APM / PPS (scripts/mosaic.usual), for "a lot more than usual".
        board: your board now, {"garbage", "height"} (scripts/mosaic.board_now)."""
        amount = AMOUNT.get(display.get("challenge_comments", "off"))
        if amount is None or display.get("enabled") is False:
            self.items = []
            return None
        st = state or {}
        lang = display.get("language", "ja")
        names = st.get("names") or {}
        you_side = st.get("you_side") if st.get("you_side") in ("left", "right") else "left"
        self._me = names.get(you_side)
        self._rival = names.get("right" if you_side == "left" else "left")
        in_set = st.get("match_screen") is True
        if self._in_set and not in_set:   # the set is over (back to the menus)
            self._say("set_end", now, lang, amount)
            self._tail_until = now + SET_END_S
        self._in_set = in_set
        if in_set or (self._tail_until is not None and now < self._tail_until):
            if self._next_ambient is None:
                self._next_ambient = now + self.rng.uniform(*AMBIENT_S) / amount
            elif now >= self._next_ambient:
                idle = "pause" if st.get("paused") and not st.get("frozen") else "ambient"
                self._say(idle, now, lang, 1.0 / COUNT[idle])
                self._next_ambient = now + self.rng.uniform(*AMBIENT_S) / amount
        else:
            self._next_ambient = None
            self._buzz = None
        you = st.get("you_side") if st.get("you_side") in ("left", "right") else "left"
        match = st.get("match_start_t")
        playing = st.get("match_screen") is True and match is not None
        if match != self._match:
            self._match, self._seen, self._ended = match, {}, False
            self._openers, self._last_ren, self._marks, self._next_stats = {}, {}, set(), None
            self._last_b2b, self._numbers_quiet = 0, 0.0
            self._garbage, self._high_since, self._pinched, self._had_pinch = [], None, False, False
            self._last_clear, self._buzz, self._sent = now, None, []
            self._paused = False
            self._mid.reset()
            if playing and not st.get("frozen"):
                self._say("start", now, lang, amount)
        paused = playing and bool(st.get("paused")) and not st.get("frozen")
        if paused != self._paused:
            self._paused = paused
            self._buzz = None
            self._say("pause" if paused else "resume", now, lang, amount)
        if playing:
            for side in ("left", "right"):
                sd = st.get(side) or {}
                log = sd.get("event_log") or []
                log = [e for e in log if isinstance(e, dict) and e.get("t") is not None]
                # each entry known by what it is (a REN break goes on top later
                # with an earlier time: the clear under it isn't new again)
                keys = {_event_key(e) for e in log}
                if side not in self._seen:
                    self._seen[side] = keys    # (what was there before: no flood)
                    self._openers[side] = sd.get("opener")
                    continue
                new = [e for e in log if _event_key(e) not in self._seen[side]]
                self._seen[side] = keys
                for e in reversed(new):
                    self._react(e, side, side == you, now, lang, amount, sd.get("b2b") or 0)
                opener = sd.get("opener")
                if opener and opener != self._openers.get(side):
                    self._openers[side] = opener
                    self._say("opener" if side == you else "rival_opener", now, lang, amount, name=str(opener))
            if not st.get("frozen") and not paused:
                self._numbers(st, you, now, lang, amount, usual or {})
                if board:
                    self._board(board, now, lang, amount)
            winner = st.get("winner")
            if st.get("frozen") and winner in ("left", "right") and not self._ended:
                self._ended = True
                if winner == you and self._had_pinch:
                    self._say("comeback", now, lang, amount)
                kind = "win" if winner == you else "lose"
                self._say(kind, now, lang, amount)
                # and on for a while, one after another: the room's buzzing (user)
                self._buzz = (kind, now + BUZZ_S[kind], now + 0.4)   # (after the first burst)
        if self._buzz:
            kind, until, nxt = self._buzz
            while nxt <= now and nxt < until:
                self._say(kind, nxt, lang, 1.0 / max(1, COUNT[kind]))   # (one at a time)
                nxt += self.rng.uniform(*BUZZ_GAP_S[kind]) / amount
            self._buzz = (kind, until, nxt) if nxt < until else None
        self.items = [c for c in self.items if now - c["t"] < FLOW_S]
        return {"now": round(now, 3), "items": list(self.items)}

    def _numbers(self, st, you, now, lang, amount, usual):
        """Your APM / PPS against your usual, and the match time."""
        if self._next_stats is None:
            self._next_stats = now + STATS_EVERY_S
            return
        if now < self._next_stats:
            return
        self._next_stats = now + STATS_EVERY_S
        elapsed = float(st.get("match_elapsed_s") or 0)
        for mark in TIME_MARKS_S:
            if elapsed >= mark and mark not in self._marks:
                self._marks.add(mark)
                if elapsed < mark + STATS_EVERY_S * 2:   # (not when the app came on long after)
                    self._say("time", now, lang, amount, n=mark // 60)
        if elapsed < 20:   # the numbers settle first
            return
        sd = st.get(you) or {}
        apm = (sd.get("apm") or {}).get("apm") if isinstance(sd.get("apm"), dict) else None
        pps = sd.get("pps")
        enough = usual.get("matches", 0) >= 5
        u_apm = usual.get("apm") if enough and usual.get("apm") else DEFAULT_USUAL["apm"]
        u_pps = usual.get("pps") if enough and usual.get("pps") else DEFAULT_USUAL["pps"]

        def ready(kind):
            return now >= self._cool.get(kind, 0.0)

        def said(kind, n=None):
            self._cool[kind] = now + COOLDOWN_S[kind]
            self._say(kind, now, lang, amount, n=n)
        # milestones (each once a match) and the numbers as they are
        stats = sd.get("match_stats") or {}
        for kind, value, marks in (("attack_mark", sd.get("attack"), ATTACK_MARKS),
                                   ("pieces_mark", sd.get("pieces"), PIECE_MARKS),
                                   ("spin_count", stats.get("tspin"), SPIN_MARKS),
                                   ("tetris_count", stats.get("tetris"), TETRIS_MARKS)):
            if value is None:
                continue
            reached = [m for m in marks if value >= m and (kind, m) not in self._marks]
            for m in reached:
                self._marks.add((kind, m))
            if reached and value < reached[-1] * 1.5:   # (not a pile of old ones when the app came on late)
                self._say(kind, now, lang, amount, n=reached[-1])
        b2b = int(sd.get("b2b") or 0)
        if self._last_b2b >= B2B_BREAK_MIN and b2b == 0:
            self._say("b2b_break", now, lang, amount, n=self._last_b2b)
        self._last_b2b = b2b
        if now < self._numbers_quiet:
            return
        before = len(self.items)
        rival = st.get("right" if you == "left" else "left") or {}
        r_apm = (rival.get("apm") or {}).get("apm") if isinstance(rival.get("apm"), dict) else None
        app = sd.get("app")
        if apm is not None and r_apm and apm >= r_apm * AHEAD and r_apm >= 10 and ready("apm_ahead"):
            said("apm_ahead", n=int(round(r_apm)))
        elif apm and r_apm is not None and r_apm >= apm * AHEAD and ready("apm_behind"):
            said("apm_behind", n=int(round(r_apm)))
        elif app is not None and elapsed >= 40 and app >= APP_HIGH and ready("app_high"):
            said("app_high", n=f"{app:.2f}")
        elif apm is not None and u_apm * 0.9 <= apm < u_apm * APM_HIGH and ready("apm_now"):
            said("apm_now", n=int(round(apm)))
        elif pps is not None and pps < u_pps * PPS_FAST and ready("pps_now"):
            said("pps_now", n=f"{pps:.2f}")
        if len(self.items) > before:
            self._numbers_quiet = now + NUMBERS_GAP_S
        if apm is not None and apm >= u_apm * APM_HIGH and ready("apm_high"):
            said("apm_high", n=int(round(apm)))
        elif apm is not None and elapsed >= 40 and apm <= u_apm * APM_LOW and ready("apm_low"):
            said("apm_low")
        if pps is not None and pps >= u_pps * PPS_FAST and ready("pps_fast"):
            said("pps_fast", n=f"{pps:.2f}")

    def _ready(self, kind, now):
        return now >= self._cool.get(kind, 0.0)

    def _board(self, board, now, lang, amount):
        """Your board: garbage coming up, a pinch and getting out of it, a long quiet."""
        g, h = int(board.get("garbage") or 0), int(board.get("height") or 0)
        self._mid.see(board.get("grid"), now)
        self._garbage = [(t, n) for t, n in self._garbage if now - t <= GARBAGE_WINDOW_S] + [(now, g)]
        if g - min(n for _, n in self._garbage) >= GARBAGE_BIG and self._ready("garbage_big", now):
            self._cool["garbage_big"] = now + COOLDOWN_S["garbage_big"]
            self._garbage = [(now, g)]
            self._say("garbage_big", now, lang, amount)
        if h >= PINCH_ROWS:
            self._high_since = self._high_since if self._high_since is not None else now
            if not self._pinched and now - self._high_since >= PINCH_HOLD_S and self._ready("pinch", now):
                self._pinched = self._had_pinch = True
                self._cool["pinch"] = now + COOLDOWN_S["pinch"]
                self._say("pinch", now, lang, amount)
                if not self._buzz:   # (and on for a moment: the room's worried)
                    self._buzz = ("pinch", now + BUZZ_S["pinch"], now + 0.4)
        else:
            self._high_since = None
            if self._pinched and h <= RECOVER_ROWS:
                self._pinched = False
                self._say("recover", now, lang, amount)
        if self._last_clear is not None and now - self._last_clear >= QUIET_S and self._ready("quiet", now):
            self._cool["quiet"] = now + COOLDOWN_S["quiet"]
            self._say("quiet", now, lang, amount)

    def _react(self, e, side, mine, now, lang, amount, b2b=0):
        label = str(e.get("label") or "")
        if not mine:   # the other player: only the big ones, a few
            if e.get("perfect_clear") or "T-SPIN" in label or "TETRIS" in label:
                self._say("rival", now, lang, amount)
            return
        if label not in ("REN途切れ", "T-SPIN", "T-SPIN Mini"):   # (a clear: not quiet any more)
            self._last_clear = now
        if label == "REN途切れ":
            if self._last_ren.get(side, 0) >= 4:
                self._say("ren_break", now, lang, amount)
            self._last_ren[side] = 0
            return
        if e.get("perfect_clear"):
            self._say("pc", now, lang, amount)
            self._buzz = ("pc", now + BUZZ_S["pc"], now + 0.4)   # (and on for a moment)
        elif label in TSPIN_KIND:
            self._say(TSPIN_KIND[label], now, lang, amount)
            setup = self._mid.spun(TSPIN_KIND[label], now)
            if setup:
                self._say("midgame", now, lang, amount, name=midgame.names(setup, lang))
        elif "TETRIS" in label:
            self._say("tetris", now, lang, amount)
        ren = e.get("ren_count") or 0
        self._last_ren[side] = ren
        if ren >= 4:
            self._say("ren", now, lang, amount, n=ren)
        if e.get("btb") and b2b >= 2 and b2b % 2 == 0:   # a Back-to-Back chain: now and then
            self._say("b2b", now, lang, amount, n=b2b)
        self._burst(e, now, lang, amount)

    def _burst(self, e, now, lang, amount):
        """A lot of attack in a short time: comments, and on for a moment (user)."""
        try:
            lines = int(e.get("lines") or 0)
        except (TypeError, ValueError):
            lines = 0
        if lines <= 0:
            return
        self._sent = [(t, n) for t, n in self._sent if now - t <= BURST_WINDOW_S] + [(now, lines)]
        total = sum(n for _, n in self._sent)
        if total >= BURST_LINES and self._ready("burst", now):
            self._cool["burst"] = now + COOLDOWN_S["burst"]
            self._say("burst", now, lang, amount, n=total)
            self._sent = []
            if not self._buzz:
                self._buzz = ("burst", now + BUZZ_S["burst"], now + 0.4)


def catalog():
    """docs/comments.md: every comment, by when it comes."""
    out = ["# 縛りプレイ「コメントが流れる」のコメント一覧", "",
           "このファイルは `scripts/comments.py` の中身から作っています（`python scripts/comments.py` で作り直し）。",
           "`{n}` には数字、`{name}` には開幕テンプレの名前が入ります。「数」は量「ふつう」のとき 1 回に流れる数です。",
           ""]
    for kind, (when, ja, en) in POOL.items():
        shown = [" → ".join(x) + "（2 つセット）" if isinstance(x, list) else x for x in ja]
        out += [f"## {when}", "", f"数: {COUNT[kind]}"
                + f"　種類: {len(ja)}", "", "- " + " / ".join(shown), "",
                "英語: " + " / ".join(" → ".join(x) if isinstance(x, list) else x for x in en), ""]
    return "\n".join(out)


if __name__ == "__main__":
    from pathlib import Path
    path = Path(__file__).resolve().parent.parent / "docs" / "comments.md"
    path.write_text(catalog(), encoding="utf-8")
    print("wrote", path)

# wugniu-gram

[蘇滬混合腔](https://github.com/SiqYin/wugniu_suwu)（吳語）韻書輸入法的
Rime 語法模型（octagram / 八股文）。

參照 [`zh-hant-cantonese.gram`](https://github.com/JACKCHAN000/rime-corpus-processing)
的做法，用**字符 2–6 gram** 從吳語語料訓練，供 Rime 根據已上屏的上文
調整候選詞排序。

* 模型檔：`out/wu-suhu.gram`（約 253 KB）
* 語料：作者私有吳語語料（1.6 萬字，正字法與輸入法一致）
  ＋ `wuphin.*` 吳語詞庫（補高頻搭配）
* 用法：見下方「部署」一節

---

## 這個模型是什麼

`.gram` 不是神經網絡，而是一張**字符 n-gram 頻次表**：

1. 訓練時對語料滑窗，統計 2–6 個連續漢字的出現次數
2. 編譯成 Darts 雙數組 trie，每條 n-gram 存一個 `int(ln(次數) × 10000)` 的評分
3. 運行時拿**已上屏的漢字**當上下文查表，命中則給候選詞加分

它不理解語法，只知道「哪些字常常挨在一起」。

---

## 為什麼用自帶的純 Python 構建器

官方構建工具 `build_grammar.exe`（來自 gaboolic/rime-build-grammar）是
MinGW 動態鏈接的二進制檔，依賴 `libglog-2.dll`、`libmarisa-0.dll`、
`libopencc-1.2.dll`、`libyaml-cpp.dll`、`libleveldb.dll` 等運行庫，
在未裝 MSYS2/MinGW 環境的機器上無法直接運行（退出碼 127）。

本倉庫的 `tools/build_gram.py` 按
[`darts.h`](https://github.com/s-yata/darts-clone) 的位域與尋址語義
自行實現了構建，輸出格式與官方工具一致：

```
偏移 0    char format[32]     "Rime::Grammar/1.0"
偏移 32   uint32 db_checksum  實測恆為 0
偏移 36   uint32 unit_count   雙數組單元個數
偏移 40   int32  offset_rel   實測恆為 4 → 數據自偏移 44 起
偏移 44   uint32 unit[]       每單元 4 字節小端
```

文件大小恆等於 `44 + unit_count × 4`（已用本倉庫模型與 39 MB 的
`zh-hant-cantonese.gram`、403 MB 的 `wanxiang-lts-zh-hant.gram` 三方核對）。

單元位域（同 `DoubleArrayBuilderUnit`）：

| 位 | 含義 |
|---|---|
| bit31 | 葉子標誌（該單元存評分） |
| bit8 | `has_leaf`（本節點是某 key 的結尾） |
| bit0–7 | `label`（邊上的字節） |
| bit10+ | `offset`；若 bit9 置位則再左移 8 |

尋址：`base = node ^ offset(node)`，子節點 = `base ^ label`。

### 可驗證性

* `tools/gram_format.py` 的解析器已用它成功讀出官方
  `zh-hant-cantonese.gram`：`香港` → 約 386 萬次、`唔該` → 約 5.2 萬次，
  證明對格式的理解無誤
* `tools/verify_gram.py` 把構建輸入逐條回查，本模型 **11,717 / 11,717 全部通過**

### 已知限制

Darts 的 `set_offset` 在 `offset >= 2^21` 時會切到「左移 8」的編碼，
該編碼丟棄低 8 位、必須配合 256 對齊。本實現未做塊對齊，
故安全邊界是約 **8 MiB**（2^21 單元）的雙數組；超過時腳本會主動報錯。
本模型 0.25 MiB，餘量充足。

---

## 語料準備

### 字形的兩個坑

**坑一：必須與輸入法的實際輸出字形一致。**
`wugniu_suwu` 的 schema 有一個 `options` 開關：

```yaml
options: [ noop, varients_wy, variants_hk, trad_tw, varients_jp, simplification, varients_sy ]
states:  [ 漢字, 吳語漢字, 香港漢字, 臺灣漢字, 日本漢字, 汉字, 雪螢漢字]
reset: 1
```

* 序號 0 = `noop` = 「漢字」= **詞庫原生字形**（本項目語料採用的標準）
* 序號 1 = `varients_wy` = 「吳語漢字」，經 `s2wy.json` 轉換

grammar 模型匹配的是**上屏後的字元**。若語料與實際輸出字形不一致，
命中率會大幅下降，表現為「模型好像沒生效」。

**坑二：不要按字集做白名單過濾。**
本項目詞庫主體是**繁體**（`講`、`曉`、`飯`），而語料裡混入了一小批
簡體殘留（多來自引用的簡體段落）。早期版本若按字集過濾，
會把「曉得、講、話、飯、閒、難」這類基礎字整片剔除，
曾把 4,811 行語料清成 17 行。

`tools/count_ngram.py` 的做法：把語料中混入的簡體殘留統一歸一到
詞庫標準繁體（內置一份小而精確的映射，候選均已在詞庫字集中核驗），
**不做**大規模字集過濾。

### 一個容易誤判的現象

腳本報告「正字法未收 XX 字」時不必緊張。實測 24 個蘇滬基礎字
（`講 曉 飯 閒 難 亂 儂 關 廟 當 來 樁 氣 靈 緊 蘇 蠻 覺 該 過 還 們 說 點`）
在**繁體形式下全部已收錄**，只是詞庫檔案裡存的是繁體。
判斷「打不出」要看完整字集（含 `sougouciku`、`luna_pinyin.sogou`），
而不是只看吳語專用庫。

---

## 構建

```bash
# 一鍵走完：抽取 → 統計 → 構建 → 自檢
python tools/build_all.py \
  --dict path/to/wuphin.word.dict.yaml \
  --dict path/to/wuphin.map.dict.yaml \
  --dict path/to/wuphin.phrases.dict.yaml

# 若需從 .docx 重新抽取語料
python tools/build_all.py --docx-dir "D:/Wu/Chrome/吳語語料" --dict ...
```

產物為 `out/wu-suhu.gram`。

### 分步執行

```bash
python tools/docx_to_txt.py  in.docx  corpus/wu_text.txt
python tools/count_ngram.py  --input corpus/wu_text.txt \
                             --dict-words wuphin.word.dict.yaml \
                             --output work/ngram.tsv
python tools/build_gram.py   --input work/ngram.tsv --language wu-suhu
python tools/verify_gram.py  --gram out/wu-suhu.gram --tsv work/ngram.tsv
```

### 參數取捨

| 參數 | 說明 |
|---|---|
| `--min-count-N` | 各階最低出現次數。默認 2 |
| `--dict-weight` | 補充詞庫的重複次數 |
| `--dict-sentence-end` | 為補充詞庫生成 `$` 句末標記，**默認關閉** |
| `--value-multiplier` | 評分整體抬升，增大模型影響力 |

兩個實測結論：

* **不要用大 `--weight` 配大 `--min-count`**。權重是全局相乘的，
  `--weight 3` 配 `--min-count 3` 等於「出現過就算過關」，
  6-gram 會從 319 條暴增到 7,475 條，全是雜訊。
* **補充詞庫要關掉 `$` 標記**。詞庫是離散詞條，每條都會被當成
  句子結尾，生成大量假的 `$` 條目，會污染 octagram 的 `is_rear` 判斷。

### 語料量與各階的關係

實測本語料（1.6 萬字）各階在不同 min-count 下可保留的條目數：

| 階 | 類型數 | ≥2 次 | ≥3 次 |
|---|---|---|---|
| 2-gram | 9,829 | 2,446 | 1,089 |
| 3-gram | 11,645 | 1,395 | 363 |
| 4-gram | 10,596 | 811 | 147 |
| 5-gram | 9,039 | 503 | 75 |
| 6-gram | 7,475 | 319 | 39 |

可見 2–3 階是靠譜的，5–6 階在 `min-count 2` 下只剩幾百條。
加入 `wuphin.*` 詞庫後 2-gram 補到 7,667 條，是模型的主要貢獻來源。

---

## 部署

1. 把 `out/wu-suhu.gram` 與 `grammar.yaml` 複製到 Rime 用戶文件夾
   （Windows：`%APPDATA%\Rime`）
2. 把 `wugniu_suwu.custom.yaml` 複製到同一文件夾
   （若已存在同名檔案，只合併 `patch:` 內容，**不要出現兩個 `patch:` 鍵**）
3. 執行 Rime「重新部署」

### 三個必須知道的坑

**坑一：`grammar/language` 必須與 `.gram` 檔名逐字相同。**
不一致時 Rime 會**靜默失敗**（退回無語法模型狀態，不報錯）。

**坑二：`collocation_min_length` 必須是 2。**
octagram 對「匹配長度 < min_length」的命中套用
`weak_collocation_penalty`（默認 −24），比 `non_collocation_penalty`
（默認 −12）更差，會讓 2-gram 的命中**反而變成懲罰**。

**坑三：`collocation_max_length` 要對應模型實際的階數。**
內部取值 `n = min(8, collocation_max_length − 1)`。若設成 2，
`n = 1`，只能檢索 2-gram，本模型裡 3–6 階的條目將永遠查不到。

### 關於評分尺度

本模型語料量有限，各條目評分 = `ln(次數)`，取值範圍只有 **0～6**；
而 librime 默認 `non_collocation_penalty = −12`。
因此「命中」相對「未命中」的增益最大約 6 分 —— 有感，但不強勢。

`grammar.yaml` 裡附了一段「增強參數」註釋（把 `collocation_penalty`
從 −12 抬到 −6 等）。原則是讓 `collocation_penalty` 明顯大於
`non_collocation_penalty`，差值即固定增益。差值過大會讓小語料裡的
偶然搭配壓過詞庫本身的詞頻，反而變差，建議實測調整。

> 參考：`zh-hant-cantonese.gram` 語料極大（`香港` 一條就有 386 萬次），
> `ln(次數)` 可達 15 分以上，所以官方參數直接用默認值就夠。

---

## 部署前提：octagram 支持

`librime` 的語法模型由 `octagram` 插件提供。經核查，
本機 Weasel 0.17.4 的 `rime.dll` **已內置**該插件：

```
plugins\octagram\src\gram_db.cc
plugins\octagram\src\octagram.cc
Rime::Grammar/1.0
```

即 `zh-hant-cantonese.gram` 一直在正常生效，無需另行安裝插件。

---

## 倉庫結構

```
wu-gram/
├─ grammar.yaml               Rime 語法模型配置
├─ wugniu_suwu.custom.yaml    方案補丁（示例）
├─ out/wu-suhu.gram           構建產物
├─ corpus/                    語料（不入庫，私有）
└─ tools/
   ├─ gram_format.py    .gram 格式讀寫 + Darts 單元位域
   ├─ build_gram.py     純 Python .gram 構建器
   ├─ count_ngram.py    語料 → n-gram 頻次
   ├─ verify_gram.py    逐條回查自檢
   ├─ docx_to_txt.py    .docx → 純文字
   └─ build_all.py      一鍵流水線
```

---

## 發佈說明與授權

* **語料不入庫**。`corpus/` 已列入 `.gitignore`；作者的個人文章與
  歌詞改編屬私有創作。
* `.gram` 是從上述語料統計出的字符 n-gram 頻次表，**不含原文**，
  但 6-gram 條目理論上可能與原文有 6 字以內的重合片段。
  若對此有顧慮，可只用 `--input`（不接 `--dict-words`）以純私有語料
  構建後自行決定是否發佈。
* 本倉庫目前**未附許可證**（與上游 `wugniu_suwu` 一致）。
  若要正式發佈，建議補一份 `LICENSE`；`tools/` 為本項目原創實現，
  `wuphin.*` 詞庫來自 `wugniu_suwu`，引用時請遵循其條款。

## 參考

* [rime-corpus-processing](https://github.com/JACKCHAN000/rime-corpus-processing) —— 粵語模型的語料處理與構建流程
* [librime-octagram](https://github.com/lotem/librime-octagram) —— 八股文插件
* [darts-clone](https://github.com/s-yata/darts-clone) —— 雙數組 trie
* [wugniu_suwu](https://github.com/SiqYin/wugniu_suwu) —— 蘇滬混合腔輸入方案

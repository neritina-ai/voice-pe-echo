# Voice PE Echo 使用手冊

這個小程式在電腦上執行後，會 **24 小時透過 Home Assistant Voice Preview Edition（以下簡稱 Voice PE）收音**：
你對 Voice PE 說一句話，電腦喇叭就把那句話原音重播出來，直到你關掉程式為止。

```
 你說話 ──▶ Voice PE 麥克風 ──(Wi-Fi，ESPHome API)──▶ 電腦上的 voice-pe-echo
                                                        │ 偵測「一句話」的開頭與結尾
                                                        ▼
                                                    電腦喇叭播放
```

**不需要安裝 Home Assistant，也不需要改韌體。** 剛買來的 Voice PE 只要連上 Wi-Fi，就能直接使用。
（Voice PE 名字裡有 Home Assistant，但它跑的是 ESPHome 韌體，本程式直接透過 Wi-Fi 跟它溝通，取代平常 Home Assistant 的角色。）

這份手冊以「**剛買來、電腦上什麼都還沒裝**」為主。如果你的 Voice PE 已經加入 Home Assistant，請先看〈[附錄：Voice PE 已經加入 Home Assistant](#附錄voice-pe-已經加入-home-assistant)〉。
想知道「為什麼這樣設計」，請看 [設計說明](design.md)。

---

## 目錄

1. [準備清單](#1-準備清單)
2. [讓 Voice PE 連上 Wi-Fi](#2-讓-voice-pe-連上-wi-fi)
3. [安裝與啟動程式](#3-安裝與啟動程式)
4. [使用方式](#4-使用方式)
5. [擺放位置與防回授](#5-擺放位置與防回授)
6. [設定與參數](#6-設定與參數)
7. [疑難排解](#7-疑難排解)
8. [附錄：Voice PE 已經加入 Home Assistant](#附錄voice-pe-已經加入-home-assistant)

---

## 1. 準備清單

| 項目 | 說明 |
|---|---|
| Voice PE | 用 USB-C 接上電源（5V/2A 以上的手機充電器即可）。 |
| 電腦 | Windows 10/11、macOS 或 Linux，要有喇叭（或耳機）。 |
| 瀏覽器 | Chrome 或 Edge（設定 Wi-Fi 時用，只需要一次）。 |
| USB-C 傳輸線 | 建議準備：用 USB 設定 Wi-Fi 最穩，還能順便更新韌體。必須是能傳資料的線，不是只能充電的線。 |
| 同一個網路 | 電腦和 Voice PE 要連在**同一台路由器**底下。Wi-Fi 的「訪客網路」或開啟「AP 隔離」的網路會讓兩者互相看不到。 |
| Python 3.11 以上 | 建議 3.12 或更新版本。Windows 請到 <https://www.python.org/downloads/> 下載，安裝時**勾選「Add python.exe to PATH」**。macOS 可用 `brew install python`。 |

---

## 2. 讓 Voice PE 連上 Wi-Fi

剛買來的 Voice PE 只缺這一步。下面兩種方法擇一，**只需要做一次**，Voice PE 會記住 Wi-Fi，之後插電就會自動連上。

### 方法 1：用 USB 線（推薦，可順便更新韌體）

1. 用 USB-C 傳輸線把 Voice PE 接到電腦（Voice PE 直接由電腦供電即可）。
2. 用 Chrome 或 Edge 打開 Voice PE 的官方安裝頁面：<https://esphome.github.io/home-assistant-voice-pe/>
3. 在「**Install Voice PE Latest Firmware**」下面按 **CONNECT**，選擇出現的序列埠（通常名稱含 `USB JTAG/serial debug unit` 或 `ESP32`）。
4. 連上後畫面會顯示 Voice PE 目前的韌體版本，並提供幾個選項：
   - **更新／安裝韌體**（建議）：如果顯示有新版，按下去更新成最新的**官方**韌體，約需 2～3 分鐘，過程中不要拔線。
     這是官方版本的更新，不是改韌體；裝的就是 Home Assistant 平常推送給 Voice PE 的同一份韌體。
   - **設定 Wi-Fi**（Connect to Wi-Fi／Change Wi-Fi）：選擇你的 Wi-Fi、輸入密碼。
5. 顯示連線成功後就完成了。之後可以拔掉 USB，改用一般充電器供電。

> 只想設定 Wi-Fi、不想更新，也可以改用 <https://web.esphome.io> → **CONNECT** → **Configure Wi-Fi**。

### 方法 2：用藍牙（不用接線）

1. 用電腦（需有藍牙）或 Android 手機的 Chrome 開 <https://www.improv-wifi.com>，按 **Connect device to Wi-Fi**。
2. 選擇名稱開頭為 `ha-voice-pe` 的裝置。
3. 依提示**按一下 Voice PE 的中央按鈕**授權，然後選擇 Wi-Fi、輸入密碼。

### 連上 Wi-Fi 之後

- Voice PE 的燈環會顯示「等待連線」的動畫（例如整圈閃紅光）。它在等 Home Assistant 連過來；我們用本程式代替，所以這是**正常的**，程式一連上就會恢復。
- 剛買來、沒加入過 Home Assistant 的 Voice PE **沒有加密金鑰**，程式可以直接連線，不需要任何密碼。

### 關於韌體版本

| 韌體 | 能不能用 |
|---|---|
| 新版（大約 2025 年中以後） | 程式啟動後會自動叫 Voice PE 開始收音（會聽到一聲提示音），完全不用動手。 |
| 很舊的出廠版本 | 也能用。程式會提示你「說一次 Okay Nabu 或按一下中央按鈕」，之後就會一直收音。想省掉這一步，用方法 1 更新韌體即可。 |

沒有 Home Assistant 時，Voice PE **不會自動更新**；想更新時，再用方法 1 的官方安裝頁面就好（Wi-Fi 設定會保留）。

---

## 3. 安裝與啟動程式

### 下載程式

在 GitHub 專案頁面按 **Code → Download ZIP** 下載後解壓縮，或用 `git clone`。

### 啟動

| 系統 | 怎麼啟動 |
|---|---|
| Windows | 雙擊 **`run.bat`**（或在命令提示字元執行 `run.bat`）。 |
| macOS | 在終端機進入資料夾執行 `./run.sh`。 |
| Linux | 先安裝音效函式庫 `sudo apt install libportaudio2`，再執行 `./run.sh`。 |

第一次執行會自動建立 Python 虛擬環境（`.venv` 資料夾）並安裝需要的套件，需要網路，約 1～2 分鐘。之後啟動只要幾秒。

不需要任何設定：程式會自動在區網找到 Voice PE。只有在你想調整參數、或家裡有多台 Voice PE 時，才需要設定檔（見第 6 節）。

> Windows 第一次執行時，防火牆可能詢問是否允許 Python 存取網路：請勾選「私人網路」並允許。
> 這是自動搜尋 Voice PE（mDNS）需要的；若沒有允許，請改用 `--host` 直接指定 Voice PE 的 IP。

### 啟動成功的畫面

```
10:15:02 沒有指定 --host，搜尋區網內的 Voice PE…
10:15:05 找到 Home Assistant Voice 0a1b2c
      主機：home-assistant-voice-0a1b2c.local  IP：192.168.1.50
      韌體：26.9.0  MAC：aa:bb:cc:0a:1b:2c  不需要金鑰
10:15:05 播放裝置：喇叭 (Realtek(R) Audio)（16000 Hz）
10:15:05 連線到 Voice PE（home-assistant-voice-0a1b2c.local）…
10:15:06 已連線：Home Assistant Voice 0a1b2c（韌體 26.9.0，ESPHome 2026.9.0）
10:15:07 請 Voice PE 開始收音…
10:15:08 開始收音：對著 Voice PE 說一句話，電腦就會原音重播（按 Ctrl+C 結束）
10:15:12 偵測到說話，錄音中…
10:15:14 第 1 句：2.3 秒，從電腦喇叭播放…
10:15:16 播放完畢，繼續收音
狀態：收音中         音量 [####----------------]  -48.3 dBFS
```

最下面那一行會即時更新：「音量」就是 Voice PE 目前收到的聲音大小，說話時應該明顯跳高。
這也是確認「Voice PE 有沒有收到聲音」最直接的方法。

### 常用指令

| 指令 | 用途 |
|---|---|
| `run.bat --discover` | 列出區網內所有 ESPHome 裝置（名稱、IP、韌體版本、MAC、是否需要金鑰）。 |
| `run.bat --list-devices` | 列出電腦的音訊輸出裝置（喇叭、耳機…）。 |
| `run.bat --host 192.168.1.50` | 指定 Voice PE 的 IP（自動搜尋失敗或有多台時用）。 |
| `run.bat --save-dir recordings` | 另外把每句話存成 WAV 檔。 |
| `run.bat -h` | 顯示所有參數。 |

macOS／Linux 把 `run.bat` 換成 `./run.sh`。

---

## 4. 使用方式

1. 程式連上後，Voice PE 會播放一聲提示音，燈環開始**慢慢旋轉** → 表示正在收音。
   （舊版韌體沒有提示音，請依畫面提示說一次「Okay Nabu」或按一下中央按鈕。）
2. 對著 Voice PE 說一句話。說話時燈環會**轉快**。
3. 停頓約 0.8 秒，程式判定這句話結束，就從**電腦喇叭**把原話播出來。
4. 播完再過約 0.6 秒，才會開始聽下一句（避免把喇叭的聲音又錄進去，見第 5 節）。
5. 要結束時，在程式視窗按 **Ctrl+C**。Windows 若問「終止批次工作 (Y/N)?」，輸入 `Y`。

### 燈環與實體按鍵

| 你看到／做的 | 意思 |
|---|---|
| 燈環慢速旋轉 | 收音中，等你說話。 |
| 燈環快速旋轉 | 偵測到有人說話，錄音中。 |
| 燈環上固定亮兩顆紅燈 | Voice PE 側邊的靜音開關打開了。程式會暫停；切回來就自動恢復收音（會再響一次提示音）。 |
| 整圈閃紅光 | Voice PE 沒有和任何程式連線（本程式還沒連上，或已經結束）。 |
| 按一下中央按鈕／說「Okay Nabu」 | Voice PE 會停止這一輪收音，程式約 1.5 秒後自動重新開始。 |
| 轉動上方旋鈕 | 調整 Voice PE **本身**喇叭的音量（只影響提示音），與電腦播放的音量無關。 |

### 注意事項

- **一次一句，像對講機**：電腦正在播放時不會收音。播放中你說的話不會被錄到。
- 程式會把每句話自動調整到差不多的音量再播放（可用 `--no-normalize` 關閉、`--volume` 調整倍率）。
- 一句話最長 20 秒，超過會被切開（`--max-sentence` 可調）。
- 很短的聲音（咳嗽、敲桌子，有效語音少於 0.3 秒）會被略過。
- 網路斷線、Voice PE 重新開機時，程式會自動重新連線，不需要重開。

---

## 5. 擺放位置與防回授

**回授**是指：電腦喇叭播出的聲音又被 Voice PE 收進去，被當成新的一句話再播一次，然後無限循環。

Voice PE 內建的回音消除晶片只認得「Voice PE 自己喇叭播放的聲音」，**無法消除電腦喇叭的聲音**，所以本程式用軟體處理，你不需要做任何事：

1. 電腦播放時，暫停處理 Voice PE 傳來的聲音。
2. 播放結束後，再多等 0.6 秒（房間迴音、喇叭延遲、網路延遲）。
3. 之後還要先聽到一小段安靜（0.25 秒），才會開始錄下一句；就算有殘留的迴音也不會被誤認成新的一句。

這個做法在測試中已確認可以擋住回授（測試同時驗證了：拿掉這個機制就會無限重播）。
搭配下面的擺放建議，效果最好：

| 建議 | 原因 |
|---|---|
| Voice PE 與電腦喇叭**相距 1 公尺以上** | 迴音越小，越不容易在等待時間結束後還殘留。 |
| 喇叭**不要正對** Voice PE | 同上。 |
| 喇叭音量**適中** | 太大聲時房間迴音拖得比較久。 |
| 使用者坐在 Voice PE 前方 30～100 公分 | 說話聲比背景聲大，偵測最準。 |
| **戴耳機**最保險 | 聲音完全不會回到麥克風。 |

**使用藍牙喇叭／藍牙耳機**：藍牙有 0.2～0.5 秒的額外延遲，如果發現偶爾會重播自己，把 `guard` 調到 `1.0`～`1.5`。

---

## 6. 設定與參數

不改也能用。想調整時，把資料夾裡的 `voice-pe-echo.example.toml` 複製一份並改名為 **`voice-pe-echo.toml`**，用記事本修改；
或在命令列指定（命令列優先）。主機與金鑰也可以用環境變數 `VOICE_PE_HOST`、`VOICE_PE_KEY` 提供。

| 設定檔名稱 | 命令列 | 預設 | 說明 |
|---|---|---|---|
| `host` | `--host` | 自動搜尋 | Voice PE 的 IP 或主機名稱（如 `home-assistant-voice-0a1b2c.local`）。 |
| `port` | `--port` | 6053 | ESPHome API 連接埠，通常不用改。 |
| `key` | `--key` | 無 | API 加密金鑰。剛買來的 Voice PE 沒有金鑰，請留空；只有加入過 Home Assistant 才需要（見附錄）。 |
| `output_device` | `--output-device` | 系統預設 | 播放裝置，填 `--list-devices` 顯示的編號或名稱的一部分（例如 `"耳機"`）。 |
| `volume` | `--volume` | 1.0 | 播放音量倍率。 |
| `no_normalize` | `--no-normalize` | false | 設為 true 就不自動調整音量，保留原始大小。 |
| `save_dir` | `--save-dir` | 不存 | 把每句話存成 WAV 檔的資料夾。 |
| `guard` | `--guard` | 0.6 | 播放後再忽略麥克風幾秒（防回授）。 |
| `silence` | `--silence` | 0.8 | 安靜幾秒算一句話結束。 |
| `max_sentence` | `--max-sentence` | 20 | 一句話最長秒數。 |
| `threshold` | `--threshold` | 0.5 | 語音判斷門檻（0～1），越高越不敏感。 |
| `vad` | `--vad` | auto | 語音偵測方式：`silero`（神經網路，準確，與 Home Assistant 相同）或 `energy`（音量判斷，較不準）。`auto` 會優先用 silero。 |
| `no_led` | `--no-led` | false | 設為 true 就不用燈環顯示收音狀態。 |
| `no_meter` | `--no-meter` | false | 設為 true 就不顯示最下面的即時音量列。 |
| — | `-v` / `-vv` | — | 顯示除錯訊息；`-vv` 會連 Voice PE 本身的日誌一起顯示。 |

---

## 7. 疑難排解

| 狀況 | 可能原因與解法 |
|---|---|
| 「找不到 Voice PE」 | 確認 Voice PE 有通電且已連上 Wi-Fi（第 2 節）；電腦與它在同一個網路（不是訪客網路）；Windows 防火牆有允許 Python。仍不行就用 `--host` 指定 IP（可在路由器的「已連線裝置」清單查到，名稱是 `home-assistant-voice-xxxxxx`）。 |
| 「找到多台 Voice PE」 | 用 `--host` 指定要用哪一台。 |
| 「這版韌體不支援自動開始收音」 | 每次啟動後說一次「Okay Nabu」或按一下中央按鈕；或用第 2 節方法 1 更新韌體，以後就不用。 |
| 「Voice PE 沒有開始傳送聲音」 | 可以說一次「Okay Nabu」或按一下中央按鈕手動開始。如果 Voice PE 曾加入 Home Assistant，見附錄。 |
| 一直顯示「Voice PE 靜音中」 | Voice PE 側邊的實體靜音開關被打開了（燈環上亮兩顆紅燈），切回來即可。 |
| 音量列一直沒反應 | 看狀態欄：「等待開始收音」表示還沒開始串流（見上面幾項）；「收音中」但音量很低，請靠近一點說話。 |
| 說話了但沒有偵測到 | 靠近 Voice PE 一點；確認沒有靜音；把 `threshold` 調低到 0.3。 |
| 電視、背景人聲一直被錄下來 | 把 `threshold` 調高到 0.7，或讓 Voice PE 離電視遠一點。（偵測的是「人聲」，電視裡的人說話一樣會被當成說話。） |
| 一句話被切成好幾段 | 把 `silence` 調大，例如 1.2。 |
| 句子結束後要等很久才播放 | 把 `silence` 調小，例如 0.6。 |
| 自己的聲音一直重播（回授） | 調大 `guard`（1.0～1.5）、降低喇叭音量、拉開距離，或改用耳機。 |
| 播放的聲音太小聲／太大聲 | 調整電腦音量或 `volume`。 |
| 聽不到播放 | 用 `--list-devices` 確認輸出裝置，再用 `--output-device` 指定。 |
| Linux：「找不到 PortAudio 音效函式庫」 | 執行 `sudo apt install libportaudio2`。 |
| 「這台 Voice PE 設有 API 加密金鑰」 | 這台 Voice PE 加入過 Home Assistant，見附錄。 |
| 「加密金鑰不正確」 | 金鑰複製不完整（注意結尾的 `=`），或是別台裝置的金鑰；若 Voice PE 恢復過原廠設定，請把 `key` 清空。 |
| 「語音助理正被另一個程式使用（Home Assistant …）」 | Home Assistant 還連著 Voice PE，見附錄的「停用裝置」。停用後不用重開程式。 |

還是解決不了的話，用 `run.bat -vv` 執行，把畫面上的訊息存下來，方便判斷問題（如果有金鑰，記得先遮掉）。

---

## 附錄：Voice PE 已經加入 Home Assistant

如果你之前已經照官方流程，用 Home Assistant App 設定過這台 Voice PE，會多兩個狀況：

1. **加密金鑰**：Home Assistant 加入 Voice PE 時，會幫它設定一組隨機的 API 加密金鑰，本程式需要同一把金鑰才能連線。
2. **一次只能一個**：Voice PE 一次只接受一個「語音助理伺服器」。Home Assistant 連著的時候，本程式拿不到麥克風。

有兩種處理方式，擇一即可。

### 做法甲：恢復原廠設定，改用不需要 Home Assistant 的方式（最簡單）

1. 先在 Home Assistant 把這台裝置**停用或刪除**（方法見下面〈A-3〉），避免 HA 一直嘗試連線。
2. **按住 Voice PE 的中央按鈕約 22 秒**：10 秒時會出現警告音與燈號，請繼續按住；聽到確認音、燈環變紅後放開。
3. 恢復原廠會清掉 Wi-Fi 與金鑰。接著照〈[第 2 節](#2-讓-voice-pe-連上-wi-fi)〉重新設定 Wi-Fi，之後就和剛買來的一樣，不需要金鑰。

之後若想再交給 Home Assistant，在 HA 刪除舊的 Voice PE 裝置再重新加入即可。

### 做法乙：保留 Home Assistant 的設定

適合想同時保留 Home Assistant 裡的區域、自動化等設定的人。

#### A-1 更新韌體

1. 打開 Home Assistant → **設定**（Settings）。
2. 如果最上方出現「更新」並列出 Home Assistant Voice 的韌體，按進去 → **安裝**。
   也可以到 **設定 → 裝置與服務 → ESPHome → Home Assistant Voice xxxxxx**，在裝置頁面的「韌體」項目檢查是否有更新。
3. 更新約需幾分鐘，完成前不要拔電源。

#### A-2 取得加密金鑰

這個步驟只需要做一次。金鑰是一串約 44 個字元、結尾通常是 `=` 的文字，例如 `kXsH1vG0...Q8w=`。
Home Assistant 介面上看不到它，要從 Home Assistant 的設定資料夾讀出來。

**最簡單的方法：Terminal & SSH 附加元件（Home Assistant OS）**

1. Home Assistant → **設定 → 附加元件**（Add-ons / Apps）→ **附加元件商店** → 安裝 **Terminal & SSH** → 啟動 → **開啟網頁介面**。
2. 在終端機輸入：

   ```sh
   cat /config/.storage/esphome.encryption_keys
   ```

   （如果顯示找不到檔案，改試 `cat /homeassistant/.storage/esphome.encryption_keys`。）

3. 會看到類似：

   ```json
   {
     "version": 1,
     "key": "esphome.encryption_keys",
     "data": {
       "keys": {
         "aa:bb:cc:dd:ee:ff": "kXsH1vG0...Q8w="
       }
     }
   }
   ```

   `"aa:bb:cc:dd:ee:ff"` 是裝置的 MAC 位址，後面引號內就是金鑰。
   只有一台 ESPHome 裝置時就是它；有多台時，用本程式的 `run.bat --discover` 可以看到 Voice PE 的 MAC 位址來對照。

4. 如果上面的檔案不存在，可以改找 Home Assistant 的設定紀錄：

   ```sh
   grep -n -B 4 -A 2 '"noise_psk"' /config/.storage/core.config_entries
   ```

   找到旁邊有 `home-assistant-voice-xxxxxx` 字樣的那一筆，`"noise_psk": "..."` 引號內就是金鑰。

**其他方法**：只要能讀到 Home Assistant 設定資料夾裡 `.storage/esphome.encryption_keys` 這個檔案都可以，
例如 Studio Code Server 附加元件；Docker／Core 安裝方式則直接在主機上的設定資料夾找。

取得後，把 `voice-pe-echo.example.toml` 複製成 `voice-pe-echo.toml`，填入：

```toml
key = "kXsH1vG0...Q8w="
```

> 金鑰等同 Voice PE 的密碼，請不要貼到網路上。本專案的 `.gitignore` 已經排除放金鑰的設定檔 `voice-pe-echo.toml`。

#### A-3 每次使用本程式前，在 Home Assistant 停用這台 Voice PE

1. Home Assistant → **設定 → 裝置與服務**（Devices & services）→ 點 **ESPHome**。
2. 找到 **Home Assistant Voice xxxxxx** 那一列，按右邊的 **⋮** → **停用**（Disable）。

停用只是暫時讓 Home Assistant 放開 Voice PE，所有設定（區域、自動化）都還在。

> 如果忘了停用，程式會顯示「Voice PE 的語音助理正被另一個程式使用（Home Assistant …）」，並每 30 秒重試一次；
> 你停用之後程式會自動接手，不必重開。

#### A-4 用完之後：把 Voice PE 還給 Home Assistant

1. 在程式視窗按 **Ctrl+C** 結束（程式會先通知 Voice PE 關閉麥克風，再斷線）。
2. Home Assistant → **設定 → 裝置與服務 → ESPHome** → Home Assistant Voice xxxxxx 的 **⋮ → 啟用**（Enable）。
3. 如果你在程式執行期間就已經啟用了，請改按 **⋮ → 重新載入**（Reload），語音助理才會重新接回 Home Assistant。

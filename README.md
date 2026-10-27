# Home Assistant Voice Preview Edition echo

在電腦上執行後 **24 小時透過 Voice PE 收音**：對 Voice PE 說一句話，電腦喇叭就把原話播出來，直到關閉程式。
這是熟悉 Voice PE 的第一步——確認它聽得到你、聽到的是什麼聲音。

- 不需要安裝 Home Assistant，也不需要改韌體：剛買來的 Voice PE 連上 Wi-Fi 就能用
- 不需要喚醒詞，啟動後一直收音
- 內建防回授（電腦喇叭的聲音不會被無限重播）
- Voice PE 的燈環與終端機的音量列即時顯示收音狀態
- 斷線、重開機、按鈕、靜音都會自動恢復

## 快速開始

以剛買來的 Voice PE、電腦上沒有 Home Assistant 為例：

1. **讓 Voice PE 連上 Wi-Fi**：用 USB-C 線接上電腦，以 Chrome／Edge 打開官方安裝頁面
   <https://esphome.github.io/home-assistant-voice-pe/> → CONNECT → 設定 Wi-Fi（可順便更新成最新官方韌體）。
   也可以用藍牙設定，詳見 **[使用手冊 §2](docs/user-guide.md#2-讓-voice-pe-連上-wi-fi)**。
2. 安裝 [Python 3.11 以上](https://www.python.org/downloads/)（Windows 安裝時勾選「Add python.exe to PATH」）。
3. 啟動：Windows 雙擊 `run.bat`；macOS／Linux 執行 `./run.sh`（Linux 需先 `sudo apt install libportaudio2`）。
   程式會自動在區網找到 Voice PE，不需要任何設定。
4. 聽到 Voice PE 的提示音、燈環開始旋轉後，說一句話，電腦就會重播。按 `Ctrl+C` 結束。

Voice PE 已經加入 Home Assistant？請看 [使用手冊附錄](docs/user-guide.md#附錄voice-pe-已經加入-home-assistant)。

## 文件

- [使用手冊](docs/user-guide.md)：Voice PE 連上 Wi-Fi、安裝、使用、擺放與防回授、參數、疑難排解；附錄說明已加入 Home Assistant 的情況
- [設計說明](docs/design.md)：為什麼這樣設計（收音方式、免喚醒詞、回授、斷句、測試）

## 專案結構

```
voice_pe_echo/
  cli.py         命令列、設定檔、啟動流程
  discovery.py   用 mDNS 在區網搜尋 Voice PE
  device.py      ESPHome API 連線：扮演語音助理伺服器、保持收音、重連
  app.py         收音 → 斷句 → 播放，以及防回授閘門
  segmenter.py   把連續聲音切成「一句一句」
  vad.py         語音偵測（Silero／音量備援）
  player.py      從電腦喇叭播放
  console.py     終端機的即時狀態列
tests/           單元測試與模擬 Voice PE（fake_voice_pe.py）
```

## 開發

```sh
python -m venv .venv && . .venv/bin/activate
pip install -e ".[test]"
pytest
```

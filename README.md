# Home Assistant Voice Preview Edition echo

在電腦上執行後 **24 小時透過 Voice PE 收音**：對 Voice PE 說一句話，電腦喇叭就把原話播出來，直到關閉程式。
這是熟悉 Voice PE 的第一步——確認它聽得到你、聽到的是什麼聲音。

- 不需要刷韌體，原廠 Voice PE 即可
- 不需要喚醒詞，啟動後一直收音
- 內建防回授（電腦喇叭的聲音不會被無限重播）
- Voice PE 的燈環與終端機的音量列即時顯示收音狀態
- 斷線、重開機、按鈕、靜音都會自動恢復

## 快速開始

1. **Voice PE 設定**：Voice PE 已加入 Home Assistant 的話，先更新韌體、取得加密金鑰，並在 HA 暫時停用這台裝置。
   詳細步驟見 **[使用手冊 §2](docs/user-guide.md#2-voice-pe-需要的設定)**。
2. 安裝 [Python 3.11 以上](https://www.python.org/downloads/)（Windows 安裝時勾選「Add python.exe to PATH」）。
3. 把 `voice-pe-echo.example.toml` 複製成 `voice-pe-echo.toml`，填入金鑰（沒有金鑰就留空）。
4. 啟動：Windows 雙擊 `run.bat`；macOS／Linux 執行 `./run.sh`（Linux 需先 `sudo apt install libportaudio2`）。
5. 聽到 Voice PE 的提示音、燈環開始旋轉後，說一句話，電腦就會重播。按 `Ctrl+C` 結束。

## 文件

- [使用手冊](docs/user-guide.md)：Voice PE 設定、安裝、使用、擺放與防回授、參數、疑難排解
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

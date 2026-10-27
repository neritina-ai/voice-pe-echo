# 全雙工語音模型比較

> 整理日期：2026 年 10 月。這個領域變化很快，以下資訊以整理當時的網路資料為準，使用前請再確認各模型官方說明。

**全雙工語音模型**（full-duplex spoken dialogue model）是「語音直接對語音」的模型：使用者還在講話時，模型就已經在聽、在推理，也能同時開口、被插話、發出「嗯嗯」之類的附和聲。
它取代了傳統 STT → LLM → TTS 的三段式流程。

目前**沒有一個公認的總排行榜**，所以很難斷言誰是 SOTA（state of the art，目前最強）。

## 比較表

| 模型 | 開放／免費 | 中文 | 重點 |
|---|---|---|---|
| **NVIDIA PersonaPlex** | 開放權重，免費 | 沒查到資料，原版 Moshi 不支援，可能也不支援 | 以 Moshi 為基礎（7B），加上可以指定聲音和角色。在 NVIDIA 自己做的評測裡，自然度與插話處理都比 Moshi 好，自然度分數甚至略高於 Gemini Live。 |
| **Kyutai Moshi** | 開放權重（CC-BY），免費 | 不支援 | 這類開源架構的開山之作，PersonaPlex 就是改良它。聲音與角色固定。 |
| **MiniCPM-o 4.5**（OpenBMB） | 開放權重（列為 Apache-2.0），免費 | **支援中英雙語** | 全雙工，可同時處理即時影像和聲音，邊聽邊回答、互不阻塞。 |
| **NVIDIA NemotronLabs VoiceChat** | 開放 | 未確認 | 2026 年的新開源全雙工模型，還能呼叫工具，目前查不到評測數字。 |
| **Qwen3-Omni**（阿里巴巴） | 開放 | 支援 | 能做即時語音對話，但依 OpenBMB 的比較表，它是**半雙工**（輪流講），不是全雙工。 |
| **Google Gemini Live** | 付費 API | 支援 | 商業產品中最常被拿來當比較基準。 |
| **OpenAI Realtime** | 付費 API | 支援 | 可以插話打斷，但本質比較接近「輪流講 + 打斷」，不是真正同時聽說。 |
| **Seeduplex**（字節跳動） | 封閉，只有 API | 支援 | 號稱原生全雙工。 |

## 評測數字（PersonaPlex 對 Moshi）

以下數字主要來自 NVIDIA 自己的評測，不同文章引用的數字不太一致，僅供參考：

| 指標 | PersonaPlex | Moshi | 備註 |
|---|---|---|---|
| 對話自然度 MOS | 3.90 | 3.11 | Gemini Live 為 3.72 |
| 插話處理成功率 | 100% | 60.6% | |
| 回應延遲 | 約 0.17～0.2 秒 | 約 0.27 秒 | |
| 角色遵循（0～5 分，Full-Duplex-Bench） | 4.29 | 0.77～1.26 | 各來源數字不同 |

## 怎麼選

- **免費 + 中文**：目前最有希望的是 **MiniCPM-o 4.5**，因為 PersonaPlex 和 Moshi 主要以英文為主。
- **想看客觀比較**：學術界在用 **Full-Duplex-Bench** 這一系列評測（v1 輪流說話、v1.5 重疊語音、v2 多輪對話、v3 工具使用），可以追蹤它的排行榜，以及 [Awesome-Full-Duplex-SDM](https://github.com/Ruiqi-Yan/Awesome-Full-Duplex-SDM) 清單，裡面會標出哪些是開放權重。
- **要注意的地方**：
  - 有研究指出，PersonaPlex 在被插話時比較容易被誘導回答不該回答的內容，安全性有疑慮。
  - 這類模型都需要不錯的 NVIDIA 顯示卡才能即時運作。

## 和 Voice PE 的關係

全雙工模型的輸入、輸出都是**連續音訊**，可以接在本專案的架構上：

- Voice PE 的麥克風串流本來就是連續不斷的（見 [設計說明](design.md)）；
- 模型的語音輸出可以用 HTTP 串流（FLAC，chunked 傳輸）交給 Voice PE 的媒體播放器播放，不需要 Home Assistant，也不需要改韌體；
- Voice PE 的 XMOS 晶片可以消掉自己喇叭的回音，理論上很適合做「可以互相插話」的對話。

實際效果還要看電腦的顯示卡跑不跑得動，以及實機上的串流延遲。

## 資料來源

- [Nvidia releases open model PersonaPlex (The Decoder)](https://the-decoder.com/nvidia-open-sources-personaplex-a-voice-ai-that-listens-and-talks-at-the-same-time/)
- [PersonaPlex: Full-Duplex Voice Without the Fixed Persona](https://www.getmaxim.ai/blog/personaplex-full-duplex-voice-without-the-fixed-persona/)
- [NVIDIA PersonaPlex explained](https://pasqualepillitteri.it/en/news/26826/nvidia-personaplex-explained-full-duplex-voice-ai)
- [How to Run NVIDIA PersonaPlex Locally](https://themenonlab.blog/blog/nvidia-personaplex-full-duplex-voice-ai-how-to-guide)
- [Speech-to-Speech Models in 2026 (Sopyła)](https://ai.ksopyla.com/posts/voice-to-voice-models-2026-review/)
- [Full-Duplex Voice Agents (Evalgent)](https://www.evalgent.com/blog/full-duplex-voice-agents)
- [NemotronLabs VoiceChat (arXiv)](https://arxiv.org/pdf/2609.21967)
- [Full-Duplex-Bench overview](https://www.emergentmind.com/topics/full-duplex-bench)
- [Awesome-Full-Duplex-SDM](https://github.com/Ruiqi-Yan/Awesome-Full-Duplex-SDM)
- [MiniCPM-o 4.5 (Hugging Face)](https://huggingface.co/openbmb/MiniCPM-o-4_5)
- [MiniCPM-o 4.5 AWQ (Friendli)](https://friendli.ai/models/openbmb/MiniCPM-o-4_5-awq)

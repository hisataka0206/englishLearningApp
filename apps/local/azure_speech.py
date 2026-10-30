"""Azure AI Speech - Pronunciation Assessment client (stdlib only).

REST (short audio, <=30s) 方式。録音音声と正解テキストを送ると、
単語ごと・音素ごとの精度スコアが返る。中国語(zh-CN)では音素がSAPI表記
（例: h ao3）で返るため、声調番号を比較して声調誤りも判定できる。

必要な設定（config.json の azure セクション）:
  key    : Speech リソースのキー
  region : 例 japaneast / eastus
"""

import base64
import json
import re
import urllib.request
import urllib.error


class AzureSpeech:
    def __init__(self, cfg):
        self.key = (cfg or {}).get("key", "")
        self.region = (cfg or {}).get("region", "japaneast")

    def configured(self):
        return bool(self.key and "PUT_YOUR" not in self.key)

    def assess(self, audio_bytes, reference_text, lang="zh-CN", content_type=None):
        """録音を評価して結果JSONを返す。audio_bytes は WAV(16k mono) か WebM/OGG。"""
        if not self.configured():
            return None, "Azure未設定（config.jsonのazure.keyを確認）"
        params = {
            "ReferenceText": reference_text,
            "GradingSystem": "HundredMark",
            "Granularity": "Phoneme",     # 単語＋音素レベルまで取得
            "Dimension": "Comprehensive",
            "EnableProsodyAssessment": True,
        }
        hdr = base64.b64encode(json.dumps(params).encode("utf-8")).decode()
        url = (f"https://{self.region}.stt.speech.microsoft.com/speech/recognition"
               f"/conversation/cognitiveservices/v1?language={lang}")
        ctype = content_type or "audio/wav; codecs=audio/pcm; samplerate=16000"
        req = urllib.request.Request(url, data=audio_bytes, method="POST")
        req.add_header("Ocp-Apim-Subscription-Key", self.key)
        req.add_header("Pronunciation-Assessment", hdr)
        req.add_header("Content-Type", ctype)
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8")), None
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8")[:300]
            except Exception:
                pass
            return None, f"Azure HTTP {e.code}: {body}"
        except Exception as e:
            return None, f"Azure接続エラー: {e}"


    def recognize(self, audio_bytes, lang="zh-CN", content_type=None):
        """参照テキストなしの音声認識（実際に何と発音したかを得る）。"""
        if not self.configured():
            return "", "Azure未設定"
        url = (f"https://{self.region}.stt.speech.microsoft.com/speech/recognition"
               f"/conversation/cognitiveservices/v1?language={lang}")
        req = urllib.request.Request(url, data=audio_bytes, method="POST")
        req.add_header("Ocp-Apim-Subscription-Key", self.key)
        req.add_header("Content-Type",
                       content_type or "audio/wav; codecs=audio/pcm; samplerate=16000")
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                res = json.loads(r.read().decode("utf-8"))
            return res.get("DisplayText", ""), None
        except Exception as e:
            return "", str(e)


    # ------------------------------------------------------------ 音声合成
    VOICES = {"zh": "zh-CN-XiaoxiaoNeural", "en": "en-US-JennyNeural",
              "ja": "ja-JP-NanamiNeural"}

    def synthesize(self, lines, lang="zh", rate=1.0, gap_ms=350, voice=None):
        """文のリストをつなげた1本のMP3にして返す（通し読みのダウンロード用）。

        1リクエストあたりの上限があるため、文字数でまとめて分割送信し、
        返ってきたMP3を順につなぐ（MP3はフレーム連結で再生できる）。
        """
        if not self.configured():
            return None, "Azure未設定（config.jsonのazure.keyを確認）"
        lines = [re.sub(r"[\s/|｜／]+", "", x) for x in (lines or [])]
        lines = [x for x in lines if x]
        if not lines:
            return None, "読み上げる文がありません"
        name = voice or self.VOICES.get(lang, self.VOICES["zh"])
        xml_lang = name[:5]
        pct = int(round((float(rate) - 1.0) * 100))
        rate_attr = f"{pct:+d}%"

        chunks, cur, n = [], [], 0
        for s in lines:
            if cur and n + len(s) > 700:   # 1回あたりの文字数の目安
                chunks.append(cur)
                cur, n = [], 0
            cur.append(s)
            n += len(s)
        if cur:
            chunks.append(cur)

        out = bytearray()
        for ch in chunks:
            body = "".join(
                f"<prosody rate='{rate_attr}'>{self._xml(s)}</prosody>"
                f"<break time='{int(gap_ms)}ms'/>" for s in ch)
            ssml = (f"<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' "
                    f"xml:lang='{xml_lang}'><voice name='{name}'>{body}</voice></speak>")
            data, err = self._tts(ssml)
            if err:
                return None, err
            out += data
        return bytes(out), None

    @staticmethod
    def _xml(s):
        return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                 .replace('"', "&quot;").replace("'", "&apos;"))

    def _tts(self, ssml):
        url = f"https://{self.region}.tts.speech.microsoft.com/cognitiveservices/v1"
        req = urllib.request.Request(url, data=ssml.encode("utf-8"), method="POST")
        req.add_header("Ocp-Apim-Subscription-Key", self.key)
        req.add_header("Content-Type", "application/ssml+xml")
        req.add_header("X-Microsoft-OutputFormat", "audio-24khz-48kbitrate-mono-mp3")
        req.add_header("User-Agent", "english-learning-app")
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read(), None
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8")[:200]
            except Exception:
                pass
            return None, f"Azure TTS HTTP {e.code}: {body}"
        except Exception as e:
            return None, f"Azure TTS接続エラー: {e}"


TONE_RE = re.compile(r"([a-zü]+)([1-5])", re.I)

# 声調記号つき母音 → 声調番号
_TONE_MARKS = {
    "1": "āēīōūǖĀĒĪŌŪǕ", "2": "áéíóúǘÁÉÍÓÚǗ",
    "3": "ǎěǐǒǔǚǍĚǏǑǓǙ", "4": "àèìòùǜÀÈÌÒÙǛ",
}



def tone_from_pinyin(py):
    """拼音（声調記号 or 数字）から声調番号を返す。無声調(軽声)は '5'。"""
    if not py:
        return ""
    m = TONE_RE.search(py)
    if m:
        return m.group(2)
    for tone, marks in _TONE_MARKS.items():
        if any(ch in marks for ch in py):
            return tone
    return "5" if any("a" <= c.lower() <= "z" for c in py) else ""


def _tone_of(phonemes):
    """SAPI音素列から声調番号を拾う（例: ['h','ao3'] や ['wo 3'] -> '3'）"""
    for p in phonemes:
        s = re.sub(r"\s+", "", str(p))
        m = TONE_RE.fullmatch(s) or TONE_RE.search(s)
        if m:
            return m.group(2)
    return ""


def summarize(result, expected_pairs=None):
    """Azureの生レスポンスを、アプリで使いやすい形へ整形する。

    expected_pairs: [[文字, 期待拼音], ...]（中国語のみ。声調比較に使う）
    返り値: {scores, words:[{word, score, error, tone_said, tone_expected, tone_error}]}
    """
    nbest = (result or {}).get("NBest") or []
    if not nbest:
        return {"ok": False, "error": "認識できませんでした（もう一度録音してください）"}
    top = nbest[0]
    # REST APIはスコアがNBest直下、SDKは PronunciationAssessment 配下。両対応。
    pa = top.get("PronunciationAssessment") or top
    words = []
    for w in top.get("Words", []):
        wpa = w.get("PronunciationAssessment") or w
        # 音素（中国語は音節＋声調, 英語は個々の音）ごとのスコア
        phs = [[p.get("Phoneme", ""), round(p.get("AccuracyScore", 0))]
               for p in (w.get("Phonemes") or [])]
        score = round(wpa.get("AccuracyScore", 0))
        etype = wpa.get("ErrorType", "None")
        # いちばんスコアが低い音＝弱点（正解の読みなので「本来こう読む」も分かる）
        worst = min(phs, key=lambda x: x[1]) if phs else None
        words.append({
            "word": w.get("Word", ""),
            "score": score,
            "error": etype,
            "phonemes": [p[0] for p in phs],
            "phoneme_scores": phs,
            "worst": {"name": worst[0], "score": worst[1]} if worst else None,
            "worst_tone": _tone_of([worst[0]]) if worst else "",
        })
    return {
        "ok": True,
        "recognized": top.get("Display", ""),
        "scores": {
            "pron": round(pa.get("PronScore", 0)),
            "accuracy": round(pa.get("AccuracyScore", 0)),
            "fluency": round(pa.get("FluencyScore", 0)),
            "completeness": round(pa.get("CompletenessScore", 0)),
            "prosody": round(pa.get("ProsodyScore", 0)) if pa.get("ProsodyScore") else None,
        },
        "words": words,
    }

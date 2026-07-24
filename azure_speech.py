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
    # 句読点は拼音が無くAzureの単語列にも出てこないため、拼音のある文字だけで対応付ける
    exp_py = [p[1] for p in (expected_pairs or []) if p[1]]
    exp_idx = 0
    for w in top.get("Words", []):
        wpa = w.get("PronunciationAssessment") or w
        phs = [p.get("Phoneme", "") for p in (w.get("Phonemes") or [])]
        said_tone = _tone_of(phs)
        score = round(wpa.get("AccuracyScore", 0))
        etype = wpa.get("ErrorType", "None")
        exp_tone = ""
        if exp_py:
            word = w.get("Word", "")
            n = sum(1 for ch in word if "一" <= ch <= "鿿" or ch.isdigit()) or 1
            if exp_idx < len(exp_py):
                exp_tone = tone_from_pinyin(exp_py[exp_idx])
            exp_idx += n
        # 発音されなかった語（Omission/スコア0）は声調判定の対象外
        spoken = etype not in ("Omission", "Insertion") and score > 0
        words.append({
            "word": w.get("Word", ""),
            "score": score,
            "error": etype,
            "phonemes": phs,
            "tone_said": said_tone,
            "tone_expected": exp_tone,
            "tone_error": bool(spoken and said_tone and exp_tone and said_tone != exp_tone),
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

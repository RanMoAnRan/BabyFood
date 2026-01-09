from deep_translator import GoogleTranslator

# 简单的内存缓存，避免重复翻译相同的短语
_CACHE = {}
_TRANSLATORS = {}


def _get_translator(dest: str) -> GoogleTranslator:
    key = str(dest or "zh-CN")
    tr = _TRANSLATORS.get(key)
    if tr is None:
        tr = GoogleTranslator(source="auto", target=key)
        _TRANSLATORS[key] = tr
    return tr

def translate_text(text: str, dest: str = "zh-CN") -> str:
    if not text:
        return ""
    
    # 简单的预处理：如果是数字或简单的单位，可能不需要翻译
    if text.isdigit():
        return text

    key = f"{text}_{dest}"
    if key in _CACHE:
        return _CACHE[key]

    try:
        # 使用 Google Translator (free)
        # 注意：大量频繁调用可能会被暂时限制
        translator = _get_translator(dest)
        # 限制文本长度，避免出错
        if len(text) > 4500:
            text = text[:4500]
        
        res = translator.translate(text)
        
        # 简单的后处理
        if res:
            _CACHE[key] = res
            return res
        return text
    except Exception as e:
        print(f"Translation error for '{text[:20]}...': {e}")
        return text

def translate_list(texts: list[str], dest: str = "zh-CN") -> list[str]:
    # translate_batch 仍会逐条调用 translate，但可复用同一个 translator 实例
    if not texts:
        return []
    translator = _get_translator(dest)
    out = []
    for t in texts:
        if not t:
            out.append("")
            continue
        key = f"{t}_{dest}"
        if key in _CACHE:
            out.append(_CACHE[key])
            continue
        try:
            res = translator.translate(t if len(t) <= 4500 else t[:4500])
            out.append(res or t)
            if res:
                _CACHE[key] = res
        except Exception as e:
            print(f"Translation error for '{t[:20]}...': {e}")
            out.append(t)
    return out

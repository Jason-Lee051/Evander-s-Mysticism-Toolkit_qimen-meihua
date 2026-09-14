"""
core/llm/analyzer.py - 调用 LLM 进行分析（支持流式和非流式）

说明：思考型模型（如 DeepSeek 思考模式）会把思考内容计入 max_tokens，
若思考占满配额，正文将为空——表现为界面一直停留在"正在思考"、没有任何
流式输出。本模块统一处理该问题：按模型预判关闭思考、参数不兼容时自动回退、
仅收到思考无正文时自动换方式重试，最终仍无正文则给出明确提示。
"""
import json
import os
from openai import OpenAI
from .prompt_templates import (
    format_qimen_result, build_qimen_prompt,
    format_meihua_result, build_meihua_prompt
)

DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-flash"

NO_THINK_BODY = {"reasoning_effort": "none"}

EMPTY_REPLY_HINT = (
    "（模型未返回正文内容：思考过程可能占满了 max_tokens。\n"
    "建议：打开「设置 → LLM API 设置」，把 max_tokens 调大（建议 8000 以上），"
    "或改用非思考型模型后重试。）"
)


def load_config(config_path: str = "config/llm_config.json") -> dict:
    """加载 LLM 配置"""
    if not os.path.exists(config_path):
        return {
            "api_key": "",
            "base_url": DEFAULT_BASE_URL,
            "model": DEFAULT_MODEL,
            "max_tokens": 4000,
            "temperature": 0.7
        }
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    return config


def _extra_body_for(model: str):
    """
    针对 DeepSeek 思考型模型默认开启思考的问题，请求体关闭思考，避免思考
    占满 max_tokens 导致正文为空（现象：界面停留在"正在思考"、无流式输出）。

    - 覆盖 deepseek-flash / deepseek-v4 / deepseek-chat 等思考型模型
    - reasoner（R1）系列必须思考，不发送该参数
    - 非 deepseek 模型不发送，保持原有行为
    若服务端不支持该参数，_stream_chat 会自动去掉参数重试。
    """
    m = (model or "").lower()
    if m.startswith("deepseek") and "reasoner" not in m:
        return dict(NO_THINK_BODY)
    return None


def _delta_text(delta):
    """从流式 delta 中提取 (正文, 思考) 文本，兼容不同 SDK 版本"""
    reasoning = getattr(delta, "reasoning_content", None)
    if reasoning is None:
        extra = getattr(delta, "model_extra", None)
        if extra:
            reasoning = extra.get("reasoning_content")
    return (delta.content or "", reasoning or "")


def _stream_chat(client, model: str, messages: list, config: dict):
    """
    统一的流式请求生成器：只产出正文文本。

    自动规避"思考型模型思考占满 max_tokens → 正文为空"：
      1) 按模型名预判并关闭思考（DeepSeek 思考系模型）
      2) 若服务端不支持该参数（请求异常）→ 去掉参数重试一次
      3) 若首轮只收到思考而无正文 → 换成关闭思考再试一次
    最终仍无正文时给出明确提示，而不是静默返回空内容。
    """
    max_tokens = config.get("max_tokens", 2000)
    temperature = config.get("temperature", 0.7)

    if _extra_body_for(model) is not None:
        # 先按预判关闭思考；若参数不被支持则回退为不带参数
        attempts = [dict(NO_THINK_BODY), None]
    else:
        # 常规请求；若仅返回思考无正文，再尝试关闭思考
        attempts = [None, dict(NO_THINK_BODY)]

    last_error = None
    for extra_body in attempts:
        got_content = False
        got_reasoning = False
        try:
            kwargs = dict(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=True,
            )
            if extra_body:
                kwargs["extra_body"] = extra_body
            response = client.chat.completions.create(**kwargs)
            for chunk in response:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta is None:
                    continue
                content, reasoning = _delta_text(delta)
                if reasoning:
                    got_reasoning = True
                if content:
                    got_content = True
                    yield content
        except Exception as e:
            last_error = e
            continue  # 换下一种请求方式重试

        if got_content:
            return
        # 无正文则进入下一轮：换用另一种请求方式再试
        # （有思考无正文 → 下一轮关闭思考；被静默截断 → 下一轮换参数）

    if last_error is not None:
        yield f"分析失败：{last_error}"
    else:
        yield EMPTY_REPLY_HINT


def _analyze_once(result_text: str, prompt: str, system_prompt: str,
                  config: dict, api_key: str, base_url: str, model: str) -> str:
    """非流式调用（供 analyze_qimen / analyze_meihua 复用）"""
    kwargs = dict(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        max_tokens=config.get("max_tokens", 2000),
        temperature=config.get("temperature", 0.7),
        stream=False
    )
    extra_body = _extra_body_for(model)
    if extra_body:
        kwargs["extra_body"] = extra_body
    client = OpenAI(api_key=api_key, base_url=base_url)
    try:
        response = client.chat.completions.create(**kwargs)
    except Exception:
        # 服务端不支持关闭思考参数 → 去掉参数重试
        if extra_body:
            kwargs.pop("extra_body", None)
            response = client.chat.completions.create(**kwargs)
        else:
            raise
    text = response.choices[0].message.content or ""
    return text if text else EMPTY_REPLY_HINT


# ---------- 奇门遁甲 ----------
def analyze_qimen(result: dict, matter: str, location: str,
                  api_key: str = None, base_url: str = None, model: str = None) -> str:
    """非流式分析，返回完整字符串（保留兼容）"""
    config = load_config()
    if api_key is None:
        api_key = config.get("api_key", "")
    if base_url is None:
        base_url = config.get("base_url", DEFAULT_BASE_URL)
    if model is None:
        model = config.get("model", DEFAULT_MODEL)

    if not api_key:
        return "错误：未配置 API Key，请在设置中填写后再试。"

    try:
        pan_text = format_qimen_result(result)
        prompt = build_qimen_prompt(pan_text, matter, location)
        return _analyze_once(pan_text, prompt,
                             "你是一位精通奇门遁甲的专业占卜师。",
                             config, api_key, base_url, model)
    except Exception as e:
        return f"分析失败：{str(e)}"


def analyze_qimen_stream(result: dict, matter: str, location: str,
                         api_key: str = None, base_url: str = None, model: str = None):
    """流式分析奇门遁甲"""
    config = load_config()
    if api_key is None:
        api_key = config.get("api_key", "")
    if base_url is None:
        base_url = config.get("base_url", DEFAULT_BASE_URL)
    if model is None:
        model = config.get("model", DEFAULT_MODEL)

    if not api_key:
        yield "错误：未配置 API Key，请在设置中填写后再试。"
        return

    try:
        pan_text = format_qimen_result(result)
        prompt = build_qimen_prompt(pan_text, matter, location)
    except Exception as e:
        yield f"分析失败：排盘数据格式化出错（{e}）"
        return

    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
    except Exception as e:
        yield f"分析失败：{str(e)}"
        return

    yield from _stream_chat(client, model, [
        {"role": "system", "content": "你是一位精通奇门遁甲的专业占卜师。"},
        {"role": "user", "content": prompt}
    ], config)


# ---------- 梅花易数 ----------
def analyze_meihua(gua_data: dict, question: str, background: str = "",
                   api_key: str = None, base_url: str = None, model: str = None) -> str:
    """非流式分析梅花易数"""
    config = load_config()
    if api_key is None:
        api_key = config.get("api_key", "")
    if base_url is None:
        base_url = config.get("base_url", DEFAULT_BASE_URL)
    if model is None:
        model = config.get("model", DEFAULT_MODEL)

    if not api_key:
        return "错误：未配置 API Key"

    try:
        pan_text = format_meihua_result(gua_data)
        prompt = build_meihua_prompt(pan_text, question, background)
        return _analyze_once(pan_text, prompt,
                             "你是一位精通《梅花易数》的资深易学专家。",
                             config, api_key, base_url, model)
    except Exception as e:
        return f"分析失败：{str(e)}"


def analyze_meihua_stream(gua_data: dict, question: str, background: str = "",
                          api_key: str = None, base_url: str = None, model: str = None):
    """流式分析梅花易数"""
    config = load_config()
    if api_key is None:
        api_key = config.get("api_key", "")
    if base_url is None:
        base_url = config.get("base_url", DEFAULT_BASE_URL)
    if model is None:
        model = config.get("model", DEFAULT_MODEL)

    if not api_key:
        yield "错误：未配置 API Key"
        return

    try:
        pan_text = format_meihua_result(gua_data)
        prompt = build_meihua_prompt(pan_text, question, background)
    except Exception as e:
        yield f"分析失败：卦象数据格式化出错（{e}）"
        return

    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
    except Exception as e:
        yield f"分析失败：{str(e)}"
        return

    yield from _stream_chat(client, model, [
        {"role": "system", "content": "你是一位精通《梅花易数》的资深易学专家。"},
        {"role": "user", "content": prompt}
    ], config)

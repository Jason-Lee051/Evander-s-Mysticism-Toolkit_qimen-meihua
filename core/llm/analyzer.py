"""
core/llm/analyzer.py - 调用 LLM 进行分析（支持流式和非流式）
"""
import json
import os
from openai import OpenAI
from .prompt_templates import (
    format_qimen_result, build_qimen_prompt,
    format_meihua_result, build_meihua_prompt
)

def load_config(config_path: str = "config/llm_config.json") -> dict:
    """加载 LLM 配置"""
    if not os.path.exists(config_path):
        return {
            "api_key": "",
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
            "max_tokens": 2000,
            "temperature": 0.7
        }
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    return config

# ---------- 奇门遁甲（原有） ----------
def analyze_qimen(result: dict, matter: str, location: str,
                  api_key: str = None, base_url: str = None, model: str = None) -> str:
    """非流式分析，返回完整字符串（保留兼容）"""
    config = load_config()
    if api_key is None:
        api_key = config.get("api_key", "")
    if base_url is None:
        base_url = config.get("base_url", "https://api.deepseek.com/v1")
    if model is None:
        model = config.get("model", "deepseek-chat")

    if not api_key:
        return "错误：未配置 API Key，请在设置中填写后再试。"

    pan_text = format_qimen_result(result)
    prompt = build_qimen_prompt(pan_text, matter, location)

    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是一位精通奇门遁甲的专业占卜师。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=config.get("max_tokens", 2000),
            temperature=config.get("temperature", 0.7),
            stream=False
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"分析失败：{str(e)}"

def analyze_qimen_stream(result: dict, matter: str, location: str,
                         api_key: str = None, base_url: str = None, model: str = None):
    """流式分析奇门遁甲"""
    config = load_config()
    if api_key is None:
        api_key = config.get("api_key", "")
    if base_url is None:
        base_url = config.get("base_url", "https://api.deepseek.com/v1")
    if model is None:
        model = config.get("model", "deepseek-chat")

    if not api_key:
        yield "错误：未配置 API Key，请在设置中填写后再试。"
        return

    pan_text = format_qimen_result(result)
    prompt = build_qimen_prompt(pan_text, matter, location)

    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是一位精通奇门遁甲的专业占卜师。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=config.get("max_tokens", 2000),
            temperature=config.get("temperature", 0.7),
            stream=True
        )
        for chunk in response:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta is None:
                continue
            # 兼容推理型模型：内容可能在 reasoning_content（思考过程）
            text = delta.content or getattr(delta, "reasoning_content", None)
            if text:
                yield text
    except Exception as e:
        yield f"分析失败：{str(e)}"

# ---------- 梅花易数（新增） ----------
def analyze_meihua(gua_data: dict, question: str, background: str = "",
                   api_key: str = None, base_url: str = None, model: str = None) -> str:
    """非流式分析梅花易数"""
    config = load_config()
    if api_key is None:
        api_key = config.get("api_key", "")
    if base_url is None:
        base_url = config.get("base_url", "https://api.deepseek.com/v1")
    if model is None:
        model = config.get("model", "deepseek-chat")

    if not api_key:
        return "错误：未配置 API Key"

    pan_text = format_meihua_result(gua_data)
    prompt = build_meihua_prompt(pan_text, question, background)

    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是一位精通《梅花易数》的资深易学专家。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=config.get("max_tokens", 2000),
            temperature=config.get("temperature", 0.7),
            stream=False
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"分析失败：{str(e)}"

def analyze_meihua_stream(gua_data: dict, question: str, background: str = "",
                          api_key: str = None, base_url: str = None, model: str = None):
    """流式分析梅花易数"""
    config = load_config()
    if api_key is None:
        api_key = config.get("api_key", "")
    if base_url is None:
        base_url = config.get("base_url", "https://api.deepseek.com/v1")
    if model is None:
        model = config.get("model", "deepseek-chat")

    if not api_key:
        yield "错误：未配置 API Key"
        return

    pan_text = format_meihua_result(gua_data)
    prompt = build_meihua_prompt(pan_text, question, background)

    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是一位精通《梅花易数》的资深易学专家。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=config.get("max_tokens", 2000),
            temperature=config.get("temperature", 0.7),
            stream=True
        )
        for chunk in response:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta is None:
                continue
            # 兼容推理型模型：内容可能在 reasoning_content（思考过程）
            text = delta.content or getattr(delta, "reasoning_content", None)
            if text:
                yield text
    except Exception as e:
        yield f"分析失败：{str(e)}"
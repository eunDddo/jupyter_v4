from __future__ import annotations
from manufacturing_agent._common import *  # noqa: F401,F403
from manufacturing_agent.config import *  # noqa: F401,F403

def _json_object(raw: str) -> dict:
    """LLM 응답에서 첫 번째 JSON object를 견고하게 추출한다.
    코드펜스(```json)를 제거하고, 첫 '{'부터 balanced하게 닫히는 지점까지만 파싱한다.
    (기존 greedy 패턴은 산문/후행 텍스트의 닫는 괄호 때문에 정상 요청도 parse 실패시킬 수 있었다.)"""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    start = text.find("{")
    if start == -1:
        return json.loads(text)
    try:
        obj, _ = json.JSONDecoder().raw_decode(text, start)
        return obj
    except json.JSONDecodeError:
        end = text.rfind("}")
        return json.loads(text[start:end + 1])

# import * 가 밑줄(_x) 이름까지 가져오도록 명시 export
__all__ = [n for n in dir() if not n.startswith("__")]

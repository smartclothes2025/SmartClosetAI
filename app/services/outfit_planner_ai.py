import json
import logging
import os
import re
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field, ValidationError

try:
    import google.generativeai as genai
except ImportError:  # pragma: no cover
    genai = None  # type: ignore

logger = logging.getLogger(__name__)

COLOR_FAMILY_KEYWORDS = {
    "中性": ["白", "黑", "灰", "銀", "米", "奶", "象牙", "ivory", "gray", "black"],
    "卡其棕": ["卡其", "棕", "咖", "brown", "beige", "camel", "土"],
    "藍": ["藍", "blue", "海軍", "牛仔", "navy"],
    "紅粉": ["紅", "粉", "rose", "pink", "桃"],
    "綠": ["綠", "green", "橄欖", "olive", "墨綠", "軍綠"],
}

STORE_PALETTE_MAP = {
    "neutral": "中性",
    "khaki": "卡其棕",
    "blue": "藍",
    "pink": "紅粉",
    "green": "綠",
}

CATEGORY_CANONICAL_MAP = {
    "上衣": "top",
    "top": "top",
    "tops": "top",
    "shirt": "top",
    "sweater": "top",
    "tee": "top",
    "褲子": "bottom",
    "裙子": "bottom",
    "下身": "bottom",
    "bottom": "bottom",
    "bottoms": "bottom",
    "pants": "bottom",
    "shorts": "bottom",
    "dress": "dress",
    "洋裝": "dress",
    "外套": "outer",
    "outer": "outer",
    "outerwear": "outer",
    "coat": "outer",
    "jacket": "outer",
    "包包": "bag",
    "bag": "bag",
    "bags": "bag",
    "配件": "accessory",
    "accessory": "accessory",
    "accessories": "accessory",
    "shoes": "accessory",
    "鞋子": "accessory",
}


class OutfitItemRef(BaseModel):
    item_id: str = Field(..., description="對應來源資料的 id")
    source: Literal["wardrobe", "store"]


class OutfitRecommendation(BaseModel):
    id: str
    title: str
    items: List[OutfitItemRef]
    main_color_family5: Literal["中性", "卡其棕", "藍", "紅粉", "綠"]
    styles: List[str]
    reason: str


class OutfitPlannerResult(BaseModel):
    wardrobe_outfits: List[OutfitRecommendation]
    store_outfits: List[OutfitRecommendation]


@dataclass
class OutfitPlannerPayload:
    user_request: str
    today_main_color: str
    gender: str
    wardrobe_items: List[Dict[str, Any]]
    store_items: List[Dict[str, Any]]
    weather: Optional[Dict[str, Any]] = None


class OutfitPlannerAIService:
    """Central service that talks to Gemini and validates JSON output."""

    def __init__(self) -> None:
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.model_name = os.getenv("OUTFIT_PLANNER_MODEL", "gemini-1.5-flash")
        self._model = None

        if self.gemini_api_key and genai:
            try:
                genai.configure(api_key=self.gemini_api_key)
                self._model = genai.GenerativeModel(self.model_name)
                logger.info("OutfitPlannerAIService: Gemini model initialised (%s)", self.model_name)
            except Exception:  # pragma: no cover
                logger.exception("Failed to initialise Gemini model for outfit planner")
                self._model = None
        else:
            if not self.gemini_api_key:
                logger.warning("OutfitPlannerAIService: GEMINI_API_KEY not set")
            if not genai:
                logger.warning("OutfitPlannerAIService: google.generativeai not installed")

    @property
    def is_available(self) -> bool:
        return self._model is not None

    def generate_plan(
        self,
        payload: OutfitPlannerPayload,
        fallback_builder: Optional[callable] = None,
    ) -> Tuple[Optional[OutfitPlannerResult], str, Optional[str]]:
        """Return (result, source, raw_text)."""
        if not self.is_available:
            logger.warning("OutfitPlannerAIService: model unavailable, using fallback")
            if fallback_builder:
                return fallback_builder(), "fallback", None
            return None, "unavailable", None

        prompt = self._build_prompt(payload)
        try:
            response = self._model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.7,
                    "max_output_tokens": 2048,
                },
            )
            raw_text = self._extract_text(response)
            logger.debug("OutfitPlanner raw response: %s", raw_text[:400] if raw_text else "<empty>")
            plan = self._parse_response(raw_text)
            if plan:
                return plan, "ai", raw_text
        except Exception:  # pragma: no cover
            logger.exception("OutfitPlannerAIService: Gemini call failed")

        logger.info("OutfitPlannerAIService: falling back to rule-based result")
        if fallback_builder:
            return fallback_builder(), "fallback", None
        return None, "error", None

    def build_rule_based_plan(
        self,
        payload: OutfitPlannerPayload,
    ) -> OutfitPlannerResult:
        """Simple deterministic planner used when AI fails."""
        wardrobe_items = payload.wardrobe_items
        store_items = payload.store_items

        def pick_items(source_items: List[Dict[str, Any]], preferred: List[str]) -> List[Dict[str, Any]]:
            selected: List[Dict[str, Any]] = []
            remaining = source_items.copy()
            for cat in preferred:
                for item in remaining:
                    if item.get("category") == cat:
                        selected.append(item)
                        remaining.remove(item)
                        break
            return selected

        # Wardrobe outfit heuristics
        wardrobe_selection = pick_items(
            wardrobe_items,
            ["top", "bottom", "dress", "outer", "accessory"],
        )
        if not wardrobe_selection and wardrobe_items:
            wardrobe_selection = wardrobe_items[:2]

        store_selection = pick_items(
            store_items,
            ["top", "bottom", "dress", "outer", "bag", "accessory"],
        )
        if not store_selection and store_items:
            store_selection = store_items[:2]

        def to_reco(selection: List[Dict[str, Any]], idx: int, title_prefix: str) -> OutfitRecommendation:
            if not selection:
                return OutfitRecommendation(
                    id=f"{title_prefix}-{idx}",
                    title=f"{title_prefix}搭配",
                    items=[],
                    main_color_family5=payload.today_main_color,
                    styles=["日常"],
                    reason="資料不足，僅能提供建議框架",
                )
            main_color = selection[0].get("color_family5", payload.today_main_color)
            return OutfitRecommendation(
                id=f"{title_prefix}-{idx}",
                title=f"{title_prefix}靈感 #{idx+1}",
                items=[
                    OutfitItemRef(
                        item_id=item["id"],
                        source=item.get("source", "wardrobe"),
                    )
                    for item in selection
                ],
                main_color_family5=main_color,
                styles=selection[0].get("styles", []) or ["日常"],
                reason="根據衣櫃現有單品與色系規則產生的基礎搭配",
            )

        wardrobe_plan = to_reco(wardrobe_selection, 0, "衣櫃")
        store_plan = to_reco(store_selection, 0, "Style Shop")
        return OutfitPlannerResult(
            wardrobe_outfits=[wardrobe_plan],
            store_outfits=[store_plan],
        )

    def _build_prompt(self, payload: OutfitPlannerPayload) -> str:
        instructions = (
            "你是一個「智慧衣櫃 AI 穿搭顧問」。\n"
            "請依照以下規則生成 JSON：\n"
            "1. 產生 wardrobe_outfits 與 store_outfits 各至少 1 套。\n"
            "2. 每套需包含 title、items、main_color_family5、styles、reason。\n"
            "3. items 內僅能使用輸入 JSON 提供的 item_id 與 source。\n"
            "4. 遵守色系與類別規則：上衣需搭配下身或洋裝，並盡量符合 today_main_color。\n"
            "5. 優先使用 last_worn_days 接近 {days} 天未穿的衣櫃單品，再以 Style Shop 商品補位。\n"
            "6. 僅輸出 JSON，不能包含其他文字或解說。\n"
        ).format(days=30)

        payload_dict = {
            "user_request": payload.user_request,
            "today_main_color": payload.today_main_color,
            "gender": payload.gender,
            "weather": payload.weather or {},
            "wardrobe_items": payload.wardrobe_items,
            "store_items": payload.store_items,
        }

        return (
            f"{instructions}\n"
            f"以下是輸入資料：\n"
            f"{json.dumps(payload_dict, ensure_ascii=False, indent=2)}\n"
            "請回傳如下格式：\n"
            "{\n"
            "  \"wardrobe_outfits\": [OutfitRecommendation],\n"
            "  \"store_outfits\": [OutfitRecommendation]\n"
            "}\n"
        )

    @staticmethod
    def _extract_text(response: Any) -> str:
        if not response:
            return ""
        if hasattr(response, "text") and response.text:
            return response.text
        if getattr(response, "candidates", None):
            parts = response.candidates[0].content.parts
            if parts:
                part = parts[0]
                return getattr(part, "text", "")
        return str(response)

    def _parse_response(self, raw_text: Optional[str]) -> Optional[OutfitPlannerResult]:
        if not raw_text:
            return None
        json_text = raw_text.strip()
        if not json_text.startswith("{"):
            match = re.search(r"\{.*\}", raw_text, re.DOTALL)
            if match:
                json_text = match.group(0)
        try:
            data = json.loads(json_text)
            return OutfitPlannerResult(**data)
        except (json.JSONDecodeError, ValidationError):
            logger.warning("OutfitPlannerAIService: failed to parse AI JSON")
            return None


def map_color_to_family(color_name: Optional[str]) -> str:
    if not color_name:
        return "中性"
    text = color_name.lower()
    for family, keywords in COLOR_FAMILY_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text:
                return family
    return "中性"


def map_category(value: Optional[str]) -> str:
    if not value:
        return "top"
    key = value.lower()
    return CATEGORY_CANONICAL_MAP.get(value, CATEGORY_CANONICAL_MAP.get(key, "top"))


def normalise_styles(raw: Optional[Any]) -> List[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(item) for item in raw if str(item).strip()]
    if isinstance(raw, str):
        tokens = re.split(r"[,/、\s]", raw)
        return [token for token in tokens if token]
    return []


def build_outfit_payload(
    wardrobe_items: List[Dict[str, Any]],
    store_items: List[Dict[str, Any]],
    user_request: str,
    today_main_color: str,
    gender: str,
    weather: Optional[Dict[str, Any]] = None,
) -> OutfitPlannerPayload:
    return OutfitPlannerPayload(
        user_request=user_request,
        today_main_color=today_main_color,
        gender=gender,
        wardrobe_items=wardrobe_items,
        store_items=store_items,
        weather=weather,
    )


outfit_planner_ai_service = OutfitPlannerAIService()

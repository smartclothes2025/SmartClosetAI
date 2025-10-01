# api/v1/weather.py

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import httpx
import os
import logging
from sqlalchemy.orm import Session

from app.models.wardrobe import Wardrobe
from app.models.auth import User
from app.api.v1.auth import get_current_user
from app.core.db import get_db

logging.basicConfig(level=logging.INFO)

router = APIRouter(
    tags=["weather"],
)

# 讀取 API key
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
if not WEATHER_API_KEY:
    logging.error("未設定 WEATHER_API_KEY 環境變數！")
    WEATHER_API_KEY = "your-fallback-weather-api-key-for-dev"

WEATHER_API_URL = "http://api.openweathermap.org/data/2.5/weather"


class WeatherResponse(BaseModel):
    temperature: float
    description: str
    city: str
    humidity: int
    suggestion: str
    icon: str


def get_outfit_suggestion(temp: float, weather: str) -> str:
    """
    根據溫度和天氣描述生成穿搭建議。
    """
    suggestion = "建議穿著舒適的衣物"
    if "雨" in weather:
        suggestion = "天氣有雨，建議攜帶雨具並穿著防水鞋或外套"
    elif temp < 5:
        suggestion = "天氣嚴寒，請穿著厚重保暖衣物，如羽絨服、厚毛衣、手套、帽子和圍巾"
    elif temp < 10:
        suggestion = "天氣非常寒冷，請穿著保暖外套、毛衣和長褲"
    elif temp < 15:
        suggestion = "天氣較冷，建議穿著薄外套、毛衣或衛衣搭配長褲"
    elif temp < 20:
        suggestion = "天氣微涼，適合長袖T恤、襯衫搭配長褲或裙子，可攜帶薄外套"
    elif temp < 25:
        suggestion = "天氣舒適溫暖，適合短袖T恤、襯衫、長褲或裙子"
    elif temp < 30:
        suggestion = "天氣溫暖偏熱，建議穿著輕薄透氣的短袖、短褲或裙子"
    else:
        suggestion = "天氣炎熱，請穿著輕薄透氣衣物，並注意防曬與補充水分"
    return suggestion


async def _fetch_weather_from_openweathermap(params: dict) -> dict:
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            resp = await client.get(WEATHER_API_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
            logging.debug(f"從 OpenWeatherMap 拿到資料: {data}")
            return data
    except httpx.HTTPStatusError as e:
        logging.error(f"天氣 API 錯誤狀態碼 {e.response.status_code}: {e.response.text}")
        if e.response.status_code == 401:
            raise HTTPException(status_code=401, detail="API 金鑰無效。")
        elif e.response.status_code == 404:
            raise HTTPException(status_code=404, detail="找不到該地區天氣。")
        else:
            raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except httpx.RequestError as e:
        logging.error(f"天氣 API 請求失敗: {e}")
        raise HTTPException(status_code=500, detail=f"獲取天氣資料失敗: {e}")
    except Exception as e:
        logging.error(f"未預期錯誤: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _build_weather_response(data: dict, fallback_city: str | None = None) -> WeatherResponse:
    temperature = data["main"]["temp"]
    description = data["weather"][0]["description"]
    humidity = data["main"]["humidity"]
    icon = data["weather"][0].get("icon", "")
    city_name = data.get("name") or (fallback_city or "")
    suggestion = get_outfit_suggestion(temperature, description)
    logging.info(f"已獲取天氣：city={city_name}，temp={temperature}，desc={description}")
    return WeatherResponse(
        temperature=temperature,
        description=description,
        city=city_name,
        humidity=humidity,
        suggestion=suggestion,
        icon=icon,
    )


@router.get("/current", response_model=WeatherResponse)
async def get_current_weather(
    city: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
):
    """
    支援：
      - /current?city=Taipei
      - /current?lat=25.03&lon=121.56
    至少要傳 city 或 lat+lon
    """
    if lat is not None and lon is not None:
        params = {
            "lat": lat,
            "lon": lon,
            "appid": WEATHER_API_KEY,
            "units": "metric",
            "lang": "zh_tw",
        }
    elif city:
        params = {
            "q": city,
            "appid": WEATHER_API_KEY,
            "units": "metric",
            "lang": "zh_tw",
        }
    else:
        raise HTTPException(status_code=400, detail="請提供 city 或 lat & lon 其中之一。")

    data = await _fetch_weather_from_openweathermap(params)
    return _build_weather_response(data, fallback_city=city)


@router.get("/by-coord", response_model=WeatherResponse)
async def get_by_coord(lat: float, lon: float):
    """
    舊路徑兼容：只接受經緯度（對應前端要的 /api/v1/weather/by-coord）
    """
    params = {
        "lat": lat,
        "lon": lon,
        "appid": WEATHER_API_KEY,
        "units": "metric",
        "lang": "zh_tw",
    }
    data = await _fetch_weather_from_openweathermap(params)
    return _build_weather_response(data)


@router.get("/outfit-suggestion")
async def get_outfit_suggestion_for_user(
    city: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    根據使用者衣櫃與天氣生成穿搭建議（以 city 查）。
    """
    params = {
        "q": city,
        "appid": WEATHER_API_KEY,
        "units": "metric",
        "lang": "zh_tw",
    }
    data = await _fetch_weather_from_openweathermap(params)
    temperature = data["main"]["temp"]
    description = data["weather"][0]["description"]

    wardrobe_items = db.query(Wardrobe).filter(Wardrobe.user_id == current_user.id).all()
    if not wardrobe_items:
        raise HTTPException(status_code=404, detail="衣櫃為空，無法生成建議。")

    suggestion = get_outfit_suggestion(temperature, description)
    return {
        "city": city,
        "temperature": temperature,
        "weather": description,
        "suggestion": suggestion,
        "wardrobe_items": [item.filename for item in wardrobe_items],
    }
#api/v1/weather.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx
import os
import logging
from app.models.wardrobe import Wardrobe
from app.models.auth import User
from app.api.v1.auth import get_current_user
from app.core.db import get_db
from fastapi import Depends
from sqlalchemy.orm import Session

logging.basicConfig(level=logging.INFO)

router = APIRouter()

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

def get_outfit_suggestion(temp: float, weather: str) -> str:
    """
    根據溫度和天氣描述生成穿搭建議。
    """
    logging.debug(f"為溫度={temp}°C，天氣='{weather}'生成穿搭建議")
    suggestion = "建議穿著舒適的衣物" # 預設建議

    if "雨" in weather:
        suggestion = "天氣有雨，建議攜帶雨具並穿著防水鞋或外套"
    elif temp < 5:
        suggestion = "天氣嚴寒，請務必穿著厚重的多層保暖衣物，如羽絨服、厚毛衣、手套、帽子和圍巾"
    elif temp < 10:
        suggestion = "天氣非常寒冷，請穿著保暖外套、毛衣和長褲"
    elif temp < 15:
        suggestion = "天氣較冷，建議穿著薄外套、毛衣或衛衣搭配長褲"
    elif temp < 20:
        suggestion = "天氣微涼，適合穿著長袖T恤、襯衫搭配長褲或裙子，可攜帶薄外套"
    elif temp < 25:
        suggestion = "天氣舒適溫暖，適合穿著短袖T恤、襯衫、長褲或裙子"
    elif temp < 30:
        suggestion = "天氣溫暖偏熱，建議穿著輕薄透氣的短袖、短褲或裙子"
    else: 
        suggestion = "天氣炎熱，請穿著非常輕薄透氣的衣物，注意防曬和補充水分"

    return suggestion


@router.get("/current")
async def get_current_weather(city: str):
    """根據城市名稱獲取天氣資訊"""
    params = {
        "q": city,
        "appid": WEATHER_API_KEY,
        "units": "metric",  
        "lang": "zh_tw"  
    }
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(WEATHER_API_URL, params=params)
            response.raise_for_status() # 如果狀態碼不是 2xx，會拋出異常
            data = response.json()
        except httpx.RequestError as e:
            logging.error(f"天氣 API 的 HTTP 請求失敗: {e}")
            raise HTTPException(status_code=500, detail=f"獲取天氣數據時發生錯誤: {e}")
        except httpx.HTTPStatusError as e:
             logging.error(f"天氣 API 返回錯誤狀態碼 {e.response.status_code}: {e.response.text}")
             if e.response.status_code == 401:
                  raise HTTPException(status_code=401, detail="天氣服務的 API 金鑰無效。")
             elif e.response.status_code == 404:
                  raise HTTPException(status_code=404, detail=f"找不到城市 '{city}'。")
             else:
                  raise HTTPException(status_code=e.response.status_code, detail=f"天氣 API 錯誤: {e.response.text}")
        except Exception as e:
             logging.error(f"獲取天氣時發生未預期的錯誤: {e}")
             raise HTTPException(status_code=500, detail=f"發生未預期的錯誤: {e}")


    temperature = data["main"]["temp"]
    description = data["weather"][0]["description"]
    humidity = data["main"]["humidity"]

    suggestion = get_outfit_suggestion(temperature, description)

    logging.info(f"已獲取{city}的天氣: 溫度={temperature}，描述='{description}'，建議='{suggestion}'")

    return WeatherResponse(
        temperature=temperature,
        description=description,
        city=city,
        humidity=humidity,
        suggestion=suggestion
    )

async def get_current_weather_data(city: str):
    """
    根據城市名稱從 OpenWeatherMap API 獲取原始天氣數據。
    """
    params = {
        "q": city,
        "appid": WEATHER_API_KEY,
        "units": "metric",  
        "lang": "zh_tw"  
    }
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(WEATHER_API_URL, params=params)
            response.raise_for_status() 
            data = response.json()
            logging.debug(f"成功獲取{city}的天氣數據: {data}")
            return data
        except httpx.RequestError as e:
            logging.error(f"獲取{city}的天氣 API 的 HTTP 請求失敗: {e}")
            raise HTTPException(status_code=500, detail=f"獲取天氣數據時發生錯誤: {e}")
        except httpx.HTTPStatusError as e:
             logging.error(f"獲取{city}的天氣 API 返回錯誤狀態碼 {e.response.status_code}: {e.response.text}")
             if e.response.status_code == 401:
                  raise HTTPException(status_code=401, detail="天氣服務的 API 金鑰無效。")
             elif e.response.status_code == 404:
                  raise HTTPException(status_code=404, detail=f"找不到城市 '{city}'。")
             else:
                  raise HTTPException(status_code=e.response.status_code, detail=f"天氣 API 錯誤: {e.response.text}")
        except Exception as e:
             logging.error(f"獲取{city}的天氣時發生未預期的錯誤: {e}")
             raise HTTPException(status_code=500, detail=f"發生未預期的錯誤: {e}")

@router.get("/outfit-suggestion")
async def get_outfit_suggestion_for_user(city: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    根據使用者的衣櫃內容和天氣資訊生成穿搭建議。
    """
    # 獲取天氣數據
    weather_data = await get_current_weather_data(city)
    temperature = weather_data["main"]["temp"]
    description = weather_data["weather"][0]["description"]

    # 獲取使用者的衣櫃內容
    wardrobe_items = db.query(Wardrobe).filter(Wardrobe.user_id == current_user.id).all()
    if not wardrobe_items:
        raise HTTPException(status_code=404, detail="您的衣櫃是空的，無法生成穿搭建議。")

    # 根據天氣生成穿搭建議
    suggestion = get_outfit_suggestion(temperature, description)

    return {
        "city": city,
        "temperature": temperature,
        "weather": description,
        "suggestion": suggestion,
        "wardrobe_items": [item.filename for item in wardrobe_items]
    }

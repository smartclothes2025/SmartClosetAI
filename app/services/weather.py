"""
天氣服務
重用現有天氣 API 並提供給推薦系統使用
"""
import httpx
import os
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")
WEATHER_API_URL = "http://api.openweathermap.org/data/2.5/weather"


class WeatherService:
    """天氣服務"""
    
    @staticmethod
    async def get_weather(
        city: Optional[str] = None,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        取得天氣資訊
        
        Args:
            city: 城市名稱
            lat: 緯度
            lon: 經度
        
        Returns:
            {
                "temperature": 253,
                "description": "晴",
                "humidity": 60,
                "is_raining": False,
                "icon": "01d"
            }
        """
        if not OPENWEATHER_API_KEY:
            logger.warning("未設定 OPENWEATHER_API_KEY，使用預設天氣")
            return {
                "temperature": 25.0,
                "description": "晴",
                "humidity": 60,
                "is_raining": False,
                "icon": "01d",
            }
        
        # 建立參數
        if lat is not None and lon is not None:
            params = {
                "lat": lat,
                "lon": lon,
                "appid": OPENWEATHER_API_KEY,
                "units": "metric",
                "lang": "zh_tw",
            }
        elif city:
            params = {
                "q": city,
                "appid": OPENWEATHER_API_KEY,
                "units": "metric",
                "lang": "zh_tw",
            }
        else:
            # 預設桃園
            params = {
                "q": "Tainan",
                "appid": OPENWEATHER_API_KEY,
                "units": "metric",
                "lang": "zh_tw",
            }
        
        try:
            async with httpx.AsyncClient(trust_env=False) as client:
                resp = await client.get(WEATHER_API_URL, params=params, timeout=10.0)
                resp.raise_for_status()
                data = resp.json()
                
                temperature = data["main"]["temp"]
                description = data["weather"][0]["description"]
                humidity = data["main"]["humidity"]
                icon = data["weather"][0].get("icon", "")
                is_raining = "rain" in description.lower() or "雨" in description
                
                return {
                    "temperature": temperature,
                    "description": description,
                    "humidity": humidity,
                    "is_raining": is_raining,
                    "icon": icon,
                }
        
        except Exception as e:
            logger.error(f"取得天氣失敗: {e}")
            # 回傳預設值
            return {
                "temperature": 25.0,
                "description": "晴",
                "humidity": 60,
                "is_raining": False,
                "icon": "01d",
            }
    
    @staticmethod
    def get_outfit_categories_by_weather(temperature: float, is_raining: bool) -> Dict[str, Any]:
        """
        根據天氣推薦衣物類別
        
        Returns:
            {
                "need_outer": True/False,
                "avoid_categories": ["麂皮"],
                "suggested_categories": ["外套", "長褲"],
                "temperature_level": "cold"
            }
        """
        result = {
            "need_outer": False,
            "avoid_categories": [],
            "suggested_categories": [],
            "temperature_level": "comfortable",
        }
        
        # 根據溫度
        if temperature < 10:
            result["need_outer"] = True
            result["suggested_categories"] = ["外套", "毛衣", "長褲"]
            result["temperature_level"] = "very_cold"
        elif temperature < 15:
            result["need_outer"] = True
            result["suggested_categories"] = ["外套", "長袖", "長褲"]
            result["temperature_level"] = "cold"
        elif temperature < 20:
            result["suggested_categories"] = ["長袖", "薄外套"]
            result["temperature_level"] = "cool"
        elif temperature < 25:
            result["suggested_categories"] = ["短袖", "長褲", "裙子"]
            result["temperature_level"] = "comfortable"
        elif temperature < 30:
            result["suggested_categories"] = ["短袖", "短褲", "裙子"]
            result["temperature_level"] = "warm"
        else:
            result["suggested_categories"] = ["短袖", "短褲"]
            result["temperature_level"] = "hot"
        
        # 下雨天避免特定材質
        if is_raining:
            result["avoid_categories"].append("麂皮")
        
        return result


# 全域實例
def get_weather_service() -> WeatherService:
    """取得天氣服務實例"""
    return WeatherService()

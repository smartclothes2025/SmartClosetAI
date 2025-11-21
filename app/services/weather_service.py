# app/services/weather_service.py
import os
import logging
import httpx
from typing import Optional, Dict, Any
from datetime import datetime
from dotenv import load_dotenv

# 載入環境變數
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
load_dotenv(env_path, override=True)

logger = logging.getLogger(__name__)


class WeatherService:
    """天氣服務，使用 OpenWeatherMap API 獲取當地天氣資訊"""
    
    def __init__(self):
        self.api_key = os.getenv("OPENWEATHER_API_KEY")
        self.base_url = "https://api.openweathermap.org/data/2.5/weather"
        
        if not self.api_key:
            logger.warning("⚠️ OPENWEATHER_API_KEY 未設定，天氣功能將無法使用")
    
    async def get_weather_by_city(self, city: str = "Taoyuan", country_code: str = "TW") -> Optional[Dict[str, Any]]:
        """
        根據城市名稱獲取天氣資訊
        
        Args:
            city: 城市名稱（預設：Taoyuan）
            country_code: 國家代碼（預設：TW）
            
        Returns:
            天氣資訊字典，包含溫度、天氣狀況、濕度等
        """
        if not self.api_key:
            logger.error("❌ 無法獲取天氣：API Key 未設定")
            return None
        
        try:
            params = {
                "q": f"{city},{country_code}",
                "appid": self.api_key,
                "units": "metric",  # 使用攝氏溫度
                "lang": "zh_tw"     # 繁體中文
            }
            
            logger.info(f"🌤️ 正在獲取 {city} 的天氣資訊...")
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self.base_url, params=params)
                response.raise_for_status()
                data = response.json()
            
            # 解析天氣資訊
            weather_info = {
                "city": data.get("name", city),
                "country": data.get("sys", {}).get("country", country_code),
                "temperature": round(data.get("main", {}).get("temp", 0)),
                "feels_like": round(data.get("main", {}).get("feels_like", 0)),
                "temp_min": round(data.get("main", {}).get("temp_min", 0)),
                "temp_max": round(data.get("main", {}).get("temp_max", 0)),
                "humidity": data.get("main", {}).get("humidity", 0),
                "weather": data.get("weather", [{}])[0].get("main", "Clear"),
                "weather_description": data.get("weather", [{}])[0].get("description", "晴朗"),
                "wind_speed": data.get("wind", {}).get("speed", 0),
                "timestamp": datetime.now().isoformat()
            }
            
            logger.info(f"✅ 天氣資訊獲取成功：{weather_info['city']} {weather_info['temperature']}°C {weather_info['weather_description']}")
            return weather_info
            
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ 天氣 API 回應錯誤 {e.response.status_code}: {e.response.text}")
            return None
        except (httpx.ConnectError, httpx.ReadTimeout) as e:
            logger.error(f"❌ 天氣 API 連線失敗或逾時：{str(e)}")
            return None
        except Exception as e:
            logger.error(f"❌ 解析天氣資訊時發生錯誤：{str(e)}", exc_info=True)
            return None
    
    async def get_weather_by_coordinates(self, lat: float, lon: float) -> Optional[Dict[str, Any]]:
        """
        根據經緯度獲取天氣資訊
        
        Args:
            lat: 緯度
            lon: 經度
            
        Returns:
            天氣資訊字典
        """
        if not self.api_key:
            logger.error("❌ 無法獲取天氣：API Key 未設定")
            return None
        
        try:
            params = {
                "lat": lat,
                "lon": lon,
                "appid": self.api_key,
                "units": "metric",
                "lang": "zh_tw"
            }
            
            logger.info(f"🌤️ 正在獲取座標 ({lat}, {lon}) 的天氣資訊...")
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self.base_url, params=params)
                response.raise_for_status()
                data = response.json()
            
            weather_info = {
                "city": data.get("name", "未知地點"),
                "country": data.get("sys", {}).get("country", ""),
                "temperature": round(data.get("main", {}).get("temp", 0)),
                "feels_like": round(data.get("main", {}).get("feels_like", 0)),
                "temp_min": round(data.get("main", {}).get("temp_min", 0)),
                "temp_max": round(data.get("main", {}).get("temp_max", 0)),
                "humidity": data.get("main", {}).get("humidity", 0),
                "weather": data.get("weather", [{}])[0].get("main", "Clear"),
                "weather_description": data.get("weather", [{}])[0].get("description", "晴朗"),
                "wind_speed": data.get("wind", {}).get("speed", 0),
                "timestamp": datetime.now().isoformat()
            }
            
            logger.info(f"✅ 天氣資訊獲取成功：{weather_info['city']} {weather_info['temperature']}°C")
            return weather_info
            
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ 天氣 API 回應錯誤 {e.response.status_code}: {e.response.text}")
            return None
        except (httpx.ConnectError, httpx.ReadTimeout) as e:
            logger.error(f"❌ 天氣 API 連線失敗或逾時：{str(e)}")
            return None
        except Exception as e:
            logger.error(f"❌ 獲取天氣資訊失敗：{str(e)}", exc_info=True)
            return None
    
    def get_weather_based_clothing_advice(self, weather_info: Dict[str, Any]) -> str:
        """
        根據天氣資訊生成穿搭建議
        
        Args:
            weather_info: 天氣資訊字典
            
        Returns:
            穿搭建議文字
        """
        if not weather_info:
            return ""
        
        temp = weather_info.get("temperature", 20)
        feels_like = weather_info.get("feels_like", temp)
        weather = weather_info.get("weather", "Clear")
        weather_desc = weather_info.get("weather_description", "")
        humidity = weather_info.get("humidity", 50)
        
        advice_parts = []
        
        # 溫度建議
        if temp < 10:
            advice_parts.append("天氣寒冷，建議穿著厚外套、毛衣、長褲")
        elif temp < 15:
            advice_parts.append("天氣偏涼，建議穿著薄外套或針織衫")
        elif temp < 20:
            advice_parts.append("天氣涼爽，建議穿著長袖上衣")
        elif temp < 25:
            advice_parts.append("天氣舒適，建議穿著短袖或薄長袖")
        elif temp < 30:
            advice_parts.append("天氣溫暖，建議穿著輕薄透氣的衣物")
        else:
            advice_parts.append("天氣炎熱，建議穿著涼爽透氣的衣物，注意防曬")
        
        # 天氣狀況建議
        if weather in ["Rain", "Drizzle", "Thunderstorm"]:
            advice_parts.append("有雨，記得攜帶雨具，建議穿著防水外套和鞋子")
        elif weather == "Snow":
            advice_parts.append("下雪天氣，建議穿著保暖防水的衣物和靴子")
        elif weather == "Clouds":
            advice_parts.append("多雲天氣，可能需要準備薄外套")
        elif weather == "Clear":
            advice_parts.append("晴朗天氣，記得做好防曬措施")
        
        # 濕度建議
        if humidity > 80:
            advice_parts.append("濕度較高，建議選擇透氣吸汗的材質")
        
        # 體感溫度提醒
        if abs(feels_like - temp) > 3:
            if feels_like < temp:
                advice_parts.append(f"體感溫度較低（{feels_like}°C），實際會感覺更冷")
            else:
                advice_parts.append(f"體感溫度較高（{feels_like}°C），實際會感覺更熱")
        
        return "。".join(advice_parts) + "。"


# 創建單例
weather_service = WeatherService()

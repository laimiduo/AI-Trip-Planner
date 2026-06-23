from typing import List, Optional, Union
from pydantic import BaseModel, ConfigDict, Field, field_validator


class TripRequest(BaseModel):
    """旅行规划请求"""
    city: str = Field(..., description="城市名称", example="北京")
    start_date: str = Field(..., description="开始日期YYYY-MM-DD", example="2025-06-01")
    end_date: str = Field(..., description="结束日期YYYY-MM-DD", example="2025-06-03")
    travel_days: int = Field(..., description="旅行天数", ge=1, le=30, example=3)
    transportation: str = Field(..., description="交通方式", example="公共公交")
    accommodation: str = Field(..., description="住宿类型", example="经济型酒店")
    preferences: List[str] = Field(default=[], description="用户偏好", example=["历史文化", "美食"])
    free_text_input: Optional[str] = Field(default="", description="额外要求", example="希望多安排一些博物馆")

    # 新增字段
    budget_min: Optional[int] = Field(default=None, description="最低预算(元)")
    budget_max: Optional[int] = Field(default=None, description="最高预算(元)")
    traveler_count: int = Field(default=1, description="出行人数", ge=1, le=50)
    traveler_type: str = Field(default="solo", description="出行类型: solo/couple/family_kids/family_pets/friends/business")
    pace: str = Field(default="moderate", description="行程节奏: relaxed/moderate/intensive")
    cuisine_preferences: List[str] = Field(default=[], description="饮食偏好", example=["川菜", "海鲜"])

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "city": "北京",
                "start_date": "2025-06-01",
                "end_date": "2025-06-03",
                "travel_days": 3,
                "transportation": "公共公交",
                "accommodation": "经济型酒店",
                "preferences": ["历史文化", "美食"],
                "free_text_input": "希望多安排一些博物馆",
                "budget_min": 2000,
                "budget_max": 5000,
                "traveler_count": 2,
                "traveler_type": "couple",
                "pace": "moderate",
                "cuisine_preferences": ["川菜", "北京烤鸭"]
            }
        }
    )


class Location(BaseModel):
    """位置信息"""
    longitude: float = Field(..., description="经度")
    latitude: float = Field(..., description="纬度")

    @field_validator("longitude", "latitude", mode="before")
    @classmethod
    def coerce_float(cls, v):
        if isinstance(v, str):
            # 处理像 "116.397128" 或 "116.397128,39.916527" 这样的字符串
            v = v.split(",")[0].strip()
            try:
                return float(v)
            except ValueError:
                return 0.0
        return float(v) if v else 0.0


class Hotel(BaseModel):
    """酒店信息"""
    name: str = Field(..., description="酒店名称")
    address: str = Field(default="", description="酒店地址")
    location: Optional[Union[Location, str, dict]] = Field(default=None, description="位置信息")
    price_range: str = Field(default="", description="价格范围")
    rating: Optional[Union[str, float]] = Field(default="", description="评分")
    distance: str = Field(default="", description="离景点的距离")
    type: str = Field(default="", description="酒店类型")
    estimated_cost: int = Field(default=0, description="预估费用")

    @field_validator("rating", mode="before")
    @classmethod
    def coerce_rating(cls, v):
        if isinstance(v, (int, float)):
            return str(v)
        return v or ""


class Meal(BaseModel):
    """餐饮信息"""
    type: str = Field(default="", description="餐饮类型：(breakfast/lunch/dinner/snack)")
    name: str = Field(default="用餐", description="餐饮名称")
    address: Optional[str] = Field(default=None, description="地址")
    location: Optional[Union[Location, str, dict, None]] = Field(default=None, description="经纬度坐标")
    description: Optional[str] = Field(default=None, description="描述")
    estimated_cost: int = Field(default=0, description="预估费用(元)")

    @field_validator("type", mode="before")
    @classmethod
    def coerce_type(cls, v):
        if not v or not isinstance(v, str):
            return ""
        return v

    @field_validator("name", mode="before")
    @classmethod
    def coerce_name(cls, v):
        if not v:
            return "用餐"
        return str(v)

    @field_validator("location", mode="before")
    @classmethod
    def coerce_meal_location(cls, v):
        if isinstance(v, str):
            return None
        return v


class TrafficTip(BaseModel):
    """交通提示"""
    time: str = Field(..., description="时间段（如'上午9-11点'）")
    tip: str = Field(..., description="交通建议（如'建议乘坐地铁2号线'）")


class PackingSuggestion(BaseModel):
    """打包建议"""
    item: str = Field(..., description="建议携带的物品")
    reason: str = Field(..., description="建议原因")


class LocalEvent(BaseModel):
    """当地活动"""
    name: str = Field(..., description="活动名称")
    date: str = Field(..., description="日期")
    description: str = Field(..., description="活动描述")
    location: str = Field(default="", description="活动地点")


class Attraction(BaseModel):
    """景点信息"""
    name: str = Field(..., description="景点名称")
    address: str = Field(default="", description="地址")
    location: Optional[Union[Location, str, dict]] = Field(default=None, description="经纬度坐标")
    visit_duration: int = Field(default=120, description="建议游览时间(分钟)")
    description: str = Field(default="", description="景点描述")
    category: Optional[str] = Field(default="景点", description="景点类别")
    rating: Optional[float] = Field(default=None, description="评分")
    photos: Optional[List[str]] = Field(default_factory=list, description="景点图片URL列表")
    poi_id: Optional[str] = Field(default="", description="POI ID")
    image_url: Optional[str] = Field(default=None, description="图片URL")
    ticket_price: int = Field(default=0, description="门票价格(元)")


class DayPlan(BaseModel):
    """单日行程"""
    date: str = Field(default="", description="日期YYYY-MM-DD")
    day_index: int = Field(default=0, description="第几天(从0开始)")
    description: str = Field(default="", description="当日行程概述")
    transportation: str = Field(default="", description="交通方式")
    accommodation: str = Field(default="", description="住宿类型")
    hotel: Optional[Union[Hotel, dict, str, None]] = Field(default=None, description="推荐酒店")
    meals: List[Union[Meal, dict]] = Field(default=[], description="餐饮列表")
    attractions: List[Union[Attraction, dict]] = Field(default=[], description="景点列表")
    # 新增字段
    traffic_tips: List[TrafficTip] = Field(default=[], description="当日交通建议")
    packing_suggestions: List[PackingSuggestion] = Field(default=[], description="当日打包/携带建议")
    local_events: List[LocalEvent] = Field(default=[], description="当地活动")

    @field_validator("transportation", mode="before")
    @classmethod
    def coerce_transportation(cls, v):
        if isinstance(v, dict):
            return "; ".join(f"{k}: {val}" for k, val in v.items())
        return str(v) if v is not None else ""

    @field_validator("meals", mode="before")
    @classmethod
    def coerce_meals(cls, v):
        if isinstance(v, dict):
            return list(v.values())
        if isinstance(v, list):
            return [m if isinstance(m, dict) else {} for m in v]
        return v or []

    @field_validator("attractions", mode="before")
    @classmethod
    def coerce_attractions(cls, v):
        if isinstance(v, list):
            return [a if isinstance(a, dict) else {} for a in v]
        return v or []

    @field_validator("hotel", mode="before")
    @classmethod
    def coerce_hotel(cls, v):
        if isinstance(v, str):
            return {"name": v}
        return v or None


class WeatherInfo(BaseModel):
    """天气信息"""
    date: str = Field(..., description="日期 YYYY-MM-DD")
    day_weather: str = Field(default="", description="白天天气")
    night_weather: str = Field(default="", description="夜间天气")
    day_temp: Union[int, str] = Field(default=0, description="白天温度")
    night_temp: Union[int, str] = Field(default=0, description="夜间温度")
    wind_direction: str = Field(default="", description="风向")
    wind_power: str = Field(default="", description="风力")

    @field_validator("day_temp", "night_temp", mode="before")
    @classmethod
    def parse_temp(cls, v):
        if isinstance(v, str):
            v = v.replace("°C", "").replace("℃", "").replace("°", "").strip()
            try:
                return int(v)
            except ValueError:
                return 0
        return v


class Budget(BaseModel):
    """预算信息"""
    total_attractions: int = Field(default=0, description="景点门票总费用")
    total_hotels: int = Field(default=0, description="酒店总费用")
    total_meals: int = Field(default=0, description="餐饮总费用")
    total_transportation: int = Field(default=0, description="交通总费用")
    total: int = Field(default=0, description="总费用")


class TripPlan(BaseModel):
    """旅行计划"""
    city: str = Field(..., description="目的地城市")
    start_date: str = Field(..., description="开始日期")
    end_date: str = Field(..., description="结束日期")
    days: List[DayPlan] = Field(default=[], description="每日行程")
    weather_info: List[WeatherInfo] = Field(default=[], description="天气信息")
    overall_suggestions: str = Field(default="", description="总体建议")
    budget: Optional[Budget] = Field(default=None, description="预算信息")
    # 新增字段
    budget_per_person: Optional[int] = Field(default=None, description="人均预算")
    best_time_tips: Optional[str] = Field(default=None, description="最佳出行时间建议")

    @field_validator("overall_suggestions", mode="before")
    @classmethod
    def coerce_suggestions(cls, v):
        if isinstance(v, dict):
            return "\n".join(f"{k}: {val}" for k, val in v.items())
        return str(v) if v is not None else ""


class TripPlanResponse(BaseModel):
    """旅行计划响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(default="", description="消息")
    data: Optional[TripPlan] = Field(default=None, description="旅行计划数据")

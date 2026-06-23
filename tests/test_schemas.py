"""Schema 验证测试."""

import pytest
from pydantic import ValidationError
from schemas import (
    Attraction,
    Budget,
    DayPlan,
    Location,
    Meal,
    TripPlan,
    TripPlanResponse,
    TripRequest,
    WeatherInfo,
)


class TestTripRequest:
    def test_valid_request(self):
        r = TripRequest(
            city="北京", start_date="2025-06-01", end_date="2025-06-03",
            travel_days=3, transportation="公交", accommodation="酒店",
        )
        assert r.city == "北京"
        assert r.travel_days == 3

    def test_invalid_travel_days(self):
        with pytest.raises(ValidationError):
            TripRequest(
                city="北京", start_date="2025-06-01", end_date="2025-06-03",
                travel_days=0, transportation="公交", accommodation="酒店",
            )

    def test_defaults(self):
        r = TripRequest(
            city="上海", start_date="2025-07-01", end_date="2025-07-05",
            travel_days=5, transportation="地铁", accommodation="民宿",
        )
        assert r.preferences == []
        assert r.traveler_count == 1
        assert r.traveler_type == "solo"
        assert r.pace == "moderate"


class TestLocation:
    def test_from_string(self):
        loc = Location(longitude="116.397128", latitude="39.916527")
        assert loc.longitude == 116.397128
        assert loc.latitude == 39.916527

    def test_from_float(self):
        loc = Location(longitude=116.4, latitude=39.9)
        assert loc.longitude == 116.4

    def test_from_csv_string(self):
        loc = Location(longitude="116.397128,39.916527", latitude="39.916527,116.397128")
        assert loc.longitude == 116.397128


class TestMeal:
    def test_minimal(self):
        m = Meal()
        assert m.name == "用餐"
        assert m.estimated_cost == 0

    def test_full(self):
        m = Meal(type="lunch", name="全聚德", estimated_cost=200)
        assert m.type == "lunch"
        assert m.name == "全聚德"


class TestAttraction:
    def test_minimal(self):
        a = Attraction(name="故宫")
        assert a.visit_duration == 120
        assert a.ticket_price == 0


class TestDayPlan:
    def test_empty(self):
        d = DayPlan()
        assert d.day_index == 0
        assert d.meals == []
        assert d.attractions == []

    def test_meals_as_dict(self):
        d = DayPlan(meals={"breakfast": {"name": "包子"}})
        assert len(d.meals) == 1
        assert d.meals[0].name == "包子"

    def test_transportation_as_dict(self):
        d = DayPlan(transportation={"morning": "公交", "afternoon": "地铁"})
        assert "公交" in d.transportation
        assert "地铁" in d.transportation


class TestTripPlan:
    def test_minimal(self):
        plan = TripPlan(city="北京", start_date="2025-06-01", end_date="2025-06-03")
        assert plan.days == []

    def test_full_plan(self):
        plan = TripPlan(
            city="北京",
            start_date="2025-06-01",
            end_date="2025-06-03",
            days=[DayPlan(day_index=0, date="2025-06-01")],
            overall_suggestions="玩得开心",
            budget=Budget(total=1000),
        )
        assert len(plan.days) == 1
        assert plan.budget.total == 1000


class TestWeatherInfo:
    def test_temp_parsing(self):
        w = WeatherInfo(date="2025-06-01", day_temp="25°C", night_temp="15℃")
        assert w.day_temp == 25
        assert w.night_temp == 15


class TestTripPlanResponse:
    def test_success_response(self):
        plan = TripPlan(city="北京", start_date="2025-06-01", end_date="2025-06-03")
        resp = TripPlanResponse(success=True, message="ok", data=plan)
        assert resp.success is True
        assert resp.data.city == "北京"

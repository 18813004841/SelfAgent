from pydantic import BaseModel, Field
from typing import Literal

#-- Pydantic 定义输入格式，无需在Prompt中手写 Json 描述
class WeatherInput(BaseModel):
    location: str = Field(..., description="The location to get the weather for")   #参数描述
    units: Literal["metric", "imperial"] = Field("metric", description="The units for the weather data")    #限定可选值metric或imperial
    include_forecast: bool = Field(False, description="Whether to include a weather forecast")   #布尔值参数 
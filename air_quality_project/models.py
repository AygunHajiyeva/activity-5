from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8)


class DeviceCreate(BaseModel):
    device_id: str
    model: str
    status: str
    room_id: int


class ThresholdUpdate(BaseModel):
    pm25_threshold: float = Field(ge=0)
    co2_threshold: float = Field(ge=0)


class ReadingCreate(BaseModel):
    device_id: str
    pm25: float = Field(ge=0)
    co2: float = Field(ge=0)
    temperature: float | None = None
    humidity: float | None = None

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8)


class DeviceCreate(BaseModel):
    device_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_-]+$")
    model: str = Field(min_length=1)
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


class RoomResponse(BaseModel):
    room_id: int
    name: str


class DeviceResponse(BaseModel):
    id: int
    device_id: str
    model: str
    status: str
    room_id: int
    room_name: str | None = None
    pm25_threshold: float | None = None
    co2_threshold: float | None = None


class ReadingResponse(BaseModel):
    reading_id: int
    device_id: str
    pm25: float
    co2: float
    temperature: float | None = None
    humidity: float | None = None
    timestamp: str | None = None


class AlertResponse(BaseModel):
    alert_id: int
    device_id: str
    reading_id: int
    alert_type: str
    value: float
    threshold: float
    timestamp: str | None = None
    acknowledged: bool


class UserResponse(BaseModel):
    user_id: int
    username: str
    role: str
    created_at: str | None = None

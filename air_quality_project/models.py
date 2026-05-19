from pydantic import BaseModel


class DeviceCreate(BaseModel):
    """Payload accepted by POST /devices."""

    device_id: str
    model: str
    status: str
    room_id: int

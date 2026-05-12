import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class AppointmentResponse(BaseModel):
    id: uuid.UUID
    candidate_name: str
    candidate_email: Optional[str]
    role_title: Optional[str]
    scheduled_start: datetime
    scheduled_end: datetime
    status: str

    model_config = ConfigDict(from_attributes=True)


class CalendarResponse(BaseModel):
    appointments: List[AppointmentResponse]

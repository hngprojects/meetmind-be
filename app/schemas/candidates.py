from pydantic import BaseModel, Field


class CandidateStatsData(BaseModel):
    """Data payload for candidate statistics."""

    total: int = Field(default=0)
    completed: int = Field(default=0)
    ongoing: int = Field(default=0)
    needs_attention: int = Field(default=0)


class CandidateStatsResponse(BaseModel):
    """Envelope for candidate statistics response."""

    success: bool = True
    message: str = "OK"
    data: CandidateStatsData

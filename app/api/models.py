from pydantic import BaseModel, Field
from typing import Optional

class SignalData(BaseModel):
    """Request model for incoming signals."""
    secret_key: str = Field(..., description="Authentication secret key")
    action: str = Field(..., description="Trade action: BUY, SELL, or CLOSE")
    symbol: str = Field(..., description="Trading symbol (e.g., EURUSD)")
    price: float = Field(..., gt=0, description="Trade price")
    open_signal_id: Optional[int] = Field(None, description="ID of the signal being closed (required for CLOSE action)")

class SignalResponse(BaseModel):
    """Response model for a successfully processed signal."""
    status: str
    message: str
    signal_id: Optional[int] = None
    signals_today: int

class HealthResponse(BaseModel):
    """Response model for the health check endpoint."""
    status: str
    bot_active: bool
    timestamp: str

class StatsResponse(BaseModel):
    """Response model for the statistics endpoint."""
    date: str
    stats: dict
    bot_active: bool
    limits: dict

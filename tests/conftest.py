import pytest
import pytest_asyncio
import asyncio
import sqlite3
from unittest.mock import patch, AsyncMock
import os
import httpx
from contextlib import asynccontextmanager

# Import the main FastAPI app
from main import app
from app.db.database import init_database, get_db_connection
from app.core.config import settings

# =====================================================================
# Mocking and Test Database Setup
# =====================================================================

@asynccontextmanager
async def dummy_lifespan(app):
    """A dummy lifespan manager that does nothing, to disable the real one during tests."""
    yield

@pytest.fixture(scope="function")
def db_session(monkeypatch):
    """
    Provides a clean, file-based SQLite database for each test function.
    This is more reliable for testing than in-memory databases.
    """
    test_db_path = "./test.db"
    
    # Ensure no old test DB exists before the test
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    # Patch the settings to use the test DB path
    monkeypatch.setattr(settings, 'DB_PATH', test_db_path)
    
    # Initialize the schema in the new test DB
    init_database()
    
    # The dependency override will now use this patched path
    def override_get_db_connection():
        conn = sqlite3.connect(test_db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    app.dependency_overrides[get_db_connection] = override_get_db_connection
    
    yield # Test runs here
    
    # Clean up the dependency override and the test DB file
    app.dependency_overrides.clear()
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

# =====================================================================
# Pytest Fixtures
# =====================================================================

@pytest_asyncio.fixture
async def test_client(db_session, monkeypatch):
    """
    Provides an asynchronous test client that uses the isolated test database
    and disables the real application lifespan events.
    """
    # Patch the real lifespan manager in the main module with our dummy one
    monkeypatch.setattr("main.lifespan", dummy_lifespan)
    
    with patch("app.services.telegram_service.telegram_service.send_alert", new_callable=AsyncMock):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

@pytest_asyncio.fixture
async def mock_telegram_send_alert(db_session):
    """
    Provides a direct mock of the send_alert function for easy inspection.
    Depends on db_session to ensure database is ready.
    """
    with patch("app.services.telegram_service.telegram_service.send_alert", new_callable=AsyncMock) as mock_send_alert:
        yield mock_send_alert

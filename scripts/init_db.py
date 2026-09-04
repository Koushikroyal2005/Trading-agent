import asyncio
from backend.storage.repositories import TradingRepository
from backend.utils.config import get_settings

async def main():
    repository=TradingRepository(get_settings().database_url);await repository.initialize();await repository.close();print("Database initialized")
if __name__=="__main__":asyncio.run(main())


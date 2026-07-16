from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.settings import settings

engine = create_async_engine(
    settings.async_database_uri,
    echo=False,
    future=True,
    pool_size=5,
    max_overflow=10
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ercot_forecast.config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
)

SessionFactory = sessionmaker(
    bind = engine, 
    expire_on_commit=False
)
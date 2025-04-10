# database.py
from sqlalchemy import create_engine, Column, String, DateTime, ForeignKey, Enum as SQLAEnum
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from sqlalchemy.exc import SQLAlchemyError
import uuid
from datetime import datetime, timezone
from contextlib import contextmanager
import enum
import os
import traceback # For better error logging

from config import settings # Import settings to get DATABASE_URL

# Database setup
engine = None
SessionLocal = None
Base = declarative_base() # Define Base first

try:
    # Consider adding connect_args for timeouts if needed
    engine = create_engine(settings.database_url, pool_pre_ping=True) # Added pool_pre_ping
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    print("Database engine created successfully.")
    # Test connection early
    with engine.connect() as connection:
        print("Database connection successful.")
except Exception as e:
    print(f"!!! Error creating database engine: {e}")
    traceback.print_exc()
    engine = None
    SessionLocal = None
    # Setting Base to object here might cause issues later if models are defined
    # Ensure models are defined conditionally based on engine/SessionLocal being available


# --- Enums (mirror Pydantic enums for DB consistency) ---
class DBPorfolioStatus(enum.Enum):
    ACTIVE = "active"
    CLOSED = "closed"

# --- SQLAlchemy Models ---
# Define models regardless of engine status, but creation depends on engine

class CombinedPortfolioDB(Base):
    __tablename__ = "combined_portfolios"
    cpmID = Column(String, primary_key=True, index=True)
    combined_portfolio_id = Column(String, unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    status = Column(SQLAEnum(DBPorfolioStatus), nullable=False, default=DBPorfolioStatus.ACTIVE)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    asset_portfolios = relationship("AssetPortfolioDB", back_populates="combined_portfolio_owner", cascade="all, delete-orphan") # Added cascade

class AssetPortfolioDB(Base):
    __tablename__ = "asset_portfolios"
    asset_portfolio_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    cpmID = Column(String, ForeignKey("combined_portfolios.cpmID"), nullable=False, index=True)
    pair = Column(String, nullable=False, index=True)
    status = Column(SQLAEnum(DBPorfolioStatus), nullable=False, default=DBPorfolioStatus.ACTIVE)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    combined_portfolio_owner = relationship("CombinedPortfolioDB", back_populates="asset_portfolios")

# --- DB Session Dependency ---
def get_db():
    """FastAPI dependency to get a DB session."""
    if not SessionLocal:
         print("Database session factory not configured.")
         # Raise a more specific error for FastAPI to catch
         raise RuntimeError("Database session factory not configured.")
    db = SessionLocal()
    try:
        yield db
    except SQLAlchemyError as e:
         print(f"Database Session Error: {e}")
         db.rollback() # Rollback on error
         raise # Re-raise after logging/rollback
    finally:
        db.close()

@contextmanager
def db_session_scope():
    """Provide a transactional scope around a series of operations (for background tasks)."""
    if not SessionLocal:
        raise RuntimeError("Database session factory not configured.")
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except SQLAlchemyError as e:
        print(f"Database Transaction Error: {e}")
        session.rollback()
        raise
    except Exception as e:
        print(f"Non-DB Error during transaction: {e}")
        session.rollback()
        raise
    finally:
        session.close()

def create_db_tables():
    """Utility function to create tables (call cautiously)."""
    if engine:
        print("Creating database tables (if they don't exist)...")
        try:
            Base.metadata.create_all(bind=engine)
            print("Database tables creation check complete.")
        except Exception as e:
            print(f"!!! Error creating/checking database tables: {e}")
            traceback.print_exc()
    else:
        print("Database engine not available. Skipping table creation.")
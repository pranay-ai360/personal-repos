from sqlalchemy import create_engine, text
import os

engine = create_engine(os.getenv('postgres_url'))
with engine.connect() as conn:
    conn.execute(text('DROP TABLE IF EXISTS wallet'))
    conn.commit()
print("Table dropped successfully")

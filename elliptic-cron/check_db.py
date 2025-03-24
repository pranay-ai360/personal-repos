import os
from sqlalchemy import create_engine, text

# Get postgres URL from environment
postgres_url = os.getenv('postgres_url', 'postgresql://doadmin:xxx@postgres-cluster-do-user-12892822-0.c.db.ondigitalocean.com:25060/elliptic')

# Create engine
engine = create_engine(postgres_url)

# Query the database
with engine.connect() as conn:
    # Check table structure
    result = conn.execute(text("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'wallet'
        ORDER BY ordinal_position;
    """))
    print("\nTable Structure:")
    for row in result:
        print(f"{row[0]}: {row[1]}")
        
    # Get total count
    result = conn.execute(text("SELECT COUNT(*) FROM wallet"))
    count = result.scalar()
    print(f"\nTotal rows in wallet table: {count}")
    
    # Check all data
    result = conn.execute(text("""
        SELECT id, 
               subject__type, 
               subject__hash, 
               analysed_at,
               blockchain_info,
               customer__reference,
               triggered_rules,
               error__name,
               error__message
        FROM wallet 
        ORDER BY analysed_at DESC
    """))
    print("\nAll Data:")
    for row in result:
        print(row)

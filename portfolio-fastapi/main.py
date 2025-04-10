# main.py

from fastapi import FastAPI, HTTPException, status, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from typing import List, Optional, Dict
import uvicorn
import pandas as pd
from datetime import datetime, timezone, timedelta
import pytz
import uuid
import traceback

# --- SQLAlchemy Imports ---
from sqlalchemy.orm import Session
# Import DB setup items needed in main
from database import Base, engine, get_db, CombinedPortfolioDB, AssetPortfolioDB, DBPorfolioStatus, create_db_tables
# --- End SQLAlchemy Imports ---

from influxdb_client.client.exceptions import InfluxDBError

from config import settings
# Import models
from models import (
    PriceData, EventData, QueryRequest, StatusResponse,
    PortfolioItem, PortfolioQueryResultItem, QueryResponse,
    GenerateRequest, GenerateResponse,
    ListPortfolioRequest, ListPortfolioResponse, PortfolioInfo, PortfolioStatus,
    CreateCombinedPortfolioRequest, CreateCombinedPortfolioResponse,
    CreateAssetPortfolioRequest, CreateAssetPortfolioResponse, CreateAssetPortfolioResponseItem,
    PHT # Import PHT
)
# Import InfluxDB utilities - Use an alias for the conflicting function name
from influx_utils import (
    write_price, write_event,
    close_influx_client, client as influx_client,
    write_api, query_api, delete_api,
    query_portfolio_summary as query_influx_summary # USE ALIAS HERE
)
# Import the background job function
from background_jobs import calculate_and_store_portfolio

# Create FastAPI app instance
app = FastAPI(
    title="Portfolio Tracking API V2 (Postgres Meta)",
    description="API with Postgres metadata, InfluxDB time-series, background calculation.",
    version="2.1.0"
)

# --- Dependency Checks ---
async def get_influx_status():
    """Dependency to check InfluxDB client initialization and connectivity."""
    if influx_client is None or query_api is None or write_api is None or delete_api is None:
         raise HTTPException(status_code=503, detail="InfluxDB client components not initialized.")
    try:
        if not influx_client.ping(): raise HTTPException(status_code=503, detail="InfluxDB connection ping failed.")
    except Exception as e: raise HTTPException(status_code=503, detail=f"InfluxDB connection error: {e}")

# --- API Endpoints ---

# --- Portfolio Management Endpoints (Using PostgreSQL) ---

@app.post("/portfolios/list", response_model=ListPortfolioResponse, summary="List User Portfolios")
async def list_portfolios(request: ListPortfolioRequest, db: Session = Depends(get_db)):
    """Retrieves combined and asset portfolio information for a user from PostgreSQL."""
    try:
        combined_db = db.query(CombinedPortfolioDB).filter(CombinedPortfolioDB.cpmID == request.cpmID).first()
        combined_api: Optional[PortfolioInfo] = None
        if combined_db: combined_api = PortfolioInfo(id=combined_db.combined_portfolio_id, status=combined_db.status.value)

        asset_db = db.query(AssetPortfolioDB).filter(AssetPortfolioDB.cpmID == request.cpmID).all()
        assets_api: Dict[str, List[PortfolioInfo]] = {}
        for asset in asset_db:
            if asset.pair not in assets_api: assets_api[asset.pair] = []
            assets_api[asset.pair].append(PortfolioInfo(id=asset.asset_portfolio_id, status=asset.status.value))

        return ListPortfolioResponse(cpmID=request.cpmID, combinedPortfolio=combined_api, assetPortfolio=assets_api)
    except Exception as e: print(f"Error listing portfolios for {request.cpmID}: {e}"); traceback.print_exc(); raise HTTPException(status_code=500, detail="Failed to retrieve portfolio list.")

@app.post("/portfolios/combined", response_model=CreateCombinedPortfolioResponse, status_code=status.HTTP_201_CREATED, summary="Create Combined Portfolio")
async def create_combined_portfolio(request: CreateCombinedPortfolioRequest, db: Session = Depends(get_db)):
    """Creates a single combined portfolio entry for a user in PostgreSQL. If one exists, returns 200 OK with existing ID."""
    try:
        existing_portfolio = db.query(CombinedPortfolioDB).filter(CombinedPortfolioDB.cpmID == request.cpmID).first()
        if existing_portfolio:
             print(f"Combined portfolio already exists for {request.cpmID}, ID: {existing_portfolio.combined_portfolio_id}")
             # Return 200 OK with existing ID
             return CreateCombinedPortfolioResponse(cpmID=request.cpmID, combinedPortfolioId=existing_portfolio.combined_portfolio_id)

        new_portfolio_id = str(uuid.uuid4())
        db_portfolio = CombinedPortfolioDB(cpmID=request.cpmID, combined_portfolio_id=new_portfolio_id, status=DBPorfolioStatus.ACTIVE)
        db.add(db_portfolio); db.commit(); db.refresh(db_portfolio)
        print(f"Created combined portfolio for {request.cpmID}, ID: {new_portfolio_id}")
        return CreateCombinedPortfolioResponse(cpmID=request.cpmID, combinedPortfolioId=new_portfolio_id)
    except Exception as e: db.rollback(); print(f"Error creating combined portfolio for {request.cpmID}: {e}"); traceback.print_exc(); raise HTTPException(status_code=500, detail="Failed to create combined portfolio.")

@app.post("/portfolios/asset", response_model=CreateAssetPortfolioResponse, status_code=status.HTTP_201_CREATED, summary="Create Asset Portfolios")
async def create_asset_portfolio(request: CreateAssetPortfolioRequest, db: Session = Depends(get_db)):
    """Creates new, active asset portfolios in PostgreSQL for the specified pairs under a user. Requires combined portfolio to exist."""
    created_portfolios_api: Dict[str, List[CreateAssetPortfolioResponseItem]] = {}
    try:
         combined_exists = db.query(CombinedPortfolioDB.cpmID).filter(CombinedPortfolioDB.cpmID == request.cpmID).first() # Efficient check
         if not combined_exists: raise HTTPException(status_code=400, detail="Missing combined portfolio. Please create one first.")

         newly_created_db_entries = []
         for pair in request.assetPortfolio:
             new_asset_id = str(uuid.uuid4())
             db_asset = AssetPortfolioDB(cpmID=request.cpmID, asset_portfolio_id=new_asset_id, pair=pair, status=DBPorfolioStatus.ACTIVE)
             db.add(db_asset); newly_created_db_entries.append(db_asset)
         db.commit()

         for db_entry in newly_created_db_entries:
             pair = db_entry.pair
             if pair not in created_portfolios_api: created_portfolios_api[pair] = []
             created_portfolios_api[pair].append(CreateAssetPortfolioResponseItem(id=db_entry.asset_portfolio_id, status=PortfolioStatus(db_entry.status.value)))
         print(f"Successfully created {len(newly_created_db_entries)} asset portfolios for {request.cpmID}")
         return CreateAssetPortfolioResponse(cpmID=request.cpmID, assetPortfolio=created_portfolios_api)
    except HTTPException: db.rollback(); raise
    except Exception as e: db.rollback(); print(f"Error creating asset portfolios for {request.cpmID}: {e}"); traceback.print_exc(); raise HTTPException(status_code=500, detail="Failed to create one or more asset portfolios.")

# --- Price and Event Endpoints (InfluxDB Only) ---

@app.post("/price", response_model=StatusResponse, status_code=status.HTTP_202_ACCEPTED)
async def record_price(data: PriceData, _=Depends(get_influx_status)):
    """Endpoint to record a market price update into InfluxDB."""
    try: write_price(data)
    except Exception as e: raise HTTPException(status_code=500, detail=f"Failed to write price: {e}") # Raise generic 500 if write fails
    return StatusResponse()

@app.post("/events", response_model=StatusResponse, status_code=status.HTTP_202_ACCEPTED)
async def record_event(data: EventData, _=Depends(get_influx_status)):
    """Endpoint to record a portfolio event into InfluxDB."""
    try: write_event(data)
    except Exception as e: raise HTTPException(status_code=500, detail=f"Failed to write event: {e}") # Raise generic 500 if write fails
    return StatusResponse()

# --- Background Job Trigger Endpoint ---

@app.post("/generate-portfolio-data", response_model=GenerateResponse, status_code=status.HTTP_202_ACCEPTED)
async def generate_portfolio_data(
    request: GenerateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _=Depends(get_influx_status)):
    """
    Triggers background calculation for specific asset portfolios.
    Looks up required cpmID and pair from PostgreSQL based on assetPortfolioIDs.
    """
    if not query_api or not write_api or not delete_api:
         raise HTTPException(status_code=503, detail="InfluxDB API clients not available.")

    tasks_to_run: List[Dict] = []
    processed_ids = set()
    not_found_or_inactive_ids = []

    print(f"Attempting to generate data for assetPortfolioIDs: {request.assetPortfolioID}")
    try:
        portfolio_metadata_db = db.query(AssetPortfolioDB).filter(
            AssetPortfolioDB.asset_portfolio_id.in_(request.assetPortfolioID)
        ).all()
        metadata_map = {p.asset_portfolio_id: p for p in portfolio_metadata_db}

        for requested_id in request.assetPortfolioID:
            if requested_id in metadata_map:
                meta = metadata_map[requested_id]
                if meta.status == DBPorfolioStatus.ACTIVE:
                    tasks_to_run.append({'cpmID': meta.cpmID, 'assetPortfolioID': meta.asset_portfolio_id, 'pair': meta.pair})
                    processed_ids.add(requested_id)
                else: not_found_or_inactive_ids.append(requested_id); print(f"Skipping inactive portfolio: {requested_id}")
            else: not_found_or_inactive_ids.append(requested_id); print(f"Warning: Metadata not found for assetPortfolioID: {requested_id}")

    except Exception as e: print(f"Error fetching metadata from PostgreSQL: {e}"); traceback.print_exc(); raise HTTPException(status_code=500, detail="Failed to retrieve portfolio metadata for background job.")

    if not tasks_to_run:
        details_msg = "No active portfolios found for the provided IDs."
        if not_found_or_inactive_ids: details_msg += f" IDs not found or inactive: {not_found_or_inactive_ids}."
        return GenerateResponse(status="No generation tasks initiated.", details=details_msg)

    num_tasks = 0
    for task_info in tasks_to_run:
        if query_api and write_api and delete_api:
            print(f"Adding background task for AssetPortfolioID: {task_info['assetPortfolioID']} (Pair: {task_info['pair']})")
            background_tasks.add_task(calculate_and_store_portfolio, **task_info, query_api=query_api, write_api=write_api, delete_api=delete_api)
            num_tasks += 1
        else: print(f"Skipping task for {task_info['assetPortfolioID']} due to unavailable InfluxDB API client.")

    details_msg = f"Initiated {num_tasks} generation task(s)."
    if not_found_or_inactive_ids: details_msg += f" IDs not found or inactive: {not_found_or_inactive_ids}."
    return GenerateResponse(details=details_msg)

# --- Query Endpoint ---

@app.post("/query-portfolio", response_model=QueryResponse, summary="Query Portfolio History by Asset IDs")
async def handle_query_portfolio_summary(request: QueryRequest, db: Session = Depends(get_db), _=Depends(get_influx_status)):
    """Queries pre-calculated summaries for specific asset portfolios using list of IDs and UTC time range."""
    results: List[PortfolioQueryResultItem] = []
    start_dt_utc_req = request.start_datetime_utc
    end_dt_utc_req = request.end_datetime_utc

    portfolio_metadata_map: Dict[str, AssetPortfolioDB] = {}
    try:
        metadata_db = db.query(AssetPortfolioDB).filter(AssetPortfolioDB.asset_portfolio_id.in_(request.assetPortfolioID), AssetPortfolioDB.cpmID == request.cpmID).all()
        portfolio_metadata_map = {p.asset_portfolio_id: p for p in metadata_db}
        print(f"Fetched metadata for {len(portfolio_metadata_map)} asset portfolios matching request.")
    except Exception as e: print(f"Error fetching metadata for query: {e}"); traceback.print_exc(); raise HTTPException(status_code=500, detail="Failed to retrieve portfolio metadata.")

    for asset_id in request.assetPortfolioID:
        portfolio_items_for_id = []
        pair_val = "Unknown"; status_val = PortfolioStatus.CLOSED; cpm_id_val = request.cpmID

        if asset_id in portfolio_metadata_map:
            meta = portfolio_metadata_map[asset_id]
            pair_val = meta.pair; status_val = PortfolioStatus(meta.status.value); cpm_id_val = meta.cpmID
        else:
            print(f"Warning: Metadata not found for assetPortfolioID: {asset_id} / cpmID {request.cpmID}")
            results.append(PortfolioQueryResultItem(cpmID=request.cpmID, pair="Unknown", assetPortfolioID=asset_id, status=PortfolioStatus.CLOSED, start_datetime_pht=start_dt_utc_req.astimezone(PHT), end_datetime_pht=end_dt_utc_req.astimezone(PHT), portfolio=[{"error": "Portfolio ID not found for this user."}]))
            continue

        try:
            # Use the imported alias for the influx query function
            summary_df = query_influx_summary(asset_id, start_dt_utc_req, end_dt_utc_req, query_api)

            if summary_df is not None and not summary_df.empty:
                 if '_time' in summary_df.columns:
                    summary_df['_time_pht'] = pd.to_datetime(summary_df['_time'], utc=True).dt.tz_convert(PHT)
                    summary_df['AUM'] = pd.to_numeric(summary_df.get('AUM'), errors='coerce').fillna(0.0)
                    summary_df['AVG_cost'] = pd.to_numeric(summary_df.get('AVG_cost'), errors='coerce').fillna(0.0)
                    summary_df['Realised_Value'] = pd.to_numeric(summary_df.get('Realised_Value'), errors='coerce').fillna(0.0)
                    summary_df['Unrealised_Value'] = pd.to_numeric(summary_df.get('Unrealised_Value'), errors='coerce')
                    for _, row in summary_df.iterrows():
                         row_time_pht = row.get('_time_pht')
                         if row_time_pht is None or pd.isna(row_time_pht): continue
                         portfolio_items_for_id.append(PortfolioItem(datetime_pht=row_time_pht, AUM=row['AUM'], AVG_cost=row['AVG_cost'], Unrealised_Value=None if pd.isna(row['Unrealised_Value']) else row['Unrealised_Value'], Realised_Value=row['Realised_Value']))
                 else: print(f"Warning: '_time' column missing for {asset_id}")

            results.append(PortfolioQueryResultItem(cpmID=cpm_id_val, pair=pair_val, assetPortfolioID=asset_id, status=status_val, start_datetime_pht=start_dt_utc_req.astimezone(PHT), end_datetime_pht=end_dt_utc_req.astimezone(PHT), portfolio=portfolio_items_for_id))
        except Exception as e:
            print(f"Error querying/processing summary for {asset_id}: {e}"); traceback.print_exc()
            results.append(PortfolioQueryResultItem(cpmID=cpm_id_val, pair=pair_val, assetPortfolioID=asset_id, status=status_val, start_datetime_pht=start_dt_utc_req.astimezone(PHT), end_datetime_pht=end_dt_utc_req.astimezone(PHT), portfolio=[{"error": "Error processing summary data."}]))

    return results

# --- Event Handlers ---
@app.on_event("startup")
async def startup_event():
    print("FastAPI application startup...")
    print("Attempting to create database tables if they don't exist...")
    create_db_tables()
    print("Checking InfluxDB connection...")
    if influx_client:
        try:
            if not influx_client.ping(): print("Warning: Initial InfluxDB ping failed.")
            else: print("Initial InfluxDB ping successful.")
        except Exception as e: print(f"Warning: Error during initial InfluxDB ping: {e}")
    else: print("CRITICAL: InfluxDB client failed to initialize.")
    print("Startup checks complete.")

@app.on_event("shutdown")
def shutdown_event():
    print("FastAPI application shutting down...")
    close_influx_client()

# --- Main Execution ---
if __name__ == "__main__":
    print(f"Starting Uvicorn server on {settings.api_host}:{settings.api_port}")
    uvicorn.run( "main:app", host=settings.api_host, port=settings.api_port, reload=True)
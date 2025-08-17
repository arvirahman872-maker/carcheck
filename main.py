from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from playwright.sync_api import sync_playwright
import pandas as pd
from sqlalchemy import create_engine, Column, Integer, String, Float, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
import time
import logging  # For debugging

app = FastAPI()
Base = declarative_base()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# DB Setup: Use Render's DATABASE_URL or fallback to SQLite for local testing
# DB Setup: Use Render's DATABASE_URL or fallback to SQLite for local testing
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///cardb.db')

# Fix for Render: Rewrite 'postgres://' to 'postgresql+psycopg://' to explicitly use psycopg3
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql+psycopg://', 1)

try:
    ENGINE = create_engine(
        DATABASE_URL,
        connect_args={'check_same_thread': False} if 'sqlite' in DATABASE_URL else {},
        pool_pre_ping=True  # Add this to handle potential connection timeouts/closures on Render
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=ENGINE)
    Base.metadata.create_all(bind=ENGINE)
    logger.info(f"Connected to database: {DATABASE_URL}")
except Exception as e:
    logger.error(f"Database connection failed: {str(e)}")
    raise

# Simple Car Model
class Car(Base):
    __tablename__ = 'cars'
    id = Column(Integer, primary_key=True, index=True)
    make = Column(String)
    model = Column(String)
    year = Column(Integer)
    mileage = Column(Integer)
    price = Column(Float)
    location = Column(String)
    resale_value = Column(Float)
    profit_margin = Column(Float)

# Low-Effort Scraping (AutoScout24)
def scrape_cars(make: str, model: str, max_price: float):
    data = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_extra_http_headers({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
        try:
            page.goto(f"https://www.autoscout24.be/fr/lst/{make}/{model}?price_to={max_price}&sort=price_asc")
            time.sleep(3)
            listings = page.query_selector_all('.ListItem_wrapper__J_a_C')[:20]
            for listing in listings:
                try:
                    title = listing.query_selector('.ListItem_title__znV2I').inner_text()
                    price_str = listing.query_selector('.Price_price__WZayw').inner_text().replace('€', '').replace('.', '').strip()
                    price = float(price_str) if price_str else 0
                    mileage_str = listing.query_selector('.VehicleDetailTable_item__koKmA:nth-child(2)').inner_text().replace(' km', '').replace('.', '')
                    mileage = int(mileage_str) if mileage_str else 0
                    year = int(title.split()[0]) if title.split()[0].isdigit() else 2020
                    data.append({'make': make, 'model': model, 'year': year, 'mileage': mileage, 'price': price, 'location': 'BE'})
                except Exception as e:
                    logger.warning(f"Error scraping listing: {str(e)}")
            browser.close()
        except Exception as e:
            logger.error(f"Scraping failed: {str(e)}")
    return pd.DataFrame(data)

class SearchProfile(BaseModel):
    make: str
    model: str
    max_price: float

@app.post("/scrape-and-analyze")
def scrape_and_analyze(profile: SearchProfile):
    df = scrape_cars(profile.make, profile.model, profile.max_price)
    if df.empty:
        raise HTTPException(status_code=404, detail="No cars found")
    
    # Rule-Based "AI"
    df['resale_value'] = df['price'] * 1.15 - (df['mileage'] / 1000) * 10
    df['costs'] = 300
    df['profit_margin'] = df['resale_value'] - df['price'] - df['costs']
    
    # Store in DB
    try:
        db = SessionLocal()
        for _, row in df.iterrows():
            car = Car(**row.to_dict())
            db.add(car)
        db.commit()
        db.close()
    except Exception as e:
        logger.error(f"Database write failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Database error")
    
    return df.to_dict(orient='records')

@app.get("/get-cars")
def get_cars():
    try:
        db = SessionLocal()
        result = db.execute(text("SELECT * FROM cars LIMIT 50")).fetchall()
        db.close()
        return [dict(row._mapping) for row in result]
    except Exception as e:
        logger.error(f"Database read failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Database error")

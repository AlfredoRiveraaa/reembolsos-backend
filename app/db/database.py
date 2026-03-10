import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, URL
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()

connection_url = URL.create(
    "mssql+pyodbc",
    host=os.getenv("DB_HOST"),
    database=os.getenv("DB_NAME"),
    query={
        "driver": "ODBC Driver 17 for SQL Server",
        "Trusted_Connection": "yes",
        "TrustServerCertificate": "yes"
    }
)

engine = create_engine(connection_url)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
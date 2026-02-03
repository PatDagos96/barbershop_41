from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

# --- URL DEL DATABASE ---
# NOTA: Ho rimosso "channel_binding=require" che spesso blocca Render
DATABASE_URL = "postgresql://neondb_owner:npg_7PECzDsQx1lT@ep-gentle-meadow-ahzxk371-pooler.c-3.us-east-1.aws.neon.tech/neondb?sslmode=require"

# Correzione automatica per compatibilità
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Creazione del motore di connessione
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # Controlla se la connessione è viva prima di usarla
    pool_recycle=300,    # Ricicla le connessioni ogni 5 minuti
    pool_size=5,
    max_overflow=10
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
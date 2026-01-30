from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Sostituisci la stringa qui sotto con quella che hai copiato da Neon.tech
# Deve iniziare con postgres:// e finire con .neon.tech/neondb... (o simile)
# IMPORTANTE: Se la stringa inizia con "postgres://", cambiala in "postgresql://" (aggiungi la 'ql')
DATABASE_URL = "postgresql://neondb_owner:npg_7PECzDsQx1lT@ep-gentle-meadow-ahzxk371-pooler.c-3.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require'"

# Correzione automatica per un piccolo bug di compatibilità (se serve)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Creazione del motore di connessione
engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
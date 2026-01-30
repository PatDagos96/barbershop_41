from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session
from sqlalchemy import extract
import models, database, secrets
from datetime import datetime

# Configurazione Iniziale
models.Base.metadata.create_all(bind=database.engine)
app = FastAPI()
security = HTTPBasic()

# --- CONFIGURAZIONE ORARI NEGOZIO ---
ORA_APERTURA = 9  # 9:00
ORA_CHIUSURA = 19 # 19:00 (L'ultimo taglio sarà alle 18:00)
DURATA_SLOT = 1   # Durata in ore (es. 1 ora a cliente)

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

def controlla_credenziali(credentials: HTTPBasicCredentials = Depends(security)):
    username_corretto = secrets.compare_digest(credentials.username, "admin")
    password_corretta = secrets.compare_digest(credentials.password, "password123")
    if not (username_corretto and password_corretta):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenziali errate", headers={"WWW-Authenticate": "Basic"})
    return credentials.username

# --- PAGINE WEB ---
@app.get("/")
def home():
    return FileResponse("index.html")

@app.get("/admin")
def pannello_admin(username: str = Depends(controlla_credenziali)):
    return FileResponse("admin.html")

# --- API (IL CERVELLO) ---

# NUOVA FUNZIONE: Calcola gli orari liberi per una data specifica
@app.get("/orari-disponibili")
def get_orari(data: str, db: Session = Depends(get_db)):
    # 1. Genera tutti gli orari possibili della giornata
    orari_possibili = []
    for h in range(ORA_APERTURA, ORA_CHIUSURA, DURATA_SLOT):
        orario_formattato = f"{h:02d}:00" # Trasforma 9 in "09:00"
        orari_possibili.append(orario_formattato)
    
    # 2. Chiede al DB quali sono già occupati in quella data
    prenotazioni = db.query(models.Appointment).filter(models.Appointment.data == data).all()
    orari_occupati = [p.ora for p in prenotazioni]

    # 3. Sottrae gli occupati dai possibili
    orari_liberi = [ora for ora in orari_possibili if ora not in orari_occupati]
    
    return {"orari": orari_liberi}

@app.post("/prenota")
def prenota(nome: str, servizio: str, data: str, ora: str, db: Session = Depends(get_db)):
    # Verifica doppia sicurezza
    esiste = db.query(models.Appointment).filter(models.Appointment.data == data, models.Appointment.ora == ora).first()
    if esiste:
        raise HTTPException(status_code=400, detail="Orario appena occupato da un altro cliente!")
    
    nuova = models.Appointment(cliente=nome, servizio=servizio, data=data, ora=ora)
    db.add(nuova)
    db.commit()
    return {"status": "successo", "messaggio": "Prenotazione Confermata!"}

@app.get("/lista_appuntamenti")
def lista(db: Session = Depends(get_db)):
    return db.query(models.Appointment).order_by(models.Appointment.data, models.Appointment.ora).all()

@app.delete("/cancella/{id}")
def cancella(id: int, db: Session = Depends(get_db)):
    item = db.query(models.Appointment).filter(models.Appointment.id == id).first()
    if item:
        db.delete(item)
        db.commit()
    return {"ok": True}
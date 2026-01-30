from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import models, database, secrets

# Configurazione Iniziale
models.Base.metadata.create_all(bind=database.engine)
app = FastAPI()
security = HTTPBasic()

# --- ORARI ---
ORA_APERTURA = 9
ORA_CHIUSURA = 19
DURATA_SLOT = 1

# Modello dati per la richiesta di modifica (Pydantic)
class PrenotazioneUpdate(BaseModel):
    cliente: str
    telefono: str
    servizio: str
    data: str
    ora: str
    note: Optional[str] = ""

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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenziali errate",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

# --- PAGINE ---
@app.get("/")
def home():
    return FileResponse("index.html")

@app.get("/admin")
def pannello_admin(username: str = Depends(controlla_credenziali)):
    return FileResponse("admin.html")

# --- API ---

@app.get("/orari-disponibili")
def get_orari(data: str, db: Session = Depends(get_db)):
    orari_possibili = [f"{h:02d}:00" for h in range(ORA_APERTURA, ORA_CHIUSURA, DURATA_SLOT)]
    prenotazioni = db.query(models.Appointment).filter(models.Appointment.data == data).all()
    orari_occupati = [p.ora for p in prenotazioni]
    orari_liberi = [ora for ora in orari_possibili if ora not in orari_occupati]
    return {"orari": orari_liberi}

@app.post("/prenota")
def prenota(nome: str, telefono: str, servizio: str, data: str, ora: str, note: str = "", db: Session = Depends(get_db)):
    esiste = db.query(models.Appointment).filter(models.Appointment.data == data, models.Appointment.ora == ora).first()
    if esiste:
        raise HTTPException(status_code=400, detail="Orario appena occupato!")
    
    nuova = models.Appointment(cliente=nome, telefono=telefono, servizio=servizio, data=data, ora=ora, note=note)
    db.add(nuova)
    db.commit()
    return {"status": "successo", "messaggio": "Prenotazione Confermata!"}

@app.get("/lista_appuntamenti")
def lista(db: Session = Depends(get_db)):
    # Ordina per Data e poi per Ora
    return db.query(models.Appointment).order_by(models.Appointment.data, models.Appointment.ora).all()

# NUOVO: API per Modificare
@app.put("/modifica/{id}")
def modifica_appuntamento(id: int, app_update: PrenotazioneUpdate, db: Session = Depends(get_db)):
    prenotazione = db.query(models.Appointment).filter(models.Appointment.id == id).first()
    if not prenotazione:
        raise HTTPException(status_code=404, detail="Appuntamento non trovato")

    # Controlla se il nuovo orario è libero (solo se data o ora sono cambiate)
    if (prenotazione.data != app_update.data) or (prenotazione.ora != app_update.ora):
        occupato = db.query(models.Appointment).filter(
            models.Appointment.data == app_update.data, 
            models.Appointment.ora == app_update.ora,
            models.Appointment.id != id # Escludi se stesso
        ).first()
        if occupato:
             raise HTTPException(status_code=400, detail="Il nuovo orario scelto è già occupato!")

    # Aggiorna i dati
    prenotazione.cliente = app_update.cliente
    prenotazione.telefono = app_update.telefono
    prenotazione.servizio = app_update.servizio
    prenotazione.data = app_update.data
    prenotazione.ora = app_update.ora
    prenotazione.note = app_update.note
    
    db.commit()
    return {"messaggio": "Appuntamento modificato con successo"}

@app.delete("/cancella/{id}")
def cancella(id: int, db: Session = Depends(get_db)):
    item = db.query(models.Appointment).filter(models.Appointment.id == id).first()
    if item:
        db.delete(item)
        db.commit()
    return {"ok": True}
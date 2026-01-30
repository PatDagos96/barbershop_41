from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import models, database, secrets
import requests 
import os # <--- IMPORTANTE: Serve per leggere le variabili segrete dal sistema

# Configurazione Iniziale
models.Base.metadata.create_all(bind=database.engine)
app = FastAPI()
security = HTTPBasic()

# --- ORARI ---
ORA_APERTURA = 9
ORA_CHIUSURA = 19
DURATA_SLOT = 1

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

# --- NUOVA FUNZIONE TELEGRAM SICURA ---
def invia_telegram_admin(messaggio):
    # I dati ora vengono letti dalle "Variabili d'Ambiente" del server (Render)
    # Non sono più scritti in chiaro nel codice!
    # Se sei in locale, assicurati di averle impostate o il bot non partirà.
    BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
    
    # Controllo di sicurezza: se mancano le chiavi, non crashare, avvisa solo nei log
    if not BOT_TOKEN or not CHAT_ID:
        print("⚠️ Telegram non configurato: mancano le variabili d'ambiente (TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID) su Render!")
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": messaggio,
        "parse_mode": "Markdown"
    }
    
    try:
        requests.post(url, json=payload)
        print("✅ Notifica Telegram inviata!")
    except Exception as e:
        print(f"❌ Errore Telegram: {e}")

# --- PAGINE WEB ---
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
    
    # --- INVIO NOTIFICA TELEGRAM ---
    msg = f"🔔 *NUOVA PRENOTAZIONE*\n\n👤 {nome}\n✂️ {servizio}\n📅 {data} alle {ora}\n📞 {telefono}"
    if note:
        msg += f"\n📝 Note: {note}"
        
    invia_telegram_admin(msg)
    # -------------------------------

    return {"status": "successo", "messaggio": "Prenotazione Confermata!"}

@app.get("/lista_appuntamenti")
def lista(db: Session = Depends(get_db)):
    return db.query(models.Appointment).order_by(models.Appointment.data, models.Appointment.ora).all()

@app.put("/modifica/{id}")
def modifica_appuntamento(id: int, app_update: PrenotazioneUpdate, db: Session = Depends(get_db)):
    prenotazione = db.query(models.Appointment).filter(models.Appointment.id == id).first()
    if not prenotazione:
        raise HTTPException(status_code=404, detail="Appuntamento non trovato")

    if (prenotazione.data != app_update.data) or (prenotazione.ora != app_update.ora):
        occupato = db.query(models.Appointment).filter(
            models.Appointment.data == app_update.data, 
            models.Appointment.ora == app_update.ora,
            models.Appointment.id != id
        ).first()
        if occupato:
             raise HTTPException(status_code=400, detail="Il nuovo orario scelto è già occupato!")

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
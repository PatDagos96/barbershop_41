from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, Dict, List, Any
import models, database, secrets
import requests 
import os 
import json
from datetime import datetime, timedelta

# --- CONFIGURAZIONE INIZIALE ---
models.Base.metadata.create_all(bind=database.engine)
app = FastAPI()
security = HTTPBasic()

# File dove salviamo orari e ferie (persistenza leggera)
SETTINGS_FILE = "settings.json"

# Abilitiamo CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 1. GESTIONE IMPOSTAZIONI ---
DEFAULT_SETTINGS = {
    "weekly": {
        "Monday": {"open": False, "start": "09:00", "end": "19:00"},
        "Tuesday": {"open": True, "start": "09:00", "end": "19:00"},
        "Wednesday": {"open": True, "start": "09:00", "end": "19:00"},
        "Thursday": {"open": True, "start": "09:00", "end": "19:00"},
        "Friday": {"open": True, "start": "09:00", "end": "19:00"},
        "Saturday": {"open": True, "start": "09:00", "end": "18:00"},
        "Sunday": {"open": False, "start": "09:00", "end": "13:00"}
    },
    "holidays": [] 
}

def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "w") as f:
            json.dump(DEFAULT_SETTINGS, f)
        return DEFAULT_SETTINGS
    with open(SETTINGS_FILE, "r") as f:
        return json.load(f)

def save_settings_to_file(settings_data):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings_data, f)

# --- MODELLI PYDANTIC ---
class PrenotazioneUpdate(BaseModel):
    cliente: str
    telefono: str
    servizio: str
    data: str
    ora: str
    note: Optional[str] = ""
    staff: Optional[str] = "Barbiere" # NUOVO CAMPO

class SettingsModel(BaseModel):
    weekly: Dict[str, Any]
    holidays: List[str]

class ListaID(BaseModel):
    ids: List[int]

# --- DIPENDENZE ---
def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

def controlla_credenziali(credentials: HTTPBasicCredentials = Depends(security)):
    # Modifica qui username/password se vuoi cambiarli
    username_corretto = secrets.compare_digest(credentials.username, "admin")
    password_corretta = secrets.compare_digest(credentials.password, "password123")
    if not (username_corretto and password_corretta):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenziali errate",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

# --- TELEGRAM ---
def invia_telegram_admin(messaggio):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "INSERISCI_TOKEN") 
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "INSERISCI_CHAT_ID")
    
    if "INSERISCI" in token: 
        print("⚠️ Telegram Token non configurato.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": messaggio, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"❌ Errore Telegram: {e}")

# --- PAGINE WEB ---
@app.get("/")
def home():
    return FileResponse("index.html")

@app.get("/manifest.json")
def get_manifest():
    return FileResponse("manifest.json")

@app.get("/icon.svg")
def get_icon():
    return FileResponse("icon.svg")

@app.get("/admin")
def pannello_admin(username: str = Depends(controlla_credenziali)):
    return FileResponse("admin.html")

# --- API ---

@app.get("/settings")
def get_settings_api():
    return load_settings()

@app.post("/settings")
def update_settings_api(settings: SettingsModel): 
    save_settings_to_file(settings.dict())
    return {"message": "Impostazioni aggiornate"}

@app.get("/orari-disponibili")
def get_orari(data: str, db: Session = Depends(get_db)):
    settings = load_settings()
    
    if data in settings["holidays"]:
        return {"orari": [], "message": "Chiuso per ferie"}

    try:
        date_obj = datetime.strptime(data, "%Y-%m-%d")
        day_name = date_obj.strftime("%A")
    except ValueError:
        return {"orari": [], "message": "Data non valida"}

    day_config = settings["weekly"].get(day_name)

    if not day_config or not day_config["open"]:
        return {"orari": [], "message": "Giorno di chiusura"}

    start_time = datetime.strptime(day_config["start"], "%H:%M")
    end_time = datetime.strptime(day_config["end"], "%H:%M")
    
    orari_possibili = []
    current = start_time
    while current < end_time:
        orari_possibili.append(current.strftime("%H:%M"))
        current += timedelta(minutes=30)

    # Nota: Qui potremmo filtrare per staff se volessimo gestire due agende parallele.
    # Per ora lasciamo semplice: se uno slot è occupato da CHIUNQUE, è occupato.
    prenotazioni = db.query(models.Appointment).filter(models.Appointment.data == data).all()
    orari_occupati = [p.ora for p in prenotazioni]
    
    orari_liberi = [ora for ora in orari_possibili if ora not in orari_occupati]
    
    return {"orari": orari_liberi}

@app.post("/prenota")
def prenota(nome: str, telefono: str, servizio: str, data: str, ora: str, note: str = "", db: Session = Depends(get_db)):
    settings = load_settings()
    
    if data in settings["holidays"]:
        raise HTTPException(status_code=400, detail="Chiuso per ferie!")

    try:
        date_obj = datetime.strptime(data, "%Y-%m-%d")
        day_name = date_obj.strftime("%A") 
    except ValueError:
        raise HTTPException(status_code=400, detail="Data non valida")

    day_config = settings["weekly"].get(day_name)
    if not day_config or not day_config["open"]:
        raise HTTPException(status_code=400, detail=f"Chiuso di {day_name}!")

    esiste = db.query(models.Appointment).filter(models.Appointment.data == data, models.Appointment.ora == ora).first()
    if esiste:
        raise HTTPException(status_code=400, detail="Orario occupato!")
    
    # Default staff="Barbiere" per le prenotazioni pubbliche
    nuova = models.Appointment(
        cliente=nome, 
        telefono=telefono, 
        servizio=servizio, 
        data=data, 
        ora=ora, 
        note=note,
        staff="Barbiere" 
    )
    db.add(nuova)
    db.commit()
    
    invia_telegram_admin(f"🔔 *PRENOTAZIONE WEB*\n👤 {nome}\n📅 {data} {ora}\n📞 {telefono}")

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
             raise HTTPException(status_code=400, detail="Orario già occupato!")

    prenotazione.cliente = app_update.cliente
    prenotazione.telefono = app_update.telefono
    prenotazione.servizio = app_update.servizio
    prenotazione.data = app_update.data
    prenotazione.ora = app_update.ora
    prenotazione.note = app_update.note
    prenotazione.staff = app_update.staff # Aggiorniamo lo staff
    
    db.commit()
    return {"messaggio": "Modificato con successo"}

@app.delete("/cancella/{id}")
def cancella(id: int, db: Session = Depends(get_db)):
    item = db.query(models.Appointment).filter(models.Appointment.id == id).first()
    if item:
        db.delete(item)
        db.commit()
    return {"ok": True}

@app.post("/cancella-multipli")
def cancella_multipli(lista: ListaID, db: Session = Depends(get_db)):
    db.query(models.Appointment).filter(models.Appointment.id.in_(lista.ids)).delete(synchronize_session=False)
    db.commit()
    return {"ok": True}

@app.get("/cerca-cliente")
def cerca_cliente(q: str, db: Session = Depends(get_db)):
    risultati = db.query(models.Appointment).filter(
        (models.Appointment.cliente.ilike(f"%{q}%")) | 
        (models.Appointment.telefono.ilike(f"%{q}%"))
    ).order_by(models.Appointment.data.desc(), models.Appointment.ora).all()
    
    return risultati
from sqlalchemy import Column, Integer, String
from database import Base

class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True)
    cliente = Column(String, index=True)
    telefono = Column(String)
    servizio = Column(String)
    data = Column(String) # Formato YYYY-MM-DD
    ora = Column(String)  # Formato HH:MM
    note = Column(String, nullable=True)
    
    # NUOVA COLONNA: Chi esegue il lavoro?
    # Default = "Barbiere" (così i vecchi appuntamenti non si rompono)
    staff = Column(String, default="Barbiere")
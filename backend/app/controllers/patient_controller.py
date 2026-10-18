from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.core.exceptions import DuplicateResourceError, ResourceNotFoundError
from app.schemas.patient import PatientCreate, PatientRead, PatientUpdate
from app.services.patient_service import PatientService

class PatientController:
    def __init__(self, service: PatientService | None = None):
        self.service = service or PatientService()
    def create(self, db: Session, data: PatientCreate, owner_user_id: int) -> PatientRead:
        try: return self.service.create_patient(db, data, owner_user_id)
        except DuplicateResourceError as exc: raise HTTPException(status_code=409, detail=str(exc)) from exc
    def list(self, db: Session, skip: int, limit: int, owner_user_id: int):
        return self.service.list_patients(db, owner_user_id, skip, limit)
    def get(self, db: Session, patient_id: int, owner_user_id: int):
        try: return self.service.get_patient(db, patient_id, owner_user_id)
        except ResourceNotFoundError as exc: raise HTTPException(status_code=404, detail=str(exc)) from exc
    def update(self, db: Session, patient_id: int, data: PatientUpdate, owner_user_id: int):
        try: return self.service.update_patient(db, patient_id, data, owner_user_id)
        except ResourceNotFoundError as exc: raise HTTPException(status_code=404, detail=str(exc)) from exc
        except DuplicateResourceError as exc: raise HTTPException(status_code=409, detail=str(exc)) from exc
    def delete(self, db: Session, patient_id: int, owner_user_id: int):
        try: self.service.delete_patient(db, patient_id, owner_user_id)
        except ResourceNotFoundError as exc: raise HTTPException(status_code=404, detail=str(exc)) from exc

patient_controller = PatientController()

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models, schemas

router = APIRouter()

# test for echo
@router.post("/echo")
def echo(payload: dict):
    return {"you sent": payload}

@router.get("/hello")
def hello():
    return {"message": "Hello, Taipei Hackathon!"}

@router.get("/users", response_model=list[schemas.UserOut])
def list_users(db: Session = Depends(get_db)):
    return db.query(models.User).order_by(models.User.id).all()

@router.post("/users", response_model=schemas.UserOut)
def create_user(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    u = models.User(name=payload.name)
    db.add(u); db.commit(); db.refresh(u); return u


# TestRecord endpoints
@router.get("/test_records", response_model=list[schemas.TestOut])
def list_test_records(db: Session = Depends(get_db)):
    return db.query(models.TestRecord).order_by(models.TestRecord.id).all()


@router.post("/test_records", response_model=schemas.TestOut)
def create_test_record(payload: schemas.TestCreate, db: Session = Depends(get_db)):
    tr = models.TestRecord(title=payload.title, description=payload.description)
    db.add(tr)
    db.commit()
    db.refresh(tr)
    return tr


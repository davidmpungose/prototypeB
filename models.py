from sqlalchemy import Column, Integer, String, Float, Date, ForeignKey
from sqlalchemy.orm import relationship
from .database import Base
from sqlalchemy.orm import Session
from datetime import date, timedelta


class Borrower(Base):
    __tablename__ = "borrowers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    phone = Column(String, nullable=False)

    loans = relationship("Loan", back_populates="borrower")


class Loan(Base):
    __tablename__ = "loans"

    id = Column(Integer, primary_key=True, index=True)
    borrower_id = Column(Integer, ForeignKey("borrowers.id"))
    amount = Column(Float, nullable=False)
    date = Column(Date, nullable=False)
    status = Column(String, default="Active")

    borrower = relationship("Borrower", back_populates="loans")
    payments = relationship("Payment", back_populates="loan")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    loan_id = Column(Integer, ForeignKey("loans.id"))
    amount = Column(Float, nullable=False)
    date = Column(Date, nullable=False)

    loan = relationship("Loan", back_populates="payments")


def loan_balance(db: Session, loan_id: int):
    loan = db.query(Loan).filter(Loan.id == loan_id).first()
    payments = db.query(Payment).filter(Payment.loan_id == loan_id).all()
    received = sum(p.amount for p in payments)
    return loan.amount - received


def is_overdue(loan, balance):
    due_date = loan.date + timedelta(days=30)
    return date.today() > due_date and balance > 0


class TransactionLog(Base):
    __tablename__ = "transaction_logs"

    id = Column(Integer, primary_key=True)
    type = Column(String)  # "loan", "payment"
    amount = Column(Float)
    date = Column(Date)
    loan_id = Column(Integer, ForeignKey("loans.id"))

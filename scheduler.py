from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Loan, Payment
from datetime import date, timedelta


def check_overdue_loans():
    db: Session = SessionLocal()
    loans = db.query(Loan).all()

    for loan in loans:
        payments = db.query(Payment).filter(Payment.loan_id == loan.id).all()
        received = sum(p.amount for p in payments)
        balance = loan.amount - received

        due_date = loan.date + timedelta(days=30)
        if date.today() > due_date and balance > 0:
            loan.status = "Overdue"
            db.commit()

    db.close()


scheduler = BackgroundScheduler()
scheduler.add_job(check_overdue_loans, "interval", days=1)
scheduler.start()

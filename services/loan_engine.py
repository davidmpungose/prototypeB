from database import SessionLocal
from models import Loan

from datetime import date, timedelta


def is_overdue(loan, balance):
    """Returns True if a loan is overdue and still has a balance."""
    if balance <= 0:
        return False

    due_date = loan.date + timedelta(days=30)
    return date.today() > due_date

from fastapi import FastAPI, Request,   Form, Depends
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Form
from fastapi.responses import RedirectResponse
from database import engine
from models import Borrower, Loan, Payment, Base, loan_balance, TransactionLog

from sqlalchemy.orm import Session
from database import get_db
from fastapi import BackgroundTasks
from scheduler import scheduler


app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ----- Dummy data for Day 2 -----

borrowers = [
    {"id": 1, "name": "John Dlamini", "phone": "76123456"},
    {"id": 2, "name": "Sindi Mabuza", "phone": "76234567"},
    {"id": 3, "name": "Themba Nxumalo", "phone": "76345678"},
]

loans = [
    {"id": 101, "borrower_id": 1, "amount": 1500,
        "status": "Active", "date": "2026-08-10"},
    {"id": 87, "borrower_id": 1, "amount": 800,
        "status": "Completed", "date": "2026-06-01"},
    {"id": 76, "borrower_id": 2, "amount": 2000,
        "status": "Overdue", "date": "2026-08-01"},
]

payments = [
    {"id": 1, "loan_id": 101, "amount": 300, "date": "2026-09-01"},
]

# Simple derived values for dashboard


def total_borrowers(db: Session):
    return db.query(Borrower).count()


def total_loans(db: Session):
    return db.query(Loan).count()


def total_money_lent(db: Session):
    return sum(l.amount for l in db.query(Loan).all())


def total_money_received(db: Session):
    return sum(p.amount for p in db.query(Payment).all())


def available_funds():
    return total_money_received()  # simple for prototype


def calculate_available_funds(db: Session):
    total_loans = db.query(Loan).all()
    total_payments = db.query(Payment).all()

    loans_amount = sum(l.amount for l in total_loans)
    payments_amount = sum(p.amount for p in total_payments)

    return payments_amount - loans_amount


# ----- Routes -----


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    context = {
        "request": request,
        "borrowers_count": total_borrowers(db),
        "loans_count": total_loans(db),
        "money_lent": total_money_lent(db),
        "money_received": total_money_received(db),
        "available": calculate_available_funds(db),
        "overdue_count": 2,        # fake
        "upcoming_count": 5,       # fake
    }
    return templates.TemplateResponse("dashboard.html", context)

# -----------------------------
# BORROWERS (STATIC ROUTES FIRST)
# -----------------------------


@app.get("/borrowers", response_class=HTMLResponse)
async def borrowers_list(request: Request, db: Session = Depends(get_db)):
    borrowers = db.query(Borrower).all()

    enriched = []

    for b in borrowers:
        # All loans for this borrower
        loans = db.query(Loan).filter(Loan.borrower_id == b.id).all()

        # All payments for this borrower (via loan_id)
        payments = (
            db.query(Payment)
            .join(Loan)
            .filter(Loan.borrower_id == b.id)
            .all()
        )

        total_loans = len(loans)
        total_paid = sum(p.amount for p in payments)
        total_borrowed = sum(l.amount for l in loans)
        outstanding = total_borrowed - total_paid

        enriched.append({
            "id": b.id,
            "name": b.name,
            "phone": b.phone,
            "total_loans": total_loans,
            "total_paid": total_paid,
            "outstanding": outstanding,
        })

    return templates.TemplateResponse(
        "borrowers.html",
        {
            "request": request,
            "borrowers": enriched,
        }
    )


@app.get("/borrowers/new", response_class=HTMLResponse)
async def add_borrower_form(request: Request):
    return templates.TemplateResponse(
        "add_borrower.html",
        {"request": request}
    )


@app.post("/borrowers/new")
async def add_borrower(
    name: str = Form(...),
    phone: str = Form(...),
    db: Session = Depends(get_db)
):
    borrower = Borrower(name=name, phone=phone)
    db.add(borrower)
    db.commit()
    db.refresh(borrower)

    return RedirectResponse(url="/borrowers", status_code=303)


# -----------------------------
# BORROWERS (DYNAMIC ROUTE LAST)
# -----------------------------

@app.get("/borrowers/{borrower_id}", response_class=HTMLResponse)
async def borrower_detail(request: Request, borrower_id: int, db: Session = Depends(get_db)):
    borrower = db.query(Borrower).filter(Borrower.id == borrower_id).first()
    if not borrower:
        return HTMLResponse("Borrower not found", status_code=404)

    # All loans for this borrower
    loans = db.query(Loan).filter(Loan.borrower_id == borrower_id).all()

    # All payments for this borrower (via loan_id)
    payments = db.query(Payment).join(Loan).filter(
        Loan.borrower_id == borrower_id).all()

    # Total borrowed
    total_borrowed = sum(l.amount for l in loans)

    # Total paid
    total_paid = sum(p.amount for p in payments)

    # Outstanding balance
    outstanding_balance = total_borrowed - total_paid

    # Active loans count
    active_loans = sum(1 for l in loans if l.status == "Active")

    # Compute balance per loan (for the table)
    enriched_loans = []
    for loan in loans:
        loan_payments = [p.amount for p in payments if p.loan_id == loan.id]
        balance = loan.amount - sum(loan_payments)

        enriched_loans.append({
            "id": loan.id,
            "amount": loan.amount,
            "date": loan.date,
            "status": loan.status,
            "balance": balance
        })

    return templates.TemplateResponse(
        "borrower_detail.html",
        {
            "request": request,
            "borrower": borrower,
            "loans": enriched_loans,
            "payments": payments,
            "total_borrowed": total_borrowed,
            "total_paid": total_paid,
            "outstanding_balance": outstanding_balance,
            "active_loans": active_loans,
        }
    )


# -----------------------------
# LOANS (STATIC ROUTES FIRST)
# -----------------------------


@app.get("/loans", response_class=HTMLResponse)
async def loans_list(request: Request, db: Session = Depends(get_db)):
    loans = db.query(Loan).all()
    balance = loan_balance(db, Loan.id)
    enriched = []

    for loan in loans:
        borrower = db.query(Borrower).filter(
            Borrower.id == loan.borrower_id).first()
        enriched.append({
            "id": loan.id,
            "amount": loan.amount,
            "date": loan.date,
            "status": loan.status,
            "balance": balance,
            "borrower_name": borrower.name if borrower else "Unknown"
        })

    return templates.TemplateResponse(
        "loans.html",
        {"request": request, "loans": enriched}
    )


@app.get("/loans/new", response_class=HTMLResponse)
async def add_loan_form(request: Request, db: Session = Depends(get_db)):
    borrowers = db.query(Borrower).all()
    return templates.TemplateResponse(
        "add_loan.html",
        {"request": request, "borrowers": borrowers}
    )


@app.post("/loans/new")
async def add_loan(
    borrower_id: int = Form(...),
    amount: float = Form(...),
    date: str = Form(...),
    db: Session = Depends(get_db)
):
    loan = Loan(
        borrower_id=borrower_id,
        amount=amount,
        date=date,
        status="Active"
    )
    db.add(loan)
    db.commit()
    db.refresh(loan)

    # Log the loan creation
    log = TransactionLog(
        type="loan",
        amount=amount,
        date=date,
        loan_id=loan.id
    )
    db.add(log)
    db.commit()

    return RedirectResponse(url="/loans", status_code=303)


# -----------------------------
# LOAN PAYMENTS (STATIC ROUTES)
# -----------------------------

@app.get("/loans/{loan_id}/pay", response_class=HTMLResponse)
async def record_payment_form(request: Request, loan_id: int, db: Session = Depends(get_db)):
    loan = db.query(Loan).filter(Loan.id == loan_id).first()
    return templates.TemplateResponse(
        "record_payment.html",
        {"request": request, "loan": loan}
    )


@app.post("/loans/{loan_id}/pay")
async def record_payment(
    loan_id: int,
    amount: float = Form(...),
    date: str = Form(...),
    db: Session = Depends(get_db)
):
    payment = Payment(
        loan_id=loan_id,
        amount=amount,
        date=date
    )
    db.add(payment)
    db.commit()

    # Log the payment
    log = TransactionLog(
        type="payment",
        amount=amount,
        date=date,
        loan_id=loan_id
    )
    db.add(log)
    db.commit()

    return RedirectResponse(url=f"/loans/{loan_id}", status_code=303)


# -----------------------------
# LOANS (DYNAMIC ROUTE LAST)
# -----------------------------


@app.get("/loans", response_class=HTMLResponse)
async def loans_list(request: Request, db: Session = Depends(get_db)):
    loans = db.query(Loan).all()
    enriched = []

    for loan in loans:
        # Borrower
        borrower = db.query(Borrower).filter(
            Borrower.id == loan.borrower_id).first()

        # Payments
        payments = db.query(Payment).filter(Payment.loan_id == loan.id).all()
        money_received = sum(p.amount for p in payments)

        # Balance
        balance = loan.amount - money_received

        # Overdue detection (30 days)
        from datetime import date, timedelta
        due_date = loan.date + timedelta(days=30)
        overdue = date.today() > due_date and balance > 0

        enriched.append({
            "id": loan.id,
            "amount": loan.amount,
            "date": loan.date,
            "status": loan.status,
            "borrower_name": borrower.name if borrower else "Unknown",
            "balance": balance,
            "overdue": overdue
        })

    return templates.TemplateResponse(
        "loans.html",
        {"request": request, "loans": enriched}
    )


# @app.get("/borrowers/add", response_class=HTMLResponse)
# async def add_borrower_form(request: Request):
#     return templates.TemplateResponse("add_borrower.html", {"request": request})


# @app.post("/borrowers/add")
# async def add_borrower(
#     name: str = Form(...),
#     phone: str = Form(...),
# ):
#     new_id = max(b["id"] for b in borrowers) + 1 if borrowers else 1
#     borrowers.append({
#         "id": new_id,
#         "name": name,
#         "phone": phone
#     })
#     return RedirectResponse(url="/borrowers", status_code=303)


# @app.get("/loans", response_class=HTMLResponse)
# async def loans_list(request: Request):
#     enriched = []
#     for l in loans:
#         borrower = next(b for b in borrowers if b["id"] == l["borrower_id"])
#         enriched.append({
#             **l,
#             "borrower_name": borrower["name"]
#         })
#     return templates.TemplateResponse("loans.html", {"request": request, "loans": enriched})


# @app.get("/loans/{loan_id}", response_class=HTMLResponse)
# async def loan_detail(request: Request, loan_id: int):
#     loan = next(l for l in loans if l["id"] == loan_id)
#     borrower = next(b for b in borrowers if b["id"] == loan["borrower_id"])
#     loan_payments = [p for p in payments if p["loan_id"] == loan_id]
#     money_received = sum(p["amount"] for p in loan_payments)
#     balance = loan["amount"] - money_received  # simple

#     return templates.TemplateResponse(
#         "loan_detail.html",
#         {
#             "request": request,
#             "loan": loan,
#             "borrower": borrower,
#             "payments": loan_payments,
#             "money_received": money_received,
#             "balance": balance,
#         },
#     )


@app.get("/loans/overdue", response_class=HTMLResponse)
async def overdue_loans(request: Request, db: Session = Depends(get_db)):
    loans = db.query(Loan).all()
    overdue_list = []

    for loan in loans:
        balance = loan_balance(db, loan.id)
        if is_overdue(loan, balance):
            borrower = db.query(Borrower).filter(
                Borrower.id == loan.borrower_id).first()
            overdue_list.append({
                "loan": loan,
                "borrower": borrower,
                "balance": balance
            })

    return templates.TemplateResponse(
        "overdue_loans.html",
        {"request": request, "loans": overdue_list}
    )


@app.get("/loans/{loan_id}", response_class=HTMLResponse)
async def loan_detail(request: Request, loan_id: int, db: Session = Depends(get_db)):
    loan = db.query(Loan).filter(Loan.id == loan_id).first()
    if not loan:
        return HTMLResponse("Loan not found", status_code=404)

    borrower = db.query(Borrower).filter(
        Borrower.id == loan.borrower_id).first()
    payments = db.query(Payment).filter(Payment.loan_id == loan_id).all()

    money_received = sum(p.amount for p in payments)
    balance = loan.amount - money_received

    return templates.TemplateResponse(
        "loan_detail.html",
        {
            "request": request,
            "loan": loan,
            "borrower": borrower,
            "payments": payments,
            "money_received": money_received,
            "balance": balance,
        },
    )


@app.get("/overdue", response_class=HTMLResponse)
async def overdue_loans(request: Request):
    overdue = [l for l in loans if l["status"] == "Overdue"]
    return templates.TemplateResponse("overdue_loans.html", {"request": request, "loans": overdue})


@app.get("/available-funds", response_class=HTMLResponse)
async def available_funds(request: Request, db: Session = Depends(get_db)):
    total_loans = db.query(Loan).all()
    total_payments = db.query(Payment).all()

    loans_amount = sum(l.amount for l in total_loans)
    payments_amount = sum(p.amount for p in total_payments)

    available = calculate_available_funds(db)

    return templates.TemplateResponse(
        "available_funds.html",
        {
            "request": request,
            "available": available,
            "loans_amount": loans_amount,
            "payments_amount": payments_amount
        }
    )


# -------------------------
# STATIC ROUTES FIRST
# -------------------------

# @app.get("/loans/add", response_class=HTMLResponse)
# async def add_loan_form(request: Request):
#     return templates.TemplateResponse("add_loan.html", {"request": request, "borrowers": borrowers})


# @app.post("/loans/add")
# async def add_loan(
#     borrower_id: int = Form(...),
#     amount: float = Form(...),
#     date: str = Form(...)
# ):
#     new_id = max(l["id"] for l in loans) + 1
#     loans.append({
#         "id": new_id,
#         "borrower_id": borrower_id,
#         "amount": amount,
#         "status": "Active",
#         "date": date
#     })
#     return RedirectResponse(url="/loans", status_code=303)


# -------------------------
# DYNAMIC ROUTES AFTER
# -------------------------

# @app.get("/loans/{loan_id}", response_class=HTMLResponse)
# async def loan_detail(request: Request, loan_id: int):
#     loan = next(l for l in loans if l["id"] == loan_id)
#     borrower = next(b for b in borrowers if b["id"] == loan["borrower_id"])
#     loan_payments = [p for p in payments if p["loan_id"] == loan_id]
#     money_received = sum(p["amount"] for p in loan_payments)
#     balance = loan["amount"] - money_received

#     return templates.TemplateResponse(
#         "loan_detail.html",
#         {
#             "request": request,
#             "loan": loan,
#             "borrower": borrower,
#             "payments": loan_payments,
#             "money_received": money_received,
#             "balance": balance,
#         },
#     )
# Table for SQL Alchemy models
Base.metadata.create_all(bind=engine)

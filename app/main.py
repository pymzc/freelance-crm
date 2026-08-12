from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db, init_db
from app.models import Client, Deal

BASE_DIR = Path(__file__).resolve().parent

CLIENT_STATUSES = {
    "lead": "Лид",
    "active": "В работе",
    "paused": "Пауза",
    "archived": "Архив",
}

DEAL_STAGES = {
    "new": "Новая",
    "proposal": "Предложение",
    "negotiation": "Переговоры",
    "won": "Выиграна",
    "lost": "Проиграна",
}


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Freelance CRM", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.filters["money"] = lambda value: f"{value:,.0f}".replace(",", " ")


def page_context(request: Request, **values: object) -> dict[str, object]:
    return {
        "request": request,
        "client_statuses": CLIENT_STATUSES,
        "deal_stages": DEAL_STAGES,
        **values,
    }


def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


def get_client_or_404(db: Session, client_id: int) -> Client:
    client = db.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Клиент не найден")
    return client


@app.get("/health", include_in_schema=False)
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Annotated[Session, Depends(get_db)]):
    client_count = db.scalar(select(func.count(Client.id))) or 0
    active_clients = db.scalar(
        select(func.count(Client.id)).where(Client.status == "active")
    ) or 0
    pipeline = db.scalar(
        select(func.coalesce(func.sum(Deal.amount), 0)).where(
            Deal.stage.not_in(("won", "lost"))
        )
    ) or 0
    won_total = db.scalar(
        select(func.coalesce(func.sum(Deal.amount), 0)).where(Deal.stage == "won")
    ) or 0
    recent_clients = db.scalars(
        select(Client).order_by(Client.created_at.desc()).limit(5)
    ).all()
    recent_deals = db.scalars(
        select(Deal)
        .options(selectinload(Deal.client))
        .order_by(Deal.created_at.desc())
        .limit(5)
    ).all()

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context=page_context(
            request,
            page="dashboard",
            title="Обзор",
            client_count=client_count,
            active_clients=active_clients,
            pipeline=pipeline,
            won_total=won_total,
            recent_clients=recent_clients,
            recent_deals=recent_deals,
        ),
    )


@app.get("/clients", response_class=HTMLResponse)
def clients_list(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    q: Annotated[str, Query(max_length=120)] = "",
    client_status: str = "",
):
    query = select(Client).order_by(Client.created_at.desc())
    if q:
        pattern = f"%{q.strip()}%"
        query = query.where(
            or_(
                Client.name.ilike(pattern),
                Client.company.ilike(pattern),
                Client.email.ilike(pattern),
            )
        )
    if client_status in CLIENT_STATUSES:
        query = query.where(Client.status == client_status)

    clients = db.scalars(query).all()
    return templates.TemplateResponse(
        request=request,
        name="clients.html",
        context=page_context(
            request,
            page="clients",
            title="Клиенты",
            clients=clients,
            q=q,
            selected_status=client_status,
        ),
    )


@app.get("/clients/new", response_class=HTMLResponse)
def client_new(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="client_form.html",
        context=page_context(
            request,
            page="clients",
            title="Новый клиент",
            client=None,
            form_action="/clients/new",
        ),
    )


@app.post("/clients/new")
def client_create(
    db: Annotated[Session, Depends(get_db)],
    name: Annotated[str, Form(min_length=2, max_length=120)],
    company: Annotated[str, Form(max_length=160)] = "",
    email: Annotated[str, Form(max_length=200)] = "",
    phone: Annotated[str, Form(max_length=60)] = "",
    client_status: Annotated[str, Form()] = "lead",
    note: Annotated[str, Form(max_length=2000)] = "",
):
    if client_status not in CLIENT_STATUSES:
        client_status = "lead"

    client = Client(
        name=name.strip(),
        company=company.strip(),
        email=email.strip(),
        phone=phone.strip(),
        status=client_status,
        note=note.strip(),
    )
    db.add(client)
    db.commit()
    db.refresh(client)
    return redirect(f"/clients/{client.id}?notice=Клиент добавлен")


@app.get("/clients/{client_id}", response_class=HTMLResponse)
def client_detail(
    request: Request,
    client_id: int,
    db: Annotated[Session, Depends(get_db)],
    notice: Annotated[str, Query(max_length=80)] = "",
):
    client = db.scalar(
        select(Client)
        .where(Client.id == client_id)
        .options(selectinload(Client.deals))
    )
    if client is None:
        raise HTTPException(status_code=404, detail="Клиент не найден")

    return templates.TemplateResponse(
        request=request,
        name="client_detail.html",
        context=page_context(
            request,
            page="clients",
            title=client.name,
            client=client,
            notice=notice,
        ),
    )


@app.get("/clients/{client_id}/edit", response_class=HTMLResponse)
def client_edit(
    request: Request,
    client_id: int,
    db: Annotated[Session, Depends(get_db)],
):
    client = get_client_or_404(db, client_id)
    return templates.TemplateResponse(
        request=request,
        name="client_form.html",
        context=page_context(
            request,
            page="clients",
            title="Редактирование",
            client=client,
            form_action=f"/clients/{client.id}/edit",
        ),
    )


@app.post("/clients/{client_id}/edit")
def client_update(
    client_id: int,
    db: Annotated[Session, Depends(get_db)],
    name: Annotated[str, Form(min_length=2, max_length=120)],
    company: Annotated[str, Form(max_length=160)] = "",
    email: Annotated[str, Form(max_length=200)] = "",
    phone: Annotated[str, Form(max_length=60)] = "",
    client_status: Annotated[str, Form()] = "lead",
    note: Annotated[str, Form(max_length=2000)] = "",
):
    client = get_client_or_404(db, client_id)
    client.name = name.strip()
    client.company = company.strip()
    client.email = email.strip()
    client.phone = phone.strip()
    client.status = client_status if client_status in CLIENT_STATUSES else "lead"
    client.note = note.strip()
    db.commit()
    return redirect(f"/clients/{client.id}?notice=Изменения сохранены")


@app.post("/clients/{client_id}/delete")
def client_delete(client_id: int, db: Annotated[Session, Depends(get_db)]):
    client = get_client_or_404(db, client_id)
    db.delete(client)
    db.commit()
    return redirect("/clients")


@app.get("/deals", response_class=HTMLResponse)
def deals_list(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    stage: str = "",
):
    query = (
        select(Deal)
        .options(selectinload(Deal.client))
        .order_by(Deal.created_at.desc())
    )
    if stage in DEAL_STAGES:
        query = query.where(Deal.stage == stage)

    deals = db.scalars(query).all()
    return templates.TemplateResponse(
        request=request,
        name="deals.html",
        context=page_context(
            request,
            page="deals",
            title="Сделки",
            deals=deals,
            selected_stage=stage,
        ),
    )


@app.get("/deals/new", response_class=HTMLResponse)
def deal_new(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    client_id: int | None = None,
):
    clients = db.scalars(select(Client).order_by(Client.name)).all()
    return templates.TemplateResponse(
        request=request,
        name="deal_form.html",
        context=page_context(
            request,
            page="deals",
            title="Новая сделка",
            clients=clients,
            selected_client_id=client_id,
        ),
    )


@app.post("/deals/new")
def deal_create(
    db: Annotated[Session, Depends(get_db)],
    title: Annotated[str, Form(min_length=2, max_length=180)],
    amount: Annotated[Decimal, Form(gt=0)],
    client_id: Annotated[int, Form()],
    stage: Annotated[str, Form()] = "new",
):
    get_client_or_404(db, client_id)
    if stage not in DEAL_STAGES:
        stage = "new"

    deal = Deal(
        title=title.strip(),
        amount=amount,
        client_id=client_id,
        stage=stage,
    )
    db.add(deal)
    db.commit()
    return redirect("/deals")


@app.post("/deals/{deal_id}/stage")
def deal_change_stage(
    deal_id: int,
    db: Annotated[Session, Depends(get_db)],
    stage: Annotated[str, Form()],
):
    deal = db.get(Deal, deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    if stage not in DEAL_STAGES:
        raise HTTPException(status_code=400, detail="Неизвестный этап")
    deal.stage = stage
    db.commit()
    return redirect("/deals")


@app.post("/deals/{deal_id}/delete")
def deal_delete(deal_id: int, db: Annotated[Session, Depends(get_db)]):
    deal = db.get(Deal, deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    db.delete(deal)
    db.commit()
    return redirect("/deals")

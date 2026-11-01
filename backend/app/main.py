from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    actions, audit, auth, bank_data, bills, cards, chat, health, security, subscriptions,
    transfers, wealth,
)
from app.core.config import settings
from app.db.seed import (
    seed_demo_accounts, seed_demo_cards, seed_demo_contacts, seed_demo_subscriptions,
    seed_demo_user, seed_demo_wealth,
)
from app.db.session import init_db, session_scope
from app.services.audit_service import request_context
from uuid import uuid4


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    from app.services.chat_submissions import recover_stale_submissions
    with session_scope() as session:
        recover_stale_submissions(session)
        user = seed_demo_user(session)
        seed_demo_accounts(session, user)
        seed_demo_cards(session, user)
        seed_demo_contacts(session, user)
        seed_demo_subscriptions(session, user)
        seed_demo_wealth(session, user)
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"detail": "请求参数无效"})


@app.middleware("http")
async def assign_audit_request(request, call_next):
    token = request_context.set(uuid4().hex)
    try:
        return await call_next(request)
    finally:
        request_context.reset(token)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix=settings.api_prefix)
app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(actions.router, prefix=settings.api_prefix)
app.include_router(audit.router, prefix=settings.api_prefix)
app.include_router(bank_data.router, prefix=settings.api_prefix)
app.include_router(wealth.router, prefix=settings.api_prefix)
app.include_router(subscriptions.router, prefix=settings.api_prefix)
app.include_router(bills.router, prefix=settings.api_prefix)
app.include_router(cards.router, prefix=settings.api_prefix)
app.include_router(security.router, prefix=settings.api_prefix)
app.include_router(transfers.router, prefix=settings.api_prefix)
app.include_router(chat.router, prefix=settings.api_prefix)


@app.get("/", include_in_schema=False)
def index() -> dict[str, str]:
    return {"name": settings.app_name, "docs": "/docs"}

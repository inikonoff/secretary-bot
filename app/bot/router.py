from aiogram import Router

from app.bot.handlers import admin, confirmation, help as help_handler, interview, new_application, start

root_router = Router(name="root")

# Order matters: admin's free-text catcher must run before interview's generic
# text handler, otherwise an admin's reply to "Написать"/"Добавить заметку"
# would be swallowed by the client-facing interview flow (see admin.py docstring).
root_router.include_router(admin.router)
root_router.include_router(start.router)
root_router.include_router(new_application.router)
root_router.include_router(help_handler.router)
root_router.include_router(confirmation.router)
root_router.include_router(interview.router)

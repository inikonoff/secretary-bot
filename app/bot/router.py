from aiogram import Router

from app.bot.handlers import (
    admin,
    admin_mode,
    confirmation,
    help as help_handler,
    interview,
    new_application,
    revisions,
    start,
)

root_router = Router(name="root")

# Order matters: admin's free-text catcher and revisions' composing-filter must both
# run before interview's generic text/voice handlers, otherwise an admin's reply to
# "Написать"/"Добавить заметку", or a client's revision description, would be
# swallowed by the plain interview/correspondence flow (see admin.py and
# revisions.py docstrings). admin_mode's /mode and mode_toggle: callback never
# collide with anything else, so its position doesn't matter.
root_router.include_router(admin.router)
root_router.include_router(admin_mode.router)
root_router.include_router(start.router)
root_router.include_router(new_application.router)
root_router.include_router(help_handler.router)
root_router.include_router(confirmation.router)
root_router.include_router(revisions.router)
root_router.include_router(interview.router)

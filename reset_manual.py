"""Reset vacancies with status 'manual' back to 'new' and reset search_current_page to 0."""

from __future__ import annotations

import asyncio
from sqlalchemy import delete, update

from app.db.database import get_session
from app.db.models import Application, ApplicationStatus, Vacancy, VacancyStatus
from app.db.repositories import set_setting


async def main() -> None:
    async with get_session() as session:
        stmt_vac = (
            update(Vacancy)
            .where(Vacancy.status == VacancyStatus.manual)
            .values(status=VacancyStatus.new)
        )
        res_vac = await session.execute(stmt_vac)

        stmt_app = delete(Application).where(Application.status == ApplicationStatus.manual)
        res_app = await session.execute(stmt_app)

        await set_setting(session, "search_current_page", "0")
        await session.commit()
        print(
            f"Successfully reset {res_vac.rowcount} vacancies back to 'new'. "
            f"Removed {res_app.rowcount} manual application records. "
            f"Search page reset to 0."
        )


if __name__ == "__main__":
    asyncio.run(main())

from collections.abc import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.sources import SourceGateway
from app.schemas.contracts import VacancySearch


class VacancyService:
    def __init__(self, session: AsyncSession, gateways: Iterable[SourceGateway]) -> None:
        self.session = session
        self.gateways = list(gateways)

    async def import_vacancies(self, query: VacancySearch) -> int:
        # TODO: select gateways by query.sources, execute concurrently, upsert on (source, external_id).
        # TODO: persist normalized vacancies and emit an import summary/audit event.
        return 0

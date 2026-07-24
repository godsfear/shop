"""Связанный справочник Country -> Place и его локализация."""
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from shop import tables
from shop.geography_seed import seed_geography
from shop.medical_seed import seed_medical
from shop.services.geography import GeographyService


URI = "postgresql+asyncpg://shop:secret@localhost:5432/shop"


async def test_main():
    engine = create_async_engine(URI, poolclass=NullPool)
    async with engine.begin() as connection:
        await connection.execute(text("DROP SCHEMA public CASCADE"))
        await connection.execute(text("CREATE SCHEMA public"))
        await connection.run_sync(tables.Root.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async with sessions() as session:
        await seed_medical(session)
        expected = await seed_geography(session)
    async with sessions() as session:
        counts = (
            (await session.execute(select(func.count()).select_from(tables.Country))).scalar_one(),
            (await session.execute(select(func.count()).select_from(tables.Place))).scalar_one(),
        )
    assert counts == expected

    # Повтор не создаёт дубликаты.
    async with sessions() as session:
        assert await seed_geography(session) == expected
    async with sessions() as session:
        repeated = (
            (await session.execute(select(func.count()).select_from(tables.Country))).scalar_one(),
            (await session.execute(select(func.count()).select_from(tables.Place))).scalar_one(),
        )
    assert repeated == counts

    # Связь по ISO2 и подписи из Translation работают на обоих языках.
    async with sessions() as session:
        service = GeographyService(session)
        countries_ru = await service.countries("ru")
        countries_en = await service.countries("en")
        cities_ru = await service.cities("kz", "ru")
        cities_en = await service.cities("kz", "en")
    assert next(item for item in countries_ru if item["code"] == "kz")["name"] == "Казахстан"
    assert next(item for item in countries_en if item["code"] == "kz")["name"] == "Kazakhstan"
    assert next(item for item in cities_ru if item["code"] == "Q487439")["name"] == "Уральск"
    assert next(item for item in cities_en if item["code"] == "Q487439")["name"] == "Oral"

    await engine.dispose()

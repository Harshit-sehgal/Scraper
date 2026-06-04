import asyncio


async def test_provider(provider) -> bool:
    import g4f

    try:
        await g4f.client.AsyncClient().chat.completions.create(
            model="gpt-4o-mini",  # or let the provider decide
            provider=provider,
            messages=[{"role": "user", "content": 'Hello, return exactly this JSON: [{"test": 123}]'}],
        )
        return True
    except Exception as e:
        import logging

        logging.exception(e)
        return False


async def main() -> None:
    import g4f

    providers = [
        g4f.Provider.PollinationsAI,
        g4f.Provider.BlackboxPro,
        g4f.Provider.FreeNetfly,
        g4f.Provider.Liaobots,
        g4f.Provider.ApiAirforce,
        g4f.Provider.DarkAI,
    ]
    for p in providers:
        await test_provider(p)


if __name__ == "__main__":
    asyncio.run(main())

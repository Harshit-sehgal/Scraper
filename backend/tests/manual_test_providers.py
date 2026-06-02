import asyncio


async def test_provider(provider):
    import g4f

    print(f"Testing {provider.__name__}...")
    try:
        response = await g4f.client.AsyncClient().chat.completions.create(
            model="gpt-4o-mini",  # or let the provider decide
            provider=provider,
            messages=[{"role": "user", "content": 'Hello, return exactly this JSON: [{"test": 123}]'}],
        )
        print(f"[SUCCESS] {provider.__name__}: {response.choices[0].message.content[:50]}")
        return True
    except Exception as e:
        import logging

        logging.exception(e)
        print(f"[FAILED] {provider.__name__}: {str(e)[:100]}")
        return False


async def main():
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

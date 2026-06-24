import asyncio
import ccxt.async_support as ccxt

async def main():
    print("ccxt.AuthenticationError is:", getattr(ccxt, "AuthenticationError", None))
    # Or check if it is in ccxt.base.errors
    try:
        import ccxt.base.errors as ccxt_errors
        print("ccxt_errors.AuthenticationError is:", getattr(ccxt_errors, "AuthenticationError", None))
    except ImportError:
        print("Could not import ccxt.base.errors")

asyncio.run(main())

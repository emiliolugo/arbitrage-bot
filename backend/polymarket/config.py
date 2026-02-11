import asyncio
from py_clob_client.client import ClobClient
from dotenv import load_dotenv
import os

load_dotenv()

host = "https://clob.polymarket.com"
chain_id = 137
private_key = os.getenv("POLYMARKET_PRIVATE_KEY")
if private_key is None:
    raise RuntimeError("POLYMARKET_PRIVATE_KEY is not set")


async def main():
    
    signature_type = 0
    client = ClobClient(
        host,
        key=private_key,
        chain_id=chain_id,
        signature_type=signature_type,
    )
    


if __name__ == "__main__":
    asyncio.run(main())

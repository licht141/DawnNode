import requests
import json
import time
import urllib3
import logging
import colorlog
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

# Constants
BALANCE_CHECK_INTERVAL = 120  # seconds
EXTENSION_ID = "fpdkjdnhkakefebpekbdhillbhonfjjp"
VERSION = "1.0.9"
# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Load config
with open('dawn.json', 'r') as f:
    config = json.load(f)

# Setup API endpoints and headers
api_balance = config['api']['url1']
api_keep_alive = config['api']['url2']
user_id = config['settings']['user_id']
token = config['settings']['token']
use_proxy = config['settings'].get('use_proxy', True)
proxy_list_file = config['network'].get('proxy_list', None)

headers = {
    'authority': 'www.aeropres.in',
    'accept': '*/*',
    'accept-language': 'en-US,en;q=0.9',
    'authorization': f'Bearer {token}',
    'content-type': 'application/json',
    'origin': 'chrome-extension://' + EXTENSION_ID,
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'cross-site',
    'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36'
}

# Setup colorlog for colored logging
handler = colorlog.StreamHandler()
formatter = colorlog.ColoredFormatter(
    "%(log_color)s[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    log_colors={
        "DEBUG": "cyan",
        "INFO": "green",
        "WARNING": "yellow",
        "ERROR": "red",
        "CRITICAL": "bold_red",
    }
)
handler.setFormatter(formatter)
logger = logging.getLogger("AeropresClient")
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Helper functions
def load_proxies(file_path):
    try:
        with open(file_path, 'r') as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        logger.error(f"Proxy file {file_path} not found.")
        return []

def generate_browser_id(proxy):
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, proxy if proxy else "local_network"))

def create_keep_alive_data(proxy):
    return {
        "username": user_id,
        "extensionid": EXTENSION_ID,
        "numberoftabs": 0,
        "_v": VERSION,
        "browser_id": generate_browser_id(proxy)
    }

# API functions
def get_balance(session):
    """Fetch the user's balance information from the API."""
    try:
        response = session.get(api_balance, headers=headers, verify=False)
        if response.status_code == 200:
            data = response.json()
            if data.get('status') is True:
                points = data['data']['rewardPoint']['points']
                user_id_fetched = data['data']['rewardPoint']['userId']
                return True, points, user_id_fetched
            logger.warning("Failed to retrieve balance: Status is False.")
        else:
            logger.error(f"Error fetching balance: Status code {response.status_code}")
    except Exception as e:
        logger.error(f"Error in get_balance: {e}")
    return False, None, None

def keep_alive(proxy):
    """Send keep-alive requests using the specified proxy."""
    with requests.Session() as session:
        if proxy:
            session.proxies.update({"http": proxy, "https": proxy})

        while True:
            data = create_keep_alive_data(proxy)
            try:
                response = session.post(api_keep_alive, headers=headers, json=data, verify=False)
                if response.status_code == 200:
                    res = response.json()
                    if res.get('success'):
                        # Attempt to retrieve balance
                        success, points, user_id_response = get_balance(session)
                        points = points if success else None  # Set points to None if balance retrieval fails
                        message = res.get('message', "Success")

                        # Log success with points or 'None' if failed
                        logger.info(f"{message} | Proxy: {proxy if proxy else 'Local'} | Points: {points if points is not None else 'None'} | User ID: {user_id_response if success else 'None'}")
                    else:
                        logger.warning(f"Keep-alive failed | Proxy: {proxy if proxy else 'Local'} | Message: {res.get('message', 'Error')} | Points: None")
                else:
                    logger.error(f"API error on keep-alive request: Status code {response.status_code}")
            except Exception as e:
                logger.error(f"Error in keep_alive with proxy {proxy}: {e}")

            # Wait before the next request
            time.sleep(BALANCE_CHECK_INTERVAL)

# Main function
def main():
    proxies = load_proxies(proxy_list_file) if use_proxy and proxy_list_file else [None]

    if not proxies:
        logger.error("No proxies available.")
        return

    with ThreadPoolExecutor(max_workers=len(proxies)) as executor:
        futures = {executor.submit(keep_alive, proxy): proxy for proxy in proxies}
        for future in as_completed(futures):
            proxy = futures[future]
            try:
                future.result()
            except Exception as e:
                logger.error(f"Unexpected error with proxy {proxy}: {e}")

if __name__ == "__main__":
    main()

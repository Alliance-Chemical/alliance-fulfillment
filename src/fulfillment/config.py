import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # ShipStation
    shipstation_api_key: str = os.environ.get("SHIPSTATION_API_KEY", "")
    shipstation_api_secret: str = os.environ.get("SHIPSTATION_API_SECRET", "")
    # Fulfillment
    db_path: str = os.environ.get("FULFILLMENT_DB_PATH", "fulfillment.db")
    queue_refresh_seconds: int = int(os.environ.get("FULFILLMENT_REFRESH_SECONDS", "120"))
    default_batch_size: int = int(os.environ.get("FULFILLMENT_BATCH_SIZE", "8"))
    default_picker_slots: int = int(os.environ.get("FULFILLMENT_PICKER_SLOTS", "5"))
    # Twilio
    twilio_account_sid: str = os.environ.get("TWILIO_ACCOUNT_SID", "")
    twilio_auth_token: str = os.environ.get("TWILIO_AUTH_TOKEN", "")
    twilio_from_number: str = os.environ.get("TWILIO_FROM_NUMBER", "")


config = Config()

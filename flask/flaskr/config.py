import os

class Config:
    # Set to True to generate random sensor data 
    MOCK_SENSORS = False
    
    # Set to True to use the computer's local webcam instead of an external stream
    MOCK_VIDEO = True
    
    # Database Configuration
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or "sqlite:///iot_demo.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Secret key for sessions
    SECRET_KEY = os.environ.get('SECRET_KEY') or "dev-key-for-iot-dashboard"

    # Shared secret for ESP authentication
    ESP_TOKEN = os.environ.get('ESP_TOKEN') or "REDACTED-TOKEN"

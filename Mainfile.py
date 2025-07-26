# app.py
# Main Flask application for the MOSIP Notification System

from flask import Flask, request, jsonify
from dotenv import load_dotenv
import os
from datetime import datetime

# Load environment variables from .env file
load_dotenv()

# Import configuration and core components
from config import Config
from notification_core import NotificationRequest, NotificationChannel, NotificationService
from senders.whatsapp_sender import WhatsAppSender
from senders.telegram_sender import TelegramSender
from senders.viber_sender import ViberSender

app = Flask(__name__)
app.config.from_object(Config)

# Initialize sender services
# In a real application, you might use a dependency injection container
# to manage these, but for a simple Flask app, direct instantiation is fine.
whatsapp_sender = WhatsAppSender(app.config)
telegram_sender = TelegramSender(app.config)
viber_sender = ViberSender(app.config)

# Map channel types to sender instances
notification_senders = {
    NotificationChannel.WHATSAPP: whatsapp_sender,
    NotificationChannel.TELEGRAM: telegram_sender,
    NotificationChannel.VIBER: viber_sender,
    # Add Email and SMS senders if you implement them in Python
    # NotificationChannel.EMAIL: EmailSender(app.config),
    # NotificationChannel.SMS: SMSSender(app.config),
}

# Initialize the NotificationService with all available senders
notification_service = NotificationService(notification_senders)

@app.route('/notification/sendExpiryAlert', methods=['POST'])
def send_expiry_alert():
    """
    API endpoint to send certificate/event expiry alerts.
    Expects a JSON payload with notification details.
    """
    data = request.get_json()

    if not data:
        return jsonify({"status": "error", "message": "Invalid JSON payload"}), 400

    try:
        # Parse expiryDate string to datetime object
        expiry_date_str = data.get('expiryDate')
        expiry_date = None
        if expiry_date_str:
            try:
                expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d').date()
            except ValueError:
                return jsonify({"status": "error", "message": "Invalid expiryDate format. Use YYYY-MM-DD."}), 400

        # Convert channel strings to NotificationChannel enum members
        channels_str = data.get('channels', [])
        channels = []
        for channel_name in channels_str:
            try:
                channels.append(NotificationChannel[channel_name.upper()])
            except KeyError:
                return jsonify({"status": "error", "message": f"Invalid channel: {channel_name}"}), 400

        # Create NotificationRequest object
        notification_request = NotificationRequest(
            recipient_email=data.get('recipientEmail'),
            recipient_phone_number=data.get('recipientPhoneNumber'),
            telegram_chat_id=data.get('telegramChatId'),
            viber_user_id=data.get('viberUserId'),
            message_subject=data.get('messageSubject'),
            message_body=data.get('messageBody'),
            expiry_type=data.get('expiryType'),
            expiry_date=expiry_date,
            action_steps=data.get('actionSteps'),
            channels=channels,
            locale=data.get('locale', 'en') # Default to English if not provided
        )

        # Send the notification
        success = notification_service.send_notification(notification_request)

        if success:
            return jsonify({"status": "success", "message": "Notification dispatch initiated."}), 200
        else:
            return jsonify({"status": "error", "message": "Failed to dispatch all notifications."}), 500

    except Exception as e:
        app.logger.error(f"Error processing notification request: {e}", exc_info=True)
        return jsonify({"status": "error", "message": f"Internal server error: {str(e)}"}), 500

if __name__ == '__main__':
    # Run the Flask app
    # In a production environment, use a WSGI server like Gunicorn or uWSGI
    app.run(debug=True, host='0.0.0.0', port=5000)

```python
# config.py
# Centralized configuration for the Flask application

import os

class Config:
    """
    Configuration class to load API keys and other settings from environment variables.
    """
    # WhatsApp API Configuration
    WHATSAPP_API_URL = os.getenv('WHATSAPP_API_URL', '[https://graph.facebook.com/v19.0](https://graph.facebook.com/v19.0)')
    WHATSAPP_ACCESS_TOKEN = os.getenv('WHATSAPP_ACCESS_TOKEN')
    WHATSAPP_FROM_PHONE_NUMBER_ID = os.getenv('WHATSAPP_FROM_PHONE_NUMBER_ID')
    WHATSAPP_TEMPLATE_NAME = os.getenv('WHATSAPP_TEMPLATE_NAME', 'expiry_alert_template') # Pre-approved template

    # Telegram API Configuration
    TELEGRAM_API_URL = os.getenv('TELEGRAM_API_URL', '[https://api.telegram.org/bot](https://api.telegram.org/bot)')
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

    # Viber API Configuration
    VIBER_API_URL = os.getenv('VIBER_API_URL', '[https://chatapi.viber.com/pa/](https://chatapi.viber.com/pa/)')
    VIBER_AUTH_TOKEN = os.getenv('VIBER_AUTH_TOKEN')
    VIBER_SENDER_NAME = os.getenv('VIBER_SENDER_NAME', 'MOSIP Alerts')
    VIBER_SENDER_AVATAR = os.getenv('VIBER_SENDER_AVATAR', '') # Optional

    # Ensure essential tokens are provided
    if not WHATSAPP_ACCESS_TOKEN:
        print("WARNING: WHATSAPP_ACCESS_TOKEN not set in .env")
    if not TELEGRAM_BOT_TOKEN:
        print("WARNING: TELEGRAM_BOT_TOKEN not set in .env")
    if not VIBER_AUTH_TOKEN:
        print("WARNING: VIBER_AUTH_TOKEN not set in .env")

```python
# notification_core.py
# Core interfaces (Abstract Base Classes) and Data Transfer Objects (DTOs)

from abc import ABC, abstractmethod
from enum import Enum
from dataclasses import dataclass
from datetime import date
from typing import List, Optional

class NotificationChannel(Enum):
    """
    Enum representing the different notification channels supported.
    """
    EMAIL = "EMAIL"
    SMS = "SMS"
    WHATSAPP = "WHATSAPP"
    TELEGRAM = "TELEGRAM"
    VIBER = "VIBER"

@dataclass
class NotificationRequest:
    """
    Data Transfer Object (DTO) for a notification request.
    Contains all details needed to send an alert across various channels.
    """
    recipient_email: Optional[str] = None
    recipient_phone_number: Optional[str] = None # Used for SMS and WhatsApp
    telegram_chat_id: Optional[str] = None
    viber_user_id: Optional[str] = None

    message_subject: Optional[str] = None # Primarily for Email
    message_body: Optional[str] = None    # Primarily for Email/SMS (or template name/key for others)

    expiry_type: str = "Certificate" # e.g., "CERTIFICATE", "EVENT"
    expiry_date: Optional[date] = None
    action_steps: str = "Please renew your credential." # Guidance for the user

    channels: List[NotificationChannel] # List of channels to send to
    locale: str = "en" # Locale for multilingual messages (e.g., "en", "fr")

class NotificationSender(ABC):
    """
    Abstract Base Class (Interface) for all notification senders.
    Defines the contract for sending notifications to a specific channel.
    """
    @abstractmethod
    def send(self, request: NotificationRequest) -> bool:
        """
        Sends a notification based on the provided request.
        :param request: The NotificationRequest object.
        :return: True if the notification was successfully sent, False otherwise.
        """
        pass

    @abstractmethod
    def get_channel_type(self) -> NotificationChannel:
        """
        Returns the type of notification channel this sender handles.
        :return: The NotificationChannel enum member.
        """
        pass

class NotificationService:
    """
    Orchestrates the sending of notifications to various channels.
    Delegates to specific NotificationSender implementations.
    """
    def __init__(self, senders: dict[NotificationChannel, NotificationSender]):
        self.senders = senders
        print(f"Initialized notification senders: {list(self.senders.keys())}")

    def send_notification(self, request: NotificationRequest) -> bool:
        """
        Dispatches the notification request to the specified channels.
        :param request: The NotificationRequest object.
        :return: True if at least one notification was successfully sent, False otherwise.
        """
        overall_success = False
        if not request.channels:
            print("No notification channels specified in the request.")
            return False

        for channel in request.channels:
            sender = self.senders.get(channel)
            if sender:
                print(f"Attempting to send notification via {channel.value}")
                try:
                    sent = sender.send(request)
                    if sent:
                        overall_success = True
                        print(f"Successfully sent notification via {channel.value}")
                    else:
                        print(f"Failed to send notification via {channel.value}")
                except Exception as e:
                    print(f"Error sending notification via {channel.value}: {e}")
            else:
                print(f"No sender found for channel: {channel.value}")
        return overall_success

```python
# senders/__init__.py
# This file makes 'senders' a Python package.
```python
# senders/whatsapp_sender.py
# Implementation for sending notifications via WhatsApp Business API

import requests
from notification_core import NotificationSender, NotificationChannel, NotificationRequest
from messages import get_localized_message # For multilingual support
from datetime import date

class WhatsAppSender(NotificationSender):
    """
    Sends notifications using the WhatsApp Business API.
    Requires a pre-approved message template for business-initiated messages.
    """
    def __init__(self, config):
        self.api_url = config.WHATSAPP_API_URL
        self.access_token = config.WHATSAPP_ACCESS_TOKEN
        self.from_phone_number_id = config.WHATSAPP_FROM_PHONE_NUMBER_ID
        self.template_name = config.WHATSAPP_TEMPLATE_NAME

    def send(self, request: NotificationRequest) -> bool:
        if not request.recipient_phone_number:
            print("WhatsApp recipient phone number is missing.")
            return False
        if not self.access_token or not self.from_phone_number_id:
            print("WhatsApp API access token or phone number ID is not configured.")
            return False

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        # Format expiry_date for the message
        expiry_date_formatted = request.expiry_date.strftime("%d-%m-%Y") if request.expiry_date else "N/A"

        # Prepare parameters for the WhatsApp template
        # This assumes a template like: "Your {{1}} will expire on {{2}}. Please take the following action: {{3}}."
        # You need to ensure your template variables match this order and type.
        template_components = [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": request.expiry_type},
                    {"type": "text", "text": expiry_date_formatted},
                    {"type": "text", "text": request.action_steps}
                ]
            }
        ]

        payload = {
            "messaging_product": "whatsapp",
            "to": request.recipient_phone_number,
            "type": "template",
            "template": {
                "name": self.template_name,
                "language": {"code": request.locale},
                "components": template_components
            }
        }

        try:
            # The actual API endpoint will be like: https://graph.facebook.com/v19.0/{phone-number-id}/messages
            api_endpoint = f"{self.api_url}/{self.from_phone_number_id}/messages"
            response = requests.post(api_endpoint, json=payload, headers=headers)
            response.raise_for_status()  # Raise an exception for HTTP errors (4xx or 5xx)
            print(f"WhatsApp notification sent to {request.recipient_phone_number}. Response: {response.json()}")
            return True
        except requests.exceptions.RequestException as e:
            print(f"Failed to send WhatsApp notification to {request.recipient_phone_number}: {e}")
            print(f"Response content: {response.text if 'response' in locals() else 'No response'}")
            return False

    def get_channel_type(self) -> NotificationChannel:
        return NotificationChannel.WHATSAPP

```python
# senders/telegram_sender.py
# Implementation for sending notifications via Telegram Bot API

import requests
from notification_core import NotificationSender, NotificationChannel, NotificationRequest
from messages import get_localized_message
from datetime import date

class TelegramSender(NotificationSender):
    """
    Sends notifications using the Telegram Bot API.
    """
    def __init__(self, config):
        self.api_url = config.TELEGRAM_API_URL
        self.bot_token = config.TELEGRAM_BOT_TOKEN

    def send(self, request: NotificationRequest) -> bool:
        if not request.telegram_chat_id:
            print("Telegram chat ID is missing.")
            return False
        if not self.bot_token:
            print("Telegram Bot Token is not configured.")
            return False

        # Format expiry_date for the message
        expiry_date_formatted = request.expiry_date.strftime("%d-%m-%Y") if request.expiry_date else "N/A"

        # Get localized message from messages.py
        message_text = get_localized_message(
            "telegram.expiry.message",
            request.locale,
            request.expiry_type,
            expiry_date_formatted,
            request.action_steps
        )

        payload = {
            "chat_id": request.telegram_chat_id,
            "text": message_text
        }

        try:
            api_endpoint = f"{self.api_url}{self.bot_token}/sendMessage"
            response = requests.post(api_endpoint, json=payload)
            response.raise_for_status()
            print(f"Telegram notification sent to chat ID {request.telegram_chat_id}. Response: {response.json()}")
            return True
        except requests.exceptions.RequestException as e:
            print(f"Failed to send Telegram notification to {request.telegram_chat_id}: {e}")
            print(f"Response content: {response.text if 'response' in locals() else 'No response'}")
            return False

    def get_channel_type(self) -> NotificationChannel:
        return NotificationChannel.TELEGRAM

```python
# senders/viber_sender.py
# Implementation for sending notifications via Viber REST API

import requests
from notification_core import NotificationSender, NotificationChannel, NotificationRequest
from messages import get_localized_message
from datetime import date

class ViberSender(NotificationSender):
    """
    Sends notifications using the Viber REST API.
    """
    def __init__(self, config):
        self.api_url = config.VIBER_API_URL
        self.auth_token = config.VIBER_AUTH_TOKEN
        self.sender_name = config.VIBER_SENDER_NAME
        self.sender_avatar = config.VIBER_SENDER_AVATAR

    def send(self, request: NotificationRequest) -> bool:
        if not request.viber_user_id:
            print("Viber user ID is missing.")
            return False
        if not self.auth_token:
            print("Viber Auth Token is not configured.")
            return False

        headers = {
            "X-Viber-Auth-Token": self.auth_token,
            "Content-Type": "application/json"
        }

        # Format expiry_date for the message
        expiry_date_formatted = request.expiry_date.strftime("%d-%m-%Y") if request.expiry_date else "N/A"

        # Get localized message from messages.py
        message_text = get_localized_message(
            "viber.expiry.message",
            request.locale,
            request.expiry_type,
            expiry_date_formatted,
            request.action_steps
        )

        payload = {
            "receiver": request.viber_user_id,
            "type": "text",
            "text": message_text,
            "sender": {
                "name": self.sender_name,
                "avatar": self.sender_avatar
            }
        }

        try:
            api_endpoint = f"{self.api_url}send_message"
            response = requests.post(api_endpoint, json=payload, headers=headers)
            response.raise_for_status()
            print(f"Viber notification sent to user ID {request.viber_user_id}. Response: {response.json()}")
            return True
        except requests.exceptions.RequestException as e:
            print(f"Failed to send Viber notification to {request.viber_user_id}: {e}")
            print(f"Response content: {response.text if 'response' in locals() else 'No response'}")
            return False

    def get_channel_type(self) -> NotificationChannel:
        return NotificationChannel.VIBER

```python
# messages/__init__.py
# This file makes 'messages' a Python package.

from . import en # Import default language messages
# from . import fr # Import other languages as needed

# Dictionary to hold message bundles by locale
_messages = {
    "en": en.MESSAGES,
    # "fr": fr.MESSAGES, # Uncomment if you add fr.py
}

def get_localized_message(key: str, locale: str, *args) -> str:
    """
    Retrieves a localized message string and formats it.
    :param key: The key of the message (e.g., "whatsapp.expiry.message").
    :param locale: The desired locale (e.g., "en", "fr").
    :param args: Arguments to format the message string.
    :return: The formatted localized message.
    """
    # Fallback to English if locale not found
    message_bundle = _messages.get(locale, _messages["en"])
    message_template = message_bundle.get(key, f"Missing message for key: {key}")

    try:
        return message_template.format(*args)
    except IndexError:
        print(f"Warning: Not enough arguments provided for message key '{key}' in locale '{locale}'. Template: '{message_template}'")
        return message_template # Return template without formatting if args don't match
    except Exception as e:
        print(f"Error formatting message for key '{key}' in locale '{locale}': {e}")
        return message_template # Fallback

```python
# messages/en.py
# English message templates

MESSAGES = {
    "whatsapp.expiry.message": "Dear User, your {} will expire on {}. Please take the following action: {}.",
    "telegram.expiry.message": "Alert: Your {} expires on {}. Action required: {}.",
    "viber.expiry.message": "Important: {} expires {}. Next steps: {}.",
    # Add other messages as needed
}
```python
# messages/fr.py (Example for French - Good-to-have)
# French message templates

MESSAGES = {
    "whatsapp.expiry.message": "Cher utilisateur, votre {} expirera le {}. Veuillez prendre les mesures suivantes : {}.",
    "telegram.expiry.message": "Alerte : Votre {} expire le {}. Action requise : {}.",
    "viber.expiry.message": "Important : {} expire le {}. Prochaines étapes : {}.",
    # Add other messages as needed
}
```text
# .env
# Environment variables for API keys and other sensitive configurations

# WhatsApp Business API
WHATSAPP_API_URL=https://graph.facebook.com/v19.0
WHATSAPP_ACCESS_TOKEN=YOUR_WHATSAPP_BUSINESS_API_TOKEN
WHATSAPP_FROM_PHONE_NUMBER_ID=YOUR_WHATSAPP_PHONE_NUMBER_ID
WHATSAPP_TEMPLATE_NAME=expiry_alert_template # Ensure this template is pre-approved in WhatsApp Business Manager

# Telegram Bot API
TELEGRAM_API_URL=https://api.telegram.org/bot
TELEGRAM_BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN

# Viber REST API
VIBER_API_URL=https://chatapi.viber.com/pa/
VIBER_AUTH_TOKEN=YOUR_VIBER_AUTH_TOKEN
VIBER_SENDER_NAME="MOSIP Alerts"
VIBER_SENDER_AVATAR="" # Optional: URL to your public account avatar (e.g., https://example.com/avatar.png)

import datetime
import os
import requests
import json
import logging
from typing import Dict

# Get environment variables
UNITS = os.getenv('UNITS', 'metric').lower()  # Default to metric if not set
TIME_FORMAT = os.getenv('TIME_FORMAT', '24')  # Default to 24-hour if not set
API_KEY = None  # Initialize as None, will be set by the main app
BASE_URL = "https://api.openweathermap.org/data/2.5"

def format_temperature(temp: float) -> str:
    """Format temperature based on unit setting"""
    if UNITS == 'imperial':
        return f"{temp:.1f}°F"
    return f"{temp:.1f}°C"

def format_wind_speed(speed: float) -> str:
    """Format wind speed based on unit setting"""
    if UNITS == 'imperial':
        return f"{speed:.1f} mph"
    return f"{speed:.1f} m/s"

def format_time(dt: datetime.datetime) -> str:
    """Format time based on time format setting"""
    if TIME_FORMAT == '12':
        return dt.strftime("%I:%M %p")
    return dt.strftime("%H:%M")

def is_hot_temperature(temp: float) -> bool:
    """Determine if a temperature is considered hot based on units"""
    if UNITS == 'imperial':
        return temp > 68  # 68°F = 20°C
    return temp > 20  # 20°C

def set_api_key(key: str) -> None:
    """Set the API key for use in requests"""
    global API_KEY
    API_KEY = key

def make_api_request(endpoint: str, params: Dict = None, base_url: str = BASE_URL) -> Dict:
    """
    Make an API request with consistent error handling and logging
    
    Args:
        endpoint: API endpoint path (e.g., "/weather" or "/forecast")
        params: Query parameters dictionary
        base_url: Base URL for the API (defaults to OpenWeather API)
    
    Returns:
        Dict containing the JSON response
    
    Raises:
        requests.RequestException: For network/API errors
    """
    if not API_KEY:
        raise requests.RequestException("API key not set. Please configure your API key.")

    try:
        # Ensure params dictionary exists
        params = params or {}
        
        # Add API key if not present
        if 'appid' not in params:
            params['appid'] = API_KEY
            
        # Make request with timeout
        url = f"{base_url}{endpoint}"
        logging.debug(f"Making API request to: {url}")
        logging.debug(f"With params: {params}")
        
        response = requests.get(url, params=params, timeout=10)
        
        # Check for unauthorized error
        if response.status_code == 401:
            error_msg = "API key unauthorized. Please make sure you have subscribed to the correct API plan."
            logging.error(error_msg)
            raise requests.RequestException(error_msg)
            
        # Raise any other HTTP errors
        response.raise_for_status()
        
        # Parse and return JSON
        data = response.json()
        logging.debug(f"Response received: {data}")
        return data
        
    except requests.Timeout:
        logging.error("Request timed out")
        raise requests.RequestException("Request timed out. Please try again.")
    except requests.RequestException as e:
        logging.error(f"Network error: {str(e)}")
        raise
    except json.JSONDecodeError as e:
        logging.error(f"Invalid API response: {str(e)}")
        raise requests.RequestException(f"Invalid API response: {str(e)}")
    except Exception as e:
        logging.error(f"Unexpected error during API request: {str(e)}", exc_info=True)
        raise requests.RequestException(f"Unexpected error: {str(e)}") 

def set_units(units_setting: str) -> None:
    """Set the units (metric/imperial) for formatting"""
    global UNITS
    UNITS = units_setting.lower()

def set_time_format(format_setting: str) -> None:
    """Set the time format (12/24) for formatting"""
    global TIME_FORMAT
    TIME_FORMAT = format_setting 

def download_binary(endpoint: str, params: Dict = None, base_url: str = BASE_URL) -> bytes:
    """
    Download binary data (like images) from an API endpoint
    
    Args:
        endpoint: API endpoint path
        params: Query parameters dictionary
        base_url: Base URL for the API
    
    Returns:
        bytes containing the binary response data
    
    Raises:
        requests.RequestException: For network/API errors
    """
    if not API_KEY:
        raise requests.RequestException("API key not set. Please configure your API key.")

    try:
        # Ensure params dictionary exists
        params = params or {}
        
        # Add API key if not present
        if 'appid' not in params:
            params['appid'] = API_KEY
            
        # Make request with timeout
        url = f"{base_url}{endpoint}"
        logging.debug(f"Downloading binary data from: {url}")
        
        response = requests.get(url, params=params, timeout=10)
        
        # Check for unauthorized error
        if response.status_code == 401:
            error_msg = "API key unauthorized. Please make sure you have subscribed to the correct API plan."
            logging.error(error_msg)
            raise requests.RequestException(error_msg)
            
        # Raise any other HTTP errors
        response.raise_for_status()
        
        return response.content
        
    except requests.Timeout:
        logging.error("Download timed out")
        raise requests.RequestException("Download timed out. Please try again.")
    except requests.RequestException as e:
        logging.error(f"Network error during download: {str(e)}")
        raise
    except Exception as e:
        logging.error(f"Unexpected error during download: {str(e)}", exc_info=True)
        raise requests.RequestException(f"Unexpected error: {str(e)}") 
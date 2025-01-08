import os
import logging
from typing import Tuple, Dict
from helpers import make_api_request

class GeoHandler:
    def __init__(self):
        self.default_zip = os.getenv('DEFAULT_ZIP', '98272')  # Default to Monroe, WA
        self.default_country = os.getenv('DEFAULT_COUNTRY', 'US')
        self.default_city = os.getenv('DEFAULT_CITY', '')
        self.default_state = os.getenv('DEFAULT_STATE', '')
        self.current_location = "Unknown Location"

    def get_location_coords(self) -> Tuple[float, float]:
        """Get coordinates for the current location"""
        try:
            if self.default_zip:
                return self._get_coords_from_zip()
            else:
                return self._get_coords_from_city()
        except Exception as e:
            logging.error(f"Error getting location coordinates: {str(e)}", exc_info=True)
            # Default to Monroe, WA coordinates if there's an error
            return 47.8557, -121.9715

    def _get_coords_from_zip(self) -> Tuple[float, float]:
        """Get coordinates from zip code"""
        location_data = make_api_request(
            "/geo/1.0/zip",
            params={"zip": f"{self.default_zip},{self.default_country}"},
            base_url="http://api.openweathermap.org"
        )
        
        # Update the location name
        self.current_location = f"{location_data['name']}, {location_data['country']}"
        logging.debug(f"Location set to: {self.current_location}")
        
        return location_data['lat'], location_data['lon']

    def _get_coords_from_city(self) -> Tuple[float, float]:
        """Get coordinates from city name"""
        search_query = self.default_city
        if self.default_state:
            search_query += f",{self.default_state}"
        if self.default_country:
            search_query += f",{self.default_country}"
            
        locations = make_api_request(
            "/geo/1.0/direct",
            params={
                "q": search_query,
                "limit": 1
            },
            base_url="http://api.openweathermap.org"
        )
        
        if not locations:
            raise Exception(f"Location not found: {search_query}")
            
        location_data = locations[0]
        self.current_location = f"{location_data['name']}, {location_data.get('state', '')}, {location_data['country']}"
        logging.debug(f"Location set to: {self.current_location}")
        
        return location_data['lat'], location_data['lon']

    def get_current_location(self) -> str:
        """Get the current location name"""
        return self.current_location 
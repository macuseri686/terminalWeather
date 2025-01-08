import urwid
import requests
import datetime
import os
from typing import Dict, List, Optional, Callable
from dotenv import load_dotenv
import json
import logging
import numpy as np
from PIL import Image
import io
import math

# Load environment variables from .env file
load_dotenv()

# Get API key from environment variables
API_KEY = os.getenv('OPENWEATHER_API_KEY')
DEFAULT_ZIP = os.getenv('DEFAULT_ZIP', '98272')  # Default to Monroe, WA if not set
DEFAULT_COUNTRY = os.getenv('DEFAULT_COUNTRY', 'US')  # Default to US if not set
UNITS = os.getenv('UNITS', 'metric').lower()  # Default to metric if not set
TIME_FORMAT = os.getenv('TIME_FORMAT', '24')  # Default to 24-hour if not set
BASE_URL = "https://api.openweathermap.org/data/2.5"  # Changed to 2.5 as 3.0 requires subscription

# Add this near the top of the file, after imports
logging.basicConfig(
    filename='weather_app.log',
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Add these helper functions after the imports
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

class ErrorDialog(urwid.WidgetWrap):
    def __init__(self, error_msg, app, retry_callback=None):
        self.app = app
        self.retry_callback = retry_callback
        
        # Create buttons
        retry_btn = urwid.Button("Retry", on_press=self._on_retry)
        close_btn = urwid.Button("Exit", on_press=self._on_close)
        retry_btn = urwid.AttrMap(retry_btn, 'button', focus_map='button_focus')
        close_btn = urwid.AttrMap(close_btn, 'button', focus_map='highlight_red')
        
        buttons = urwid.GridFlow([retry_btn, close_btn], 12, 3, 1, 'center')
        
        # Create error message
        pile = urwid.Pile([
            urwid.Text(''),
            urwid.Text(error_msg, align='center'),
            urwid.Text(''),
            buttons,
            urwid.Text('')
        ])
        
        fill = urwid.Filler(pile, 'middle')
        box = urwid.LineBox(
            urwid.Padding(fill, left=2, right=2),
            title="Error"
        )
        self._w = urwid.AttrMap(box, 'error_dialog')
    
    def _on_retry(self, button):
        if self.retry_callback:
            self.retry_callback()
        # Remove dialog and return to main view
        self.app.loop.widget = self.app.frame
    
    def _on_close(self, button):
        raise urwid.ExitMainLoop()

class SettingsDialog(urwid.WidgetWrap):
    def __init__(self, app, on_close: Optional[Callable] = None):
        self.app = app
        self.on_close = on_close
        
        # Create input fields
        self.api_key_edit = urwid.Edit("API Key: ", app.api_key)
        
        # Determine initial location type and value from env
        initial_is_city = not bool(os.getenv('DEFAULT_ZIP'))
        initial_location = ""
        initial_country = os.getenv('DEFAULT_COUNTRY', 'US')
        
        if initial_is_city:
            initial_location = os.getenv('DEFAULT_CITY', '')
            if os.getenv('DEFAULT_STATE'):
                initial_location += f", {os.getenv('DEFAULT_STATE')}"
        else:
            initial_location = os.getenv('DEFAULT_ZIP', '')
        
        self.location_edit = urwid.Edit(
            "City, State: " if initial_is_city else "ZIP Code: ", 
            initial_location
        )
        
        self.country_edit = urwid.Edit("Country Code: ", initial_country)
        
        # Create radio button group for location type
        self.location_group = []  # Initialize the group list
        self.location_type = urwid.RadioButton(
            self.location_group, 'City Name', 
            state=initial_is_city, 
            on_state_change=self._on_location_type_change
        )
        self.zip_type = urwid.RadioButton(
            self.location_group, 'ZIP Code',  
            state=not initial_is_city,
            on_state_change=self._on_location_type_change  # Add handler to this button too
        )
        
        # Create radio button group for units
        self.units_group = []  # Initialize the group list
        self.metric = urwid.RadioButton(
            self.units_group, 'Metric', 
            state=app.units == 'metric'
        )
        self.imperial = urwid.RadioButton(
            self.units_group, 'Imperial', 
            state=app.units == 'imperial'
        )
        
        # Create radio button group for time format
        self.time_group = []  # Initialize the group list
        self.time_24 = urwid.RadioButton(
            self.time_group, '24-hour', 
            state=app.time_format == '24'
        )
        self.time_12 = urwid.RadioButton(
            self.time_group, '12-hour', 
            state=app.time_format == '12'
        )
        
        # Create buttons
        save_btn = urwid.Button("Save", on_press=self._on_save)
        cancel_btn = urwid.Button("Cancel", on_press=self._on_cancel)
        search_btn = urwid.Button("Search Location", on_press=self._on_search)
        
        # Style buttons
        save_btn = urwid.AttrMap(save_btn, 'button', focus_map='button_focus')
        cancel_btn = urwid.AttrMap(cancel_btn, 'button', focus_map='button_focus')
        search_btn = urwid.AttrMap(search_btn, 'button', focus_map='button_focus')
        
        # Create API key section
        api_section = urwid.LineBox(
            urwid.Padding(self.api_key_edit, left=1, right=1),
            title="API Key"
        )
        
        # Create location section
        location_section = urwid.LineBox(
            urwid.Pile([
                urwid.Text("Location Type:"),
                self.location_type,
                self.zip_type,
                urwid.Divider(),
                self.location_edit,
                self.country_edit,
                urwid.Divider(),
                search_btn,
            ]),
            title="Location"
        )
        
        # Create units section
        units_section = urwid.LineBox(
            urwid.Pile([
                self.metric,
                self.imperial,
            ]),
            title="Units"
        )
        
        # Create time format section
        time_section = urwid.LineBox(
            urwid.Pile([
                self.time_24,
                self.time_12,
            ]),
            title="Time Format"
        )
        
        # Create the main content with sections
        content_pile = urwid.Pile([
            api_section,
            urwid.Divider(),
            location_section,
            urwid.Divider(),
            units_section,
            urwid.Divider(),
            time_section,
        ])
        
        # Create button row with padding
        button_row = urwid.Columns([
            ('weight', 1, urwid.Padding(save_btn, width=12, align='right')),
            ('fixed', 4, urwid.Text('')),  # Add 4 spaces padding between buttons
            ('weight', 1, urwid.Padding(cancel_btn, width=12, align='left')),
        ])
        
        # Create footer with padding above buttons
        footer = urwid.Pile([
            urwid.Divider(),  # Add space above buttons
            button_row,
            urwid.Divider(),  # Add space below buttons
        ])
        
        # Combine content and footer in a Frame
        frame = urwid.Frame(
            urwid.Filler(content_pile, valign='top'),
            footer=footer
        )
        
        # Create a LineBox with padding
        box = urwid.LineBox(
            urwid.Padding(frame, left=2, right=2),
            title="Settings"
        )
        
        # Use popup style from AntGuardian
        self._w = urwid.AttrMap(box, 'popup')

    def _on_location_type_change(self, radio, new_state):
        """Handle location type change"""
        # Only handle when a button is selected (not when deselected)
        if new_state:
            is_city = (radio == self.location_type)
            self.location_edit.set_caption("City, State: " if is_city else "ZIP Code: ")
            self.location_edit.set_edit_text("")

    def _on_search(self, button):
        location = self.location_edit.edit_text.strip()
        country = self.country_edit.edit_text.strip()
        
        logging.debug(f"Searching for location: {location}, country: {country}")
        logging.debug(f"Search type: {'city' if self.location_type.state else 'zip'}")
        
        if not location:
            self._show_error("Please enter a location")
            return
            
        try:
            if self.location_type.state:
                # Search by city name
                url = "http://api.openweathermap.org/geo/1.0/direct"
                search_query = location
                if country:
                    search_query += f",{country}"
                    
                params = {
                    "q": search_query,
                    "limit": 5,
                    "appid": self.api_key_edit.edit_text
                }
            else:
                # Search by ZIP code
                url = "http://api.openweathermap.org/geo/1.0/zip"
                params = {
                    "zip": f"{location},{country or 'US'}",
                    "appid": self.api_key_edit.edit_text
                }
            
            logging.debug(f"Making request to: {url}")
            logging.debug(f"With params: {params}")
            
            response = requests.get(url, params=params, timeout=10)  # Add timeout
            logging.debug(f"Response status code: {response.status_code}")
            logging.debug(f"Response content: {response.text}")
            
            response.raise_for_status()
            location_data = response.json()
            
            if self.location_type.state:
                # City search
                if not location_data:
                    self._show_error("No locations found")
                    return
                locations = location_data
            else:
                # ZIP search
                if 'cod' in location_data and str(location_data['cod']) != '200':
                    self._show_error(location_data.get('message', 'Location not found'))
                    return
                    
                # Format the location data to match the city search format
                locations = [{
                    'name': location_data['name'],
                    'country': location_data['country'],
                    'state': '',
                    'lat': location_data['lat'],
                    'lon': location_data['lon']
                }]
            
            logging.debug(f"Found locations: {locations}")
            self.show_location_dialog(locations)
            
        except requests.exceptions.Timeout:
            logging.error("Request timed out")
            self._show_error("Request timed out. Please try again.")
        except requests.exceptions.RequestException as e:
            logging.error(f"Network error: {str(e)}", exc_info=True)
            self._show_error(f"Network error: {str(e)}")
        except Exception as e:
            logging.error(f"Error searching location: {str(e)}", exc_info=True)
            self._show_error(f"Error searching location: {str(e)}")

    def _on_save(self, button):
        # Save settings to .env file
        settings = {
            'OPENWEATHER_API_KEY': self.api_key_edit.edit_text,
            'UNITS': 'metric' if self.metric.state else 'imperial',
            'TIME_FORMAT': '24' if self.time_24.state else '12',
            'DEFAULT_COUNTRY': self.country_edit.edit_text.strip()
        }
        
        # Add location settings based on type
        if self.zip_type.state:
            settings['DEFAULT_ZIP'] = self.location_edit.edit_text.strip()
            # Clear any city-related settings
            settings['DEFAULT_CITY'] = ''
            settings['DEFAULT_STATE'] = ''
        else:
            # Clear ZIP settings
            settings['DEFAULT_ZIP'] = ''
            # Parse city and state
            parts = [p.strip() for p in self.location_edit.edit_text.split(',')]
            settings['DEFAULT_CITY'] = parts[0] if parts else ''
            settings['DEFAULT_STATE'] = parts[1] if len(parts) > 1 else ''
        
        logging.debug(f"Saving settings: {settings}")
        
        try:
            # Write to .env file
            with open('.env', 'w') as f:
                for key, value in settings.items():
                    if value:  # Only write non-empty values
                        f.write(f'{key}={value}\n')
            
            # Update app settings
            self.app.api_key = settings['OPENWEATHER_API_KEY']
            self.app.units = settings['UNITS']
            self.app.time_format = settings['TIME_FORMAT']
            
            # Update environment variables
            os.environ['OPENWEATHER_API_KEY'] = settings['OPENWEATHER_API_KEY']
            os.environ['UNITS'] = settings['UNITS']
            os.environ['TIME_FORMAT'] = settings['TIME_FORMAT']
            os.environ['DEFAULT_COUNTRY'] = settings['DEFAULT_COUNTRY']
            
            if settings['DEFAULT_ZIP']:
                os.environ['DEFAULT_ZIP'] = settings['DEFAULT_ZIP']
                os.environ.pop('DEFAULT_CITY', None)
                os.environ.pop('DEFAULT_STATE', None)
            else:
                os.environ.pop('DEFAULT_ZIP', None)
                if settings['DEFAULT_CITY']:
                    os.environ['DEFAULT_CITY'] = settings['DEFAULT_CITY']
                if settings['DEFAULT_STATE']:
                    os.environ['DEFAULT_STATE'] = settings['DEFAULT_STATE']
            
            # Return to main view
            self.app.loop.widget = self.app.frame
            
            # Refresh weather data
            self.app.update_weather()
            
        except Exception as e:
            logging.error(f"Error saving settings: {str(e)}", exc_info=True)
            self._show_error(f"Error saving settings: {str(e)}")

    def _on_cancel(self, button):
        if self.on_close:
            self.on_close()

    def _show_error(self, message):
        self.app.show_error(message)

    def show_location_dialog(self, locations):
        """Show location selection dialog"""
        dialog = LocationDialog(locations, self.app, self)
        
        # Calculate dialog size
        screen = urwid.raw_display.Screen()
        screen_cols, screen_rows = screen.get_cols_rows()
        dialog_width = int(screen_cols * 0.6)
        dialog_height = int(screen_rows * 0.6)
        
        # Create overlay for location dialog on top of settings dialog
        overlay = urwid.Overlay(
            dialog,
            self.app.settings_overlay,  # Use the settings overlay as bottom widget
            'center', dialog_width,
            'middle', dialog_height
        )
        
        # Set the overlay as the active widget
        self.app.loop.widget = overlay

class LocationDialog(urwid.WidgetWrap):
    def __init__(self, locations, app, parent_dialog, on_close=None):
        self.app = app
        self.parent_dialog = parent_dialog
        self.on_close = on_close
        
        # Create location buttons
        location_buttons = []
        for loc in locations:
            name = f"{loc['name']}, {loc.get('state', '')}, {loc['country']}"
            btn = urwid.Button(name.strip().strip(','), on_press=self._on_select, user_data=loc)
            btn = urwid.AttrMap(btn, 'button', focus_map='button_focus')
            location_buttons.append(btn)
        
        # Add cancel button
        cancel_btn = urwid.Button("Cancel", on_press=self._on_cancel)
        cancel_btn = urwid.AttrMap(cancel_btn, 'button', focus_map='button_focus')
        location_buttons.append(urwid.Divider())
        location_buttons.append(cancel_btn)
        
        # Create the layout
        pile = urwid.Pile([
            urwid.Text("Select Location", align='center'),
            urwid.Divider(),
            *location_buttons
        ])
        
        # Create a LineBox with padding
        box = urwid.LineBox(
            urwid.Padding(pile, left=2, right=2),
            title="Location Results"
        )
        
        self._w = urwid.AttrMap(box, 'dialog')

    def _on_select(self, button, location):
        logging.debug(f"Selected location: {location}")
        
        # Update parent dialog with selected location
        if self.parent_dialog.zip_type.state:
            # For ZIP code search, keep the original ZIP code
            # The ZIP is still in the parent dialog's location_edit
            pass  # Don't modify the ZIP code field
        else:
            # For city search, format the full location string
            name_parts = [location['name']]
            if location.get('state'):
                name_parts.append(location['state'])
            self.parent_dialog.location_edit.set_edit_text(', '.join(name_parts))
            
        # Update country
        self.parent_dialog.country_edit.set_edit_text(location['country'])
        
        # Return to settings dialog
        self.app.loop.widget = self.app.settings_overlay

    def _on_cancel(self, button):
        # Return to settings dialog
        self.app.loop.widget = self.app.settings_overlay

class WeatherIcons:
    """Weather icon mappings using Unicode symbols"""
    ICONS = {
        # Clear
        "01d": "☀️",  # clear sky (day)
        "01n": "🌙",  # clear sky (night)
        
        # Few clouds
        "02d": "⛅",  # few clouds (day)
        "02n": "☁️",  # few clouds (night)
        
        # Scattered/Broken clouds
        "03d": "☁️",  # scattered clouds
        "03n": "☁️",
        "04d": "☁️",  # broken clouds
        "04n": "☁️",
        
        # Rain
        "09d": "🌧️",  # shower rain
        "09n": "🌧️",
        "10d": "🌦️",  # rain (day)
        "10n": "🌧️",  # rain (night)
        
        # Thunderstorm
        "11d": "⛈️",  # thunderstorm
        "11n": "⛈️",
        
        # Snow
        "13d": "🌨️",  # snow
        "13n": "🌨️",
        
        # Mist/Fog
        "50d": "🌫️",  # mist
        "50n": "🌫️",
    }
    
    # Fallback ASCII versions if Unicode doesn't render well
    ASCII_ICONS = {
        # Clear
        "01d": "(*)",  # clear sky (day)
        "01n": "[ ]",  # clear sky (night)
        
        # Few clouds
        "02d": "(_)",  # few clouds (day)
        "02n": "[-]",  # few clouds (night)
        
        # Scattered/Broken clouds
        "03d": "(__)",  # scattered clouds
        "03n": "(__)",
        "04d": "(@@)",  # broken clouds
        "04n": "(@@)",
        
        # Rain
        "09d": "|||",  # shower rain
        "09n": "|||",
        "10d": ".|.",  # rain
        "10n": ".|.",
        
        # Thunderstorm
        "11d": "/V\\",  # thunderstorm
        "11n": "/V\\",
        
        # Snow
        "13d": "***",  # snow
        "13n": "***",
        
        # Mist/Fog
        "50d": "===",  # mist
        "50n": "===",
    }
    
    @classmethod
    def get(cls, icon_code: str, use_ascii: bool = False) -> str:
        """Get weather icon for the given weather code"""
        if use_ascii:
            return cls.ASCII_ICONS.get(icon_code, "???")
        return cls.ICONS.get(icon_code, "?")

class LargeWeatherIcons:
    """Large ASCII art weather icons for current conditions"""
    ICONS = {
        # Clear sky (day)
        "01d": [
            ('sun_ray', """\
    \\   |   /
     \\  |  /"""),
            ('sun', """
   ----█☀█----"""),
            ('sun_ray', """
     /  |  \\
    /   |   \\""")
        ],
        # Clear sky (night)
        "01n": [
            ('star', "    *  *   *"),
            ('star', "\n  *    "),
            ('moon', "█🌙█"),
            ('star', """   *
     *    *
  *     *   *
    *  *   *""")
        ],
        # Few clouds
        "02d": [
            ('sun_ray', "   \\  "),
            ('cloud_outline', "___"),
            ('sun_ray', "   /"),
            ('cloud', """
    _(███)_
   (█████)"""),
            ('sun', "\n    \\☀/")
        ],
        # Few clouds (night)
        "02n": [
            ('cloud_outline', "   ___  "),
            ('star', "*"),
            ('cloud', """
  (███)_  """),
            ('star', "*"),
            ('cloud', """
 (█████)
   * """),
            ('moon', "🌙"),
            ('star', " *")
        ],
        # Scattered clouds
        "03d": [
            ('cloud_outline', "   ___  "),
            ('cloud', """
  (███)
 (█████)
     """)
        ],
        # Broken/overcast clouds
        "04d": [
            ('cloud_outline', "  ___   ___"),
            ('cloud', """
  (███)_(███)
(█████████)
       """)
        ],
        # Shower rain
        "09d": [
            ('cloud_outline', "   ____"),
            ('cloud', """
  (████)
 (██████)"""),
            ('rain', """
  │╲│╲│╲
  ││││││""")
        ],
        # Rain
        "10d": [
            ('sun_ray', " \\  "),
            ('cloud_outline', "____  "),
            ('sun_ray', "/"),
            ('cloud', """
  _(████)_
 (██████)"""),
            ('rain', """
  │╲│╲│╲""")
        ],
        # Thunderstorm
        "11d": [
            ('cloud_outline', "   ____"),
            ('cloud', """
  (████)
 (██████)"""),
            ('lightning', """
  │⚡│⚡│"""),
            ('rain', """
  ││││││""")
        ],
        # Snow
        "13d": [
            ('cloud_outline', "   ____"),
            ('cloud', """
  (████)
 (██████)"""),
            ('snow', """
  *  *  *
   *  *""")
        ],
        # Mist/fog
        "50d": [
            ('mist_light', "  ████████"),
            ('mist_dark', """
 ██████████"""),
            ('mist_light', """
  ████████"""),
            ('mist_dark', """
 ██████████""")
        ],
    }
    
    # Add aliases for night versions
    ALIASES = {
        "03n": "03d",
        "04n": "04d",
        "09n": "09d",
        "10n": "09d",  # Use shower rain at night
        "11n": "11d",
        "13n": "13d",
        "50n": "50d",
    }

    @classmethod
    def get(cls, icon_code: str) -> List[tuple]:
        """Get large weather icon for the given weather code"""
        logging.debug(f"Getting large icon for code: {icon_code}")
        
        # Check aliases first
        if icon_code in cls.ALIASES:
            icon_code = cls.ALIASES[icon_code]
        
        # Get the icon segments
        icon = cls.ICONS.get(icon_code)
        
        if icon is None:
            logging.warning(f"No icon found for code: {icon_code}")
            return [('error', """\
   ?????
   ?   ?
   ?   ?
   ?????""")]
        
        return icon

class RadarDisplay(urwid.Widget):
    _sizing = frozenset(['box'])
    
    def __init__(self, width, height):
        super().__init__()
        self.width = width
        self.height = height
        self.radar_data = None
        self.map_data = None
        self.block_char = '#'
        self.location_name = None  # Add location name storage
    
    def render(self, size, focus=False):
        maxcol, maxrow = size
        result = []
        
        if self.radar_data is None or self.map_data is None:
            empty_line = " " * maxcol
            for i in range(maxrow):
                result.append(([(None, maxcol)], empty_line.encode('ascii')))
        else:
            # Calculate center position for marker
            center_row = maxrow // 2
            center_col = maxcol // 2
            
            # Resize radar data to fit display area
            image_radar = Image.fromarray((self.radar_data * 255).astype('uint8'))
            image_radar = image_radar.resize((maxcol, maxrow))
            radar_data = np.array(image_radar) / 255.0
            
            # Create radar display lines
            for i in range(maxrow):
                line = []
                attrs = []
                
                for j in range(maxcol):
                    val = radar_data[i][j]
                    
                    # Draw location marker and name
                    if i == center_row and j == center_col:
                        char = '+'  # Center marker
                        style = 'map_marker'
                    elif (i == center_row + 1 and 
                          self.location_name and 
                          j >= center_col - len(self.location_name)//2 and 
                          j < center_col + (len(self.location_name)+1)//2):
                        # Draw location name centered under marker
                        name_pos = j - (center_col - len(self.location_name)//2)
                        char = self.location_name[name_pos]
                        style = 'map_label'
                    else:
                        # Show precipitation
                        char = self.block_char
                        if val <= 0.0:
                            style = 'radar_none'
                        elif val <= 0.2:
                            style = 'radar_very_light'
                        elif val <= 0.4:
                            style = 'radar_light'
                        elif val <= 0.6:
                            style = 'radar_moderate'
                        elif val <= 0.8:
                            style = 'radar_heavy'
                        else:
                            style = 'radar_extreme'
                    
                    line.append(char)
                    attrs.append((style, 1))
                
                line_str = ''.join(line)
                result.append((attrs, line_str.encode('ascii')))
        
        return urwid.TextCanvas(
            [line for _, line in result],
            attr=[attrs for attrs, _ in result],
            maxcol=maxcol
        )

    def update_radar(self, radar_image_data, map_image_data, location_name=None):
        """Update radar display with new image data"""
        try:
            # Process radar data
            radar_image = Image.open(io.BytesIO(radar_image_data))
            if radar_image.mode != 'L':
                radar_image = radar_image.convert('L')
            radar_data = np.array(radar_image)
            self.radar_data = np.clip(radar_data / 100.0, 0, 1)
            
            # Store location name
            self.location_name = location_name
            
            # Process map data (blank map)
            map_image = Image.open(io.BytesIO(map_image_data))
            if map_image.mode != 'L':
                map_image = map_image.convert('L')
            self.map_data = np.array(map_image) / 255.0
            
            self._invalidate()
        except Exception as e:
            logging.error(f"Error updating radar: {str(e)}", exc_info=True)

class RadarContainer(urwid.WidgetWrap):
    def __init__(self, widget):
        super().__init__(widget)
    
    def render(self, size, focus=False):
        maxcol, maxrow = size
        # Make inner size half the width and account for borders
        inner_size = (maxcol // 2, maxrow)
        canv = self._w.render(inner_size, focus)
        
        # Create a new canvas with the exact size we were given
        new_canv = urwid.CompositeCanvas(canv)
        # Calculate padding to center the half-width canvas
        padding = (maxcol - inner_size[0]) // 2
        new_canv.pad_trim_left_right(padding, padding)
        
        return new_canv

    def sizing(self):
        return frozenset(['box'])

class WeatherApp:
    def __init__(self):
        self.weather_data: Dict = {}
        self.location = "London,UK"  # Default location
        
        # Add these properties
        self.api_key = API_KEY
        self.units = UNITS
        self.time_format = TIME_FORMAT
        
        # Get terminal dimensions
        screen = urwid.raw_display.Screen()
        _, screen_rows = screen.get_cols_rows()
        
        # Calculate available height (excluding header)
        available_height = screen_rows - 1  # -1 for header
        
        # Calculate section heights proportionally
        current_height = min(10, int(available_height * 0.3))
        forecast_height = min(9, int(available_height * 0.25))
        radar_height = min(22, available_height - current_height - (forecast_height * 2))
        
        # Create settings button and header
        settings_btn = urwid.Button("⚙", on_press=self.show_settings)
        settings_btn = urwid.AttrMap(settings_btn, 'header_button', focus_map='header_button_focus')
        
        header_text = urwid.Text("Terminal Weather", align='center')
        header_cols = urwid.Columns([
            header_text,
            ('fixed', 4, settings_btn)
        ])
        self.header = urwid.AttrMap(header_cols, 'header')
        
        # Create the UI elements (remove _create_header call)
        self.current_conditions = self._create_current_conditions()
        self.hourly_forecast = self._create_hourly_forecast()
        self.daily_forecast = self._create_daily_forecast()
        self.radar_display = self._create_radar_display(radar_height)
        
        # Main layout with dynamic heights
        self.main_pile = urwid.Pile([
            ('pack', self.header),
            ('fixed', current_height, urwid.AttrMap(self.current_conditions, 'body')),
            ('fixed', forecast_height, urwid.AttrMap(self.hourly_forecast, 'body')),
            ('fixed', forecast_height, urwid.AttrMap(self.daily_forecast, 'body')),
            ('fixed', radar_height, urwid.AttrMap(self.radar_display, 'body')),
        ])
        
        # Main frame - wrap the pile in AttrMap
        self.frame = urwid.Frame(
            urwid.AttrMap(urwid.Filler(self.main_pile, valign='top'), 'body'),
        )

        # Create an overlay with gray background
        self.overlay = urwid.Overlay(
            urwid.AttrMap(self.frame, 'body'),  # Wrap frame in AttrMap
            urwid.SolidFill(' '),
            'center', ('relative', 100),
            'middle', ('relative', 100)
        )

        # Color palette
        self.palette = [
            ('header', 'white,bold', 'dark blue'),
            ('header_button', 'white,bold', 'dark blue'),
            ('header_button_focus', 'black', 'white'),
            ('body', 'black', 'light gray'),
            ('footer', 'black', 'light gray'),
            ('linebox', 'black', 'light gray'),  # Add style for line boxes
            ('temp_hot', 'light red,bold', 'light gray'),
            ('temp_cold', 'light blue,bold', 'light gray'),
            ('highlight', 'black', 'white'),
            ('error', 'light red,bold', 'dark blue'),
            ('error_dialog', 'white', 'dark red'),
            ('highlight_red', 'white', 'dark red'),
            ('radar_none', 'black', 'black'),
            ('radar_very_light', 'light green', 'light green'),
            ('radar_light', 'dark green', 'dark green'),
            ('radar_moderate', 'yellow', 'yellow'),
            ('radar_heavy', 'light red', 'light red'),
            ('radar_extreme', 'dark red', 'dark red'),
            ('radar_default', 'black', 'black'),
            ('map_background', 'dark gray', 'dark gray'),
            ('map_road', 'white', 'dark gray'),
            ('map_label', 'yellow', 'dark gray'),
            ('map_marker', 'white,bold', 'black'),
            ('button', 'black', 'light gray'),  # Added button style
            ('button_focus', 'white,bold', 'dark blue'),  # Added button focus style
            ('sun', 'yellow,bold', 'light gray'),
            ('sun_ray', 'brown', 'light gray'),
            ('moon', 'white,bold', 'light gray'),
            ('star', 'yellow', 'light gray'),
            ('cloud', 'white', 'light gray'),
            ('cloud_outline', 'white', 'light gray'),
            ('rain', 'light blue,bold', 'light gray'),
            ('lightning', 'yellow,bold', 'light gray'),
            ('snow', 'white,bold', 'light gray'),
            ('mist_light', 'white', 'light gray'),
            ('mist_dark', 'dark gray', 'light gray'),
            ('night', 'dark blue', 'light gray'),
            ('error', 'light red,bold', 'light gray'),
            ('description', 'black,bold', 'light gray'),
            ('popup', 'black', 'white'),  # Add this to match AntGuardian's dialog style
            ('dialog', 'black', 'white'),  # Add this as well
        ]

    def _create_current_conditions(self) -> urwid.Widget:
        """Create the current conditions widget with placeholder content"""
        # Create widgets with placeholder text
        self.current_large_icon = urwid.Text(" ", align='center')  # Add align='center'
        self.current_temp = urwid.Text("Temperature: --°C")
        self.current_desc = urwid.Text("--")
        self.current_feels = urwid.Text("Feels like: --°C")
        self.current_humidity = urwid.Text("Humidity: --%")
        self.current_wind = urwid.Text("Wind: -- m/s")
        self.current_pressure = urwid.Text("Pressure: -- hPa")
        
        # Create center column for large icon with padding
        center_column = urwid.Pile([
            urwid.Padding(self.current_large_icon, width='clip', align='center'),
        ])
        
        # Create left and right columns
        left_column = urwid.Pile([
            urwid.Padding(self.current_temp, left=2),
            urwid.Padding(self.current_desc, left=2),
            urwid.Padding(self.current_feels, left=2),
        ])
        
        right_column = urwid.Pile([
            urwid.Padding(self.current_humidity, left=2),
            urwid.Padding(self.current_wind, left=2),
            urwid.Padding(self.current_pressure, left=2),
        ])
        
        # Combine columns with the large icon in the center
        columns = urwid.Columns([
            ('weight', 2, left_column),
            ('weight', 3, center_column),
            ('weight', 2, right_column),
        ], dividechars=2)  # Add some space between columns
        
        # Create a Pile to ensure proper vertical spacing
        content = urwid.Pile([
            urwid.Divider(),  # Add some top padding
            columns,
            urwid.Divider(),  # Add some bottom padding
        ])
        
        return urwid.AttrMap(urwid.LineBox(
            urwid.Filler(content, valign='middle'),  # Center content vertically
            title="Current Conditions"
        ), 'linebox')

    def _create_hourly_forecast(self) -> urwid.Widget:
        """Create the hourly forecast widget"""
        self.hourly_forecasts = []
        
        # Create a list to hold forecast columns
        self.hourly_pile = urwid.Columns([], dividechars=1)
        
        # Wrap in a horizontal scroll container
        hourly_box = urwid.BoxAdapter(
            urwid.Filler(
                urwid.Padding(self.hourly_pile, left=1, right=1)
            ),
            height=7  # Reduced from 6 to 4
        )
        
        return urwid.AttrMap(urwid.LineBox(
            hourly_box, 
            title="Hourly Forecast"
        ), 'linebox')

    def _update_hourly_forecast(self) -> None:
        """Update the hourly forecast display"""
        try:
            # Get terminal width
            screen = urwid.raw_display.Screen()
            screen_cols, _ = screen.get_cols_rows()
            
            MIN_BOX_WIDTH = 15
            available_width = screen_cols - 4
            num_boxes = available_width // MIN_BOX_WIDTH
            num_boxes = max(3, min(num_boxes, 8))
            
            box_width = available_width // num_boxes
            
            forecast_data = self.weather_data['forecast']['list']
            columns = []
            
            # Create a forecast box for each time slot
            for forecast in forecast_data[:num_boxes]:
                # Get time with new formatting
                time = datetime.datetime.fromtimestamp(forecast['dt'])
                time_str = format_time(time)
                
                # Get weather icon
                icon_code = forecast['weather'][0]['icon']
                icon = WeatherIcons.get(icon_code)
                
                # Get temperature with new formatting
                temp = forecast['main']['temp']
                temp_style = 'temp_hot' if is_hot_temperature(temp) else 'temp_cold'
                
                # Format description in two lines with word wrapping
                description = forecast['weather'][0]['description'].capitalize()
                desc_width = box_width - 4  # -4 for padding
                
                # Split into words
                words = description.split()
                first_line = []
                second_line = []
                current_line = first_line
                current_length = 0
                
                for word in words:
                    # Check if adding this word would exceed the width
                    if current_length + len(word) + (1 if current_length > 0 else 0) <= desc_width:
                        if current_length > 0:
                            current_line.append(' ')
                            current_length += 1
                        current_line.append(word)
                        current_length += len(word)
                    else:
                        # Move to second line if we're still on first line
                        if current_line is first_line:
                            current_line = second_line
                            current_length = len(word)
                            current_line.append(word)
                        else:
                            # If we're already on second line, truncate with ellipsis
                            while current_length + 1 > desc_width - 1:
                                current_line[-1] = current_line[-1][:-1]
                                current_length -= 1
                            current_line[-1] = current_line[-1] + '…'
                            break
                
                first_line_text = ''.join(first_line)
                second_line_text = ''.join(second_line)
                
                # Create forecast box
                forecast_pile = urwid.Pile([
                    urwid.Text(time_str, align='center'),
                    urwid.Text(icon, align='center'),
                    urwid.Text([
                        (temp_style, format_temperature(temp))
                    ], align='center'),
                    urwid.Text(first_line_text, align='center'),
                    urwid.Text(second_line_text, align='center'),
                ])
                
                columns.append(forecast_pile)
            
            # Properly format the contents for urwid.Columns
            self.hourly_pile.contents = [
                (col, self.hourly_pile.options('weight', 1)) 
                for col in columns
            ]
            
        except Exception as e:
            logging.error(f"Error updating hourly forecast: {str(e)}", exc_info=True)

    def _create_daily_forecast(self) -> urwid.Widget:
        """Create the daily forecast widget"""
        self.daily_pile = urwid.Columns([], dividechars=1)
        
        # Wrap in a container
        daily_box = urwid.BoxAdapter(
            urwid.Filler(
                urwid.Padding(self.daily_pile, left=1, right=1)
            ),
            height=7  # Changed from 8 to match hourly forecast height
        )
        
        return urwid.AttrMap(urwid.LineBox(
            daily_box,
            title="Daily Forecast"
        ), 'linebox')

    def _update_daily_forecast(self) -> None:
        """Update the daily forecast display"""
        try:
            # Get terminal width
            screen = urwid.raw_display.Screen()
            screen_cols, _ = screen.get_cols_rows()
            
            MIN_BOX_WIDTH = 15  # Changed from 18 to match hourly forecast
            available_width = screen_cols - 4  # -4 for frame borders
            num_boxes = available_width // MIN_BOX_WIDTH
            num_boxes = max(3, min(num_boxes, 7))  # Between 3 and 7 boxes
            
            box_width = available_width // num_boxes
            
            # Get daily forecasts from the 3-hour forecasts
            daily_forecasts = []
            current_day = None
            day_data = None
            
            for forecast in self.weather_data['forecast']['list']:
                time = datetime.datetime.fromtimestamp(forecast['dt'])
                if current_day != time.date():
                    if day_data:
                        daily_forecasts.append(day_data)
                    current_day = time.date()
                    day_data = {
                        'date': time,
                        'temp_min': forecast['main']['temp'],
                        'temp_max': forecast['main']['temp'],
                        'icon': forecast['weather'][0]['icon'],
                        'description': forecast['weather'][0]['description']
                    }
                else:
                    day_data['temp_min'] = min(day_data['temp_min'], forecast['main']['temp'])
                    day_data['temp_max'] = max(day_data['temp_max'], forecast['main']['temp'])
            
            if day_data:
                daily_forecasts.append(day_data)
            
            columns = []
            
            # Create a forecast box for each day
            for day_forecast in daily_forecasts[:num_boxes]:
                # Get day name
                day_name = day_forecast['date'].strftime('%a')
                
                # Get weather icon
                icon = WeatherIcons.get(day_forecast['icon'])
                
                # Get temperatures
                temp_max = day_forecast['temp_max']
                temp_min = day_forecast['temp_min']
                temp_style_max = 'temp_hot' if is_hot_temperature(temp_max) else 'temp_cold'
                temp_style_min = 'temp_hot' if is_hot_temperature(temp_min) else 'temp_cold'
                
                # Format description with word wrapping
                description = day_forecast['description'].capitalize()
                desc_width = box_width - 4  # -4 for padding
                
                # Split into words
                words = description.split()
                first_line = []
                second_line = []
                current_line = first_line
                current_length = 0
                
                for word in words:
                    if current_length + len(word) + (1 if current_length > 0 else 0) <= desc_width:
                        if current_length > 0:
                            current_line.append(' ')
                            current_length += 1
                        current_line.append(word)
                        current_length += len(word)
                    else:
                        if current_line is first_line:
                            current_line = second_line
                            current_length = len(word)
                            current_line.append(word)
                        else:
                            while current_length + 1 > desc_width - 1:
                                current_line[-1] = current_line[-1][:-1]
                                current_length -= 1
                            current_line[-1] = current_line[-1] + '…'
                            break
                
                first_line_text = ''.join(first_line)
                second_line_text = ''.join(second_line)
                
                # Create forecast box with added spaces after arrows
                forecast_pile = urwid.Pile([
                    urwid.Text(day_name, align='center'),
                    urwid.Text(icon, align='center'),
                    urwid.Text([
                        (temp_style_max, f"↑ {temp_max:.0f}°"),  # Added space after arrow
                        "  ",
                        (temp_style_min, f"↓ {temp_min:.0f}°")   # Added space after arrow
                    ], align='center'),
                    urwid.Text(first_line_text, align='center'),
                    urwid.Text(second_line_text, align='center'),
                ])
                
                columns.append(forecast_pile)
            
            # Update the display
            self.daily_pile.contents = [
                (col, self.daily_pile.options('weight', 1)) 
                for col in columns
            ]
            
        except Exception as e:
            logging.error(f"Error updating daily forecast: {str(e)}", exc_info=True)
            self._show_error(f"Error updating daily forecast: {str(e)}")

    def _create_radar_display(self, height: int) -> urwid.Widget:
        """Create the radar display widget"""
        # Create radar display with width set to fill available space
        self.radar = RadarDisplay(10, height - 2)  # Height -2 for borders
        
        # Create a fixed-size box for the radar
        radar_box = urwid.BoxAdapter(
            self.radar,  # Use radar directly without columns
            height - 2  # Match the height we want, accounting for borders
        )
        return urwid.AttrMap(urwid.LineBox(
            radar_box,
            title="Weather Radar"
        ), 'linebox')

    def _get_location_coords(self) -> tuple:
        """Get coordinates for the current location"""
        try:
            # Get current location settings from environment
            zip_code = os.environ.get('DEFAULT_ZIP')
            country = os.environ.get('DEFAULT_COUNTRY', 'US')
            
            if zip_code:
                # Get location from zip code
                geo_url = f"http://api.openweathermap.org/geo/1.0/zip"
                response = requests.get(
                    geo_url,
                    params={
                        "appid": self.api_key,
                        "zip": f"{zip_code},{country}"
                    },
                    timeout=10
                )
                response.raise_for_status()
                location_data = response.json()
                
                # Update the location name
                self.location = f"{location_data['name']}, {location_data['country']}"
                logging.debug(f"Location set to: {self.location}")
                
                return location_data['lat'], location_data['lon']
            else:
                # Get location from city name
                city = os.environ.get('DEFAULT_CITY', '')
                state = os.environ.get('DEFAULT_STATE', '')
                
                search_query = city
                if state:
                    search_query += f",{state}"
                if country:
                    search_query += f",{country}"
                    
                geo_url = "http://api.openweathermap.org/geo/1.0/direct"
                response = requests.get(
                    geo_url,
                    params={
                        "appid": self.api_key,
                        "q": search_query,
                        "limit": 1
                    },
                    timeout=10
                )
                response.raise_for_status()
                locations = response.json()
                
                if not locations:
                    raise Exception(f"Location not found: {search_query}")
                    
                location_data = locations[0]
                self.location = f"{location_data['name']}, {location_data.get('state', '')}, {location_data['country']}"
                logging.debug(f"Location set to: {self.location}")
                
                return location_data['lat'], location_data['lon']
                
        except Exception as e:
            logging.error(f"Error getting location coordinates: {str(e)}", exc_info=True)
            # Default to Monroe, WA coordinates if there's an error
            return 47.8557, -121.9715

    def update_weather(self) -> None:
        """Fetch and update weather data"""
        try:
            logging.debug("Starting weather update")
            
            # Get coordinates for the location
            lat, lon = self._get_location_coords()
            logging.debug(f"Using coordinates: {lat}, {lon}")
            
            # Get current weather with units parameter
            current_response = requests.get(
                f"{BASE_URL}/weather",
                params={
                    "appid": API_KEY,
                    "lat": lat,
                    "lon": lon,
                    "units": UNITS
                },
                timeout=10
            )
            
            if current_response.status_code == 401:
                error_msg = ("API key unauthorized. Please make sure you have subscribed to the correct API plan.")
                logging.error(error_msg)
                self._show_error(error_msg)
                return
            
            current_response.raise_for_status()
            
            # Get 5 day forecast with units parameter
            forecast_response = requests.get(
                f"{BASE_URL}/forecast",
                params={
                    "appid": API_KEY,
                    "lat": lat,
                    "lon": lon,
                    "units": UNITS
                },
                timeout=10
            )
            forecast_response.raise_for_status()
            
            self.weather_data = {
                'current': current_response.json(),
                'forecast': forecast_response.json()
            }
            
            # Schedule next update in 10 minutes
            self.loop.set_alarm_in(600, lambda loop, _: self.update_weather())
            
            self._update_display()
            
            # Update radar with new coordinates
            self._update_radar(lat, lon)
            
        except requests.RequestException as e:
            logging.error(f"Network error: {str(e)}")
            self._show_error(f"Network error: {str(e)}")
        except json.JSONDecodeError as e:
            logging.error(f"Invalid API response: {str(e)}")
            self._show_error(f"Invalid API response: {str(e)}")
        except Exception as e:
            logging.error(f"Error fetching weather data: {str(e)}", exc_info=True)
            self._show_error(f"Error fetching weather data: {str(e)}")

    def _update_radar(self, lat: float, lon: float) -> None:
        """Update the radar display"""
        try:
            zoom = 8
            lat_rad = math.radians(lat)
            n = 2.0 ** zoom
            x = int((lon + 180.0) / 360.0 * n)
            y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
            
            # Use precipitation layer only since map layers require subscription
            radar_url = f"https://tile.openweathermap.org/map/precipitation_new/{zoom}/{x}/{y}.png?appid={API_KEY}"
            radar_response = requests.get(radar_url, timeout=10)
            radar_response.raise_for_status()
            
            # Create a blank base map
            blank_map = np.zeros((256, 256), dtype=np.uint8)  # Standard tile size is 256x256
            blank_map_bytes = io.BytesIO()
            Image.fromarray(blank_map).save(blank_map_bytes, format='PNG')
            blank_map_bytes.seek(0)
            
            # Update radar display with precipitation layer and blank base map
            self.radar.update_radar(
                radar_response.content, 
                blank_map_bytes.getvalue(),
                location_name=self.location  # Pass current location name
            )
            
        except Exception as e:
            logging.error(f"Error fetching radar data: {str(e)}", exc_info=True)

    def _update_display(self) -> None:
        """Update all display widgets with new weather data"""
        try:
            logging.debug("Starting display update")
            current = self.weather_data['current']
            
            # Add debug logging for icon code
            icon_code = current['weather'][0]['icon']
            logging.debug(f"Weather icon code: {icon_code}")
            
            # Get the icon and log it
            icon_segments = LargeWeatherIcons.get(icon_code)
            logging.debug(f"Generated colored ASCII art segments: {icon_segments}")
            
            # Update weather icon with colored ASCII art
            self.current_large_icon.set_text(icon_segments)
            
            # Update current conditions with new formatting
            temp = current['main']['temp']
            temp_style = 'temp_hot' if is_hot_temperature(temp) else 'temp_cold'
            
            self.current_temp.set_text([
                "Temperature: ",
                (temp_style, format_temperature(temp))
            ])
            
            self.current_desc.set_text(
                ('description', f"{current['weather'][0]['description'].capitalize()}")
            )
            
            self.current_feels.set_text(
                f"Feels like: {format_temperature(current['main']['feels_like'])}"
            )
            
            self.current_humidity.set_text(
                f"Humidity: {current['main']['humidity']}%"
            )
            
            self.current_wind.set_text(
                f"Wind: {format_wind_speed(current['wind']['speed'])}"
            )
            
            self.current_pressure.set_text(
                f"Pressure: {current['main']['pressure']} hPa"
            )
            
            # Update header with location name - Fixed to update the Text widget directly
            header_cols = self.header.original_widget
            header_text = header_cols.contents[0][0]  # Get the Text widget from the Columns
            header_text.set_text(f"Terminal Weather - {current['name']}, {current['sys']['country']}")
            
            # Update hourly forecast
            self._update_hourly_forecast()
            
            # Update daily forecast
            self._update_daily_forecast()
            
            logging.debug("Display update completed successfully")
            
        except Exception as e:
            logging.error(f"Error updating display: {str(e)}", exc_info=True)
            self._show_error(f"Error updating display: {str(e)}")

    def _show_error(self, message: str) -> None:
        """Display error dialog"""
        dialog = ErrorDialog(message, self, retry_callback=self.update_weather)
        
        # Calculate dialog size (50% of terminal width, 30% of height)
        screen = urwid.raw_display.Screen()
        screen_cols, screen_rows = screen.get_cols_rows()
        dialog_width = int(screen_cols * 0.5)
        dialog_height = int(screen_rows * 0.3)
        
        # Create dialog overlay
        overlay = urwid.Overlay(
            dialog,
            self.frame,
            'center', dialog_width,
            'middle', dialog_height
        )
        
        self.loop.widget = overlay

    def run(self) -> None:
        """Start the application"""
        # Use overlay instead of frame
        self.loop = urwid.MainLoop(self.overlay, self.palette)
        # Schedule the first update to happen right after the loop starts
        self.loop.set_alarm_in(0.1, self._first_update)
        self.loop.run()

    def _first_update(self, loop, user_data):
        """Initial weather update after UI starts"""
        logging.debug("Starting first update")
        self.update_weather()

    def show_settings(self, button=None):
        """Show the settings dialog"""
        dialog = SettingsDialog(self, on_close=self._close_dialog)
        
        # Calculate dialog size
        screen = urwid.raw_display.Screen()
        screen_cols, screen_rows = screen.get_cols_rows()
        dialog_width = int(screen_cols * 0.6)
        dialog_height = int(screen_rows * 0.8)
        
        # Create overlay
        self.settings_overlay = urwid.Overlay(  # Store the settings overlay
            dialog,
            self.frame,
            'center', dialog_width,
            'middle', dialog_height
        )
        
        self.loop.widget = self.settings_overlay

    def show_location_dialog(self, locations):
        """Show location selection dialog"""
        dialog = LocationDialog(locations, self, self)
        
        # Calculate dialog size
        screen = urwid.raw_display.Screen()
        screen_cols, screen_rows = screen.get_cols_rows()
        dialog_width = int(screen_cols * 0.6)
        dialog_height = int(screen_rows * 0.6)
        
        # Create overlay for location dialog on top of settings dialog
        overlay = urwid.Overlay(
            dialog,
            self.app.settings_overlay,  # Use the settings overlay as bottom widget
            'center', dialog_width,
            'middle', dialog_height
        )
        
        # Set the overlay as the active widget
        self.app.loop.widget = overlay

    def _close_dialog(self):
        """Close the current dialog and return to main view"""
        self.loop.widget = self.frame

    def show_error(self, message):
        """Show error message"""
        self._show_error(message)

def main():
    if not API_KEY:
        print("Please set OPENWEATHER_API_KEY environment variable")
        return
    
    if len(API_KEY) != 32:  # OpenWeather API keys are 32 characters long
        print("Invalid API key format. Please check your API key.")
        return
    
    print("Starting Terminal Weather...")
    print("Note: If you just created your API key, it may take up to 2 hours to activate.")
    print("The app will keep trying to connect every 5 minutes.")
    
    logging.debug(f"API Key loaded: {API_KEY[:4]}...")
    app = WeatherApp()
    app.run()

if __name__ == "__main__":
    main()

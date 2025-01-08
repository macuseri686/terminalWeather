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
from helpers import (
    format_temperature,
    format_wind_speed,
    format_time,
    is_hot_temperature,
    make_api_request,
    set_api_key,
    set_units,
    set_time_format,
    download_binary
)
from dialogs.error_dialog import ErrorDialog
from dialogs.progress_dialog import ProgressDialog
from dialogs.location_dialog import LocationDialog
from dialogs.settings_dialog import SettingsDialog
from icon_handler import WeatherIcons, LargeWeatherIcons
from radar import RadarDisplay, RadarContainer
from geo_handler import GeoHandler
import locale

# Set locale to user's default to support UTF-8
locale.setlocale(locale.LC_ALL, '')

# Load environment variables from .env file
load_dotenv()

# Get API key from environment variables
API_KEY = os.getenv('OPENWEATHER_API_KEY')
if API_KEY:
    set_api_key(API_KEY)  # Set the API key in helpers module
DEFAULT_ZIP = os.getenv('DEFAULT_ZIP', '98272')  # Default to Monroe, WA if not set
DEFAULT_COUNTRY = os.getenv('DEFAULT_COUNTRY', 'US')  # Default to US if not set
UNITS = os.getenv('UNITS', 'metric').lower()  # Default to metric if not set
TIME_FORMAT = os.getenv('TIME_FORMAT', '24')  # Default to 24-hour if not set

# Add this near the top of the file, after imports
logging.basicConfig(
    filename='weather_app.log',
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# After loading environment variables, add:
if API_KEY:
    set_api_key(API_KEY)
if UNITS:
    set_units(UNITS)
if TIME_FORMAT:
    set_time_format(TIME_FORMAT)

class WeatherApp:
    def __init__(self):
        self.geo_handler = GeoHandler()
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
            ('map_label', 'yellow,bold', 'black'),
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
            ('map_water', 'light blue', 'dark blue'),  # Water features
            ('map_water_fill', 'dark blue', 'dark blue'),  # Water body fill
            ('map_road', 'black', 'light gray'),  # Roads with gray background
            ('map_road_highway', 'white,bold', 'dark gray'),  # Highways
            ('map_road_major', 'white', 'dark gray'),         # Trunk roads
            ('map_road_primary', 'light gray', 'dark gray'),  # Primary roads
            ('map_road_secondary', 'dark gray', 'dark gray'), # Secondary roads
            ('map_road_tertiary', 'dark gray', 'dark gray'),  # Tertiary roads
            ('map_road', 'dark gray', 'light gray'),  # Default road style
            ('map_ocean', 'light blue', 'dark blue'),  # Ocean areas
            ('map_urban', 'dark gray', 'default'),  # Add this for urban areas
            ('map_nature', 'dark green', 'default'),  # Add this for parks/forests
            ('map_land', 'light gray', 'default'),  # Land areas - use default background instead of light gray
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
        screen = urwid.raw_display.Screen()
        screen_width, _ = screen.get_cols_rows()
        
        # Use full screen width for the radar
        self.radar = RadarDisplay(screen_width - 2, height - 2)  # -2 for borders
        logging.debug(f"Created radar display with size: {screen_width-2}x{height-2}")
        
        # Create a fixed-size box for the radar
        radar_box = urwid.BoxAdapter(
            self.radar,
            height - 2  # Match the height we want, accounting for borders
        )
        return urwid.AttrMap(urwid.LineBox(
            radar_box,
            title="Weather Radar"
        ), 'linebox')

    def _get_location_coords(self) -> tuple:
        """Get coordinates for the current location"""
        return self.geo_handler.get_location_coords()

    def update_weather(self) -> None:
        """Fetch and update weather data"""
        try:
            logging.debug("Starting weather update")
            
            # Get coordinates for the location
            lat, lon = self._get_location_coords()
            logging.debug(f"Using coordinates: {lat}, {lon}")
            
            # Get current weather and forecast
            self.weather_data = {
                'current': make_api_request("/weather", {
                    "lat": lat,
                    "lon": lon,
                    "units": UNITS
                }),
                'forecast': make_api_request("/forecast", {
                    "lat": lat,
                    "lon": lon,
                    "units": UNITS
                })
            }
            
            # Schedule next update in 10 minutes
            self.loop.set_alarm_in(600, lambda loop, _: self.update_weather())
            
            self._update_display()
            
            # Update radar with new coordinates
            self._update_radar(lat, lon)
            
        except requests.RequestException as e:
            logging.error(f"Network error: {str(e)}")
            self._show_error(f"Network error: {str(e)}")
        except Exception as e:
            logging.error(f"Error fetching weather data: {str(e)}", exc_info=True)
            self._show_error(f"Error fetching weather data: {str(e)}")

    def _update_radar(self, lat: float, lon: float) -> None:
        """Update the radar display"""
        try:
            zoom = 11  # Changed from 12 to 11 to zoom out
            lat_rad = math.radians(lat)
            n = 2.0 ** zoom
            
            # Convert coordinates to tile numbers
            xtile = int((lon + 180.0) / 360.0 * n)
            ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
            
            # Calculate tile bounds using Mercator projection formulas
            def lat_from_y(y, n_tiles):
                n = math.pi - 2.0 * math.pi * y / n_tiles
                return math.degrees(math.atan(math.sinh(n)))
            
            def lon_from_x(x, n_tiles):
                return x * 360.0 / n_tiles - 180.0
            
            # Calculate bounds
            lat1 = lat_from_y(ytile, n)  # North latitude
            lat2 = lat_from_y(ytile + 1, n)  # South latitude
            lon1 = lon_from_x(xtile, n)  # West longitude
            lon2 = lon_from_x(xtile + 1, n)  # East longitude
            
            logging.debug(f"Tile bounds: N={lat1:.4f}, S={lat2:.4f}, W={lon1:.4f}, E={lon2:.4f}")
            
            # Re-enable radar data fetching
            radar_data = download_binary(
                f"/map/precipitation_new/{zoom}/{xtile}/{ytile}.png",
                base_url="https://tile.openweathermap.org"
            )
            
            # Get map features from Overpass API
            overpass_data = self.radar._fetch_overpass_data(lat, lon)
            
            # Update radar display
            self.radar.update_radar(
                radar_data,
                overpass_data,
                location_name=self.geo_handler.get_current_location(),
                center_lat=lat,
                center_lon=lon,
                tile_bounds=(lat1, lon1, lat2, lon2)
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
            header_text.set_text(f"Terminal Weather - {self.geo_handler.get_current_location()}")
            
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
        # Show initial loading dialog
        progress = ProgressDialog("Loading weather")
        
        # Calculate dialog size
        screen = urwid.raw_display.Screen()
        
        # Enable UTF-8 and 256 colors support
        screen.set_terminal_properties(colors=256)
        
        # Set encoding for screen output
        import sys
        if hasattr(sys.stdout, 'encoding'):
            sys.stdout.reconfigure(encoding='utf-8')  # Python 3.7+
        
        screen_cols, screen_rows = screen.get_cols_rows()
        dialog_width = int(screen_cols * 0.3)
        dialog_height = int(screen_rows * 0.2)
        
        # Create overlay for progress dialog
        self.loading_overlay = urwid.Overlay(
            progress,
            self.overlay,  # Use main overlay as bottom widget
            'center', dialog_width,
            'middle', dialog_height
        )
        
        # Use loading overlay as initial widget with UTF-8 support
        self.loop = urwid.MainLoop(
            self.loading_overlay, 
            self.palette,
            screen=screen,  # Use our configured screen
            handle_mouse=True  # Keep mouse support but remove keyboard handling
        )
        
        # Start the loading animation
        progress.start_animation(self.loop)
        
        # Schedule the first update
        self.loop.set_alarm_in(0.1, self._first_update)
        self.loop.run()

    def _first_update(self, loop, user_data):
        """Initial weather update after UI starts"""
        logging.debug("Starting first update")
        try:
            self.update_weather()
        finally:
            # Switch to main view after update (whether it succeeded or failed)
            self.loop.widget = self.overlay

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

    def update_location_settings(self):
        """Update location settings from environment variables"""
        # Reinitialize the geo_handler to pick up new settings
        self.geo_handler = GeoHandler()

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

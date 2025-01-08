import urwid
import logging
import os
from typing import Optional, Callable
import requests
from dialogs.location_dialog import LocationDialog
from dialogs.progress_dialog import ProgressDialog
from helpers import (
    make_api_request,
    set_api_key,
    set_units,
    set_time_format
)

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
                search_query = location
                if country:
                    search_query += f",{country}"
                    
                locations = make_api_request(
                    "/geo/1.0/direct",
                    params={
                        "q": search_query,
                        "limit": 5,
                        "appid": self.api_key_edit.edit_text
                    },
                    base_url="http://api.openweathermap.org"
                )
                
                if not locations:
                    self._show_error("No locations found")
                    return
            else:
                # Search by ZIP code
                location_data = make_api_request(
                    "/geo/1.0/zip",
                    params={
                        "zip": f"{location},{country or 'US'}",
                        "appid": self.api_key_edit.edit_text
                    },
                    base_url="http://api.openweathermap.org"
                )
                
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
            
        except requests.RequestException as e:
            self._show_error(str(e))
        except Exception as e:
            logging.error(f"Error searching location: {str(e)}", exc_info=True)
            self._show_error(f"Error searching location: {str(e)}")

    def _on_save(self, button):
        # Show progress dialog
        progress = ProgressDialog("Loading weather")
        
        # Calculate dialog size
        screen = urwid.raw_display.Screen()
        screen_cols, screen_rows = screen.get_cols_rows()
        dialog_width = int(screen_cols * 0.3)
        dialog_height = int(screen_rows * 0.2)
        
        # Create overlay for progress dialog
        overlay = urwid.Overlay(
            progress,
            self.app.frame,  # Use main frame as bottom widget
            'center', dialog_width,
            'middle', dialog_height
        )
        
        # Set the overlay as the active widget and start animation
        self.app.loop.widget = overlay
        progress.start_animation(self.app.loop)
        
        # Schedule the actual save to happen after the dialog is shown
        def do_save(loop, user_data):
            try:
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
                    settings['DEFAULT_CITY'] = ''
                    settings['DEFAULT_STATE'] = ''
                else:
                    settings['DEFAULT_ZIP'] = ''
                    parts = [p.strip() for p in self.location_edit.edit_text.split(',')]
                    settings['DEFAULT_CITY'] = parts[0] if parts else ''
                    settings['DEFAULT_STATE'] = parts[1] if len(parts) > 1 else ''
                
                logging.debug(f"Saving settings: {settings}")
                
                # Write to .env file
                with open('.env', 'w') as f:
                    for key, value in settings.items():
                        if value:  # Only write non-empty values
                            f.write(f'{key}={value}\n')
                
                # Update app settings
                self.app.api_key = settings['OPENWEATHER_API_KEY']
                set_api_key(self.app.api_key)  # Update API key in helpers module
                self.app.units = settings['UNITS']
                self.app.time_format = settings['TIME_FORMAT']
                
                # Update helpers module settings
                set_api_key(self.app.api_key)
                set_units(self.app.units)
                set_time_format(self.app.time_format)
                
                # Update environment variables
                for key, value in settings.items():
                    if value:
                        os.environ[key] = value
                    else:
                        os.environ.pop(key, None)
                
            except Exception as e:
                logging.error(f"Error saving settings: {str(e)}", exc_info=True)
                progress.stop_animation(loop)
                self.app.show_error(f"Error saving settings: {str(e)}")
                return
            
            finally:
                # Stop animation and return to main view
                progress.stop_animation(loop)
                self.app.loop.widget = self.app.frame
                
                # Refresh weather data
                self.app.update_weather()
        
        # Schedule the save
        self.app.loop.set_alarm_in(0.1, do_save)

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
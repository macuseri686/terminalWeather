import urwid
import logging
from .progress_dialog import ProgressDialog

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
        
        # Schedule the actual update to happen after the dialog is shown
        def do_update(loop, user_data):
            try:
                # Update parent dialog with selected location
                if self.parent_dialog.zip_type.state:
                    pass  # Don't modify the ZIP code field
                else:
                    name_parts = [location['name']]
                    if location.get('state'):
                        name_parts.append(location['state'])
                    self.parent_dialog.location_edit.set_edit_text(', '.join(name_parts))
                
                # Update country
                self.parent_dialog.country_edit.set_edit_text(location['country'])
                
            finally:
                # Stop animation and return to settings dialog
                progress.stop_animation(loop)
                self.app.loop.widget = self.app.settings_overlay
        
        # Schedule the update
        self.app.loop.set_alarm_in(0.1, do_update)

    def _on_cancel(self, button):
        # Return to settings dialog
        self.app.loop.widget = self.app.settings_overlay 
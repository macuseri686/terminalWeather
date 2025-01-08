import urwid
import numpy as np
from PIL import Image
import io
import logging

class RadarDisplay(urwid.Widget):
    _sizing = frozenset(['box'])
    
    def __init__(self, width, height):
        super().__init__()
        self.width = width
        self.height = height
        self.radar_data = None
        self.map_data = None
        self.block_char = '#'
        self.location_name = None
    
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
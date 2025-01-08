import urwid
import numpy as np
from PIL import Image
import io
import logging
import requests
from typing import Optional, Dict, List
from math import floor
import json
import os
from datetime import datetime, timedelta

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
        self.road_map = None
        self.style_map = None
        self.cache_dir = os.path.expanduser("~/.cache/terminalweather")
        os.makedirs(self.cache_dir, exist_ok=True)
        logging.debug(f"RadarDisplay initialized with size: {width}x{height}")

    def _get_cache_path(self, lat: float, lon: float, radius: float) -> str:
        """Get path for cached Overpass data"""
        return os.path.join(self.cache_dir, f"overpass_{lat:.4f}_{lon:.4f}_{radius}.json")

    def _is_cache_valid(self, cache_path: str, max_age_hours: int = 24) -> bool:
        """Check if cached data is still valid"""
        if not os.path.exists(cache_path):
            return False
        
        mtime = datetime.fromtimestamp(os.path.getmtime(cache_path))
        age = datetime.now() - mtime
        return age < timedelta(hours=max_age_hours)

    def _fetch_overpass_data(self, lat: float, lon: float, radius: float = 10000) -> Optional[Dict]:
        """Fetch map data from Overpass API with caching"""
        cache_path = self._get_cache_path(lat, lon, radius)
        
        # Try to use cached data
        if self._is_cache_valid(cache_path):
            try:
                with open(cache_path, 'r') as f:
                    data = json.load(f)
                logging.debug(f"Using cached Overpass data from {cache_path}")
                return data
            except Exception as e:
                logging.error(f"Error reading cache: {str(e)}")
        
        # Fetch new data if cache is invalid or missing
        try:
            query = f"""
                [out:json][timeout:25];
                (
                  way["highway"~"^(motorway|trunk|primary|secondary|tertiary)$"]
                    (around:{radius},{lat},{lon});
                  way["natural"="water"]
                    (around:{radius},{lat},{lon});
                  way["waterway"="river"]
                    (around:{radius},{lat},{lon});
                  node["place"~"^(city|town)$"]
                    (around:{radius},{lat},{lon});
                );
                out body;
                >;
                out skel qt;
            """
            
            logging.debug(f"Fetching Overpass data for: {lat}, {lon}, radius: {radius}m")
            url = "https://overpass-api.de/api/interpreter"
            headers = {'User-Agent': 'TerminalWeather/1.0'}
            response = requests.post(url, data={'data': query}, headers=headers, timeout=25)
            response.raise_for_status()
            data = response.json()
            
            # Log the number of elements by type
            element_types = {}
            for element in data.get('elements', []):
                element_type = element['type']
                element_types[element_type] = element_types.get(element_type, 0) + 1
            logging.debug(f"Received elements by type: {element_types}")
            
            # Cache the response
            try:
                with open(cache_path, 'w') as f:
                    json.dump(data, f)
                logging.debug(f"Cached Overpass data to {cache_path}")
            except Exception as e:
                logging.error(f"Error caching data: {str(e)}")
            
            return data
        except Exception as e:
            logging.error(f"Failed to fetch Overpass data: {str(e)}")
            return None

    def _process_overpass_features(self, data: Dict, width: int, height: int, 
                                 center_lat: float, center_lon: float,
                                 degrees_per_pixel_lat: float = None,
                                 degrees_per_pixel_lon: float = None,
                                 tile_bounds: tuple = None) -> tuple:
        """Process Overpass API data and create ASCII map and style map"""
        logging.debug(f"Processing features for map size: {width}x{height}")
        char_map = np.full((height, width), ' ', dtype='U1')
        style_map = np.full((height, width), 'map_background', dtype=object)
        
        if not data or 'elements' not in data:
            logging.warning("No elements found in Overpass data")
            return char_map, style_map

        # Initialize counters
        ways_count = {'highway': 0, 'water': 0, 'waterway': 0}
        places_count = 0

        # First, build a nodes lookup dictionary
        nodes = {}
        node_count = 0
        places = []  # Store places for later
        
        for element in data['elements']:
            if element['type'] == 'node':
                nodes[element['id']] = (element['lat'], element['lon'])
                node_count += 1
                # Store places for later processing
                if 'tags' in element and element['tags'].get('place') in ['city', 'town']:
                    places.append(element)
        
        logging.debug(f"Processed {node_count} nodes")

        # First pass: Draw water bodies (to be in background)
        for element in data['elements']:
            if element['type'] == 'way' and 'tags' in element:
                coords = [nodes[ref] for ref in element['nodes'] if ref in nodes]
                if not coords:
                    continue

                if element['tags'].get('natural') == 'water':
                    char = '~'
                    style = 'map_water_fill'
                    ways_count['water'] += 1
                    self._draw_line_feature(char_map, style_map, coords, char, style, 
                                         center_lat, center_lon, width, height,
                                         fill=True)  # Fill water bodies

        # Define road characters for different types
        road_chars = {
            'motorway': '#',     # Hash for highways
            'trunk': '=',        # Double equals for major roads
            'primary': '-',      # Single dash for primary roads
            'secondary': '.',    # Dots for secondary roads
            'tertiary': ',',     # Comma for tertiary roads
        }

        # Update the road style assignment in the loop:
        road_styles = {
            'motorway': 'map_road_highway',
            'trunk': 'map_road_major',
            'primary': 'map_road_primary',
            'secondary': 'map_road_secondary',
            'tertiary': 'map_road_tertiary',
        }

        # Second pass: Draw roads and rivers
        for element in data['elements']:
            if element['type'] == 'way':
                coords = [nodes[ref] for ref in element['nodes'] if ref in nodes]
                if not coords:
                    continue

                char = ' '
                style = 'map_background'
                if 'tags' in element:
                    highway_type = element.get('tags', {}).get('highway')
                    if highway_type in road_chars:
                        char = road_chars[highway_type]
                        style = road_styles[highway_type]
                        ways_count['highway'] += 1
                    elif element['tags'].get('waterway') == 'river':
                        char = '~'
                        style = 'map_water'
                        ways_count['waterway'] += 1
                    elif element['tags'].get('natural') == 'water':
                        continue  # Skip water bodies in second pass

                self._draw_line_feature(char_map, style_map, coords, char, style,
                                      center_lat, center_lon, width, height)

        # Finally, draw place labels on top of everything
        for element in places:
            name = element['tags'].get('name', '')
            if name:
                places_count += 1
                x, y = self._project_coords(
                    element['lat'], 
                    element['lon'], 
                    center_lat, 
                    center_lon, 
                    width, 
                    height,
                    degrees_per_pixel_lat,
                    degrees_per_pixel_lon,
                    tile_bounds
                )
                logging.debug(f"Processing place label '{name}' at coordinates ({x}, {y})")
                logging.debug(f"Map dimensions: {char_map.shape}")
                
                # Draw text centered at coordinates
                text_start_x = max(0, x - len(name)//2)
                text_end_x = min(width, text_start_x + len(name))
                logging.debug(f"Label span: {text_start_x} to {text_end_x} at y={y}")
                
                for i, char in enumerate(name):
                    pos_x = text_start_x + i
                    if pos_x < width:
                        try:
                            char_map[y, pos_x] = char
                            style_map[y, pos_x] = 'map_label'
                            logging.debug(f"Placed character '{char}' at ({pos_x}, {y})")
                        except IndexError:
                            logging.error(f"Failed to place character at ({pos_x}, {y}). Array shape: {char_map.shape}")

        # After processing
        label_count = np.sum(style_map == 'map_label')
        logging.debug(f"Total label characters placed in map: {label_count}")

        logging.debug(f"Processed features: {ways_count['highway']} highways, "
                     f"{ways_count['water']} water bodies, "
                     f"{ways_count['waterway']} waterways, "
                     f"{places_count} places")

        return char_map, style_map

    def _draw_line_feature(self, char_map: np.ndarray, style_map: np.ndarray, 
                          coords: List, char: str, style: str,
                          center_lat: float, center_lon: float, width: int, height: int,
                          fill: bool = False):
        """Draw a line feature on the character map"""
        points = []
        # Convert all coordinates to pixel positions
        for coord in coords:
            x, y = self._project_coords(coord[0], coord[1], center_lat, center_lon, width, height)
            points.append((x, y))
        
        if style == 'map_city_area':
            logging.debug(f"Drawing city boundary with {len(points)} points")
            # Draw boundary first
            for i in range(len(points)):
                x1, y1 = points[i]
                x2, y2 = points[(i + 1) % len(points)]  # Connect back to start
                self._draw_line_segment(char_map, style_map, x1, y1, x2, y2, char, style)
            
            if fill:
                # Find center point for flood fill
                center_x = sum(p[0] for p in points) // len(points)
                center_y = sum(p[1] for p in points) // len(points)
                self._flood_fill_from_point(char_map, style_map, center_x, center_y, style)
        else:
            # Draw other features normally
            for i in range(len(points) - 1):
                x1, y1 = points[i]
                x2, y2 = points[i + 1]
                self._draw_line_segment(char_map, style_map, x1, y1, x2, y2, char, style)

    def _flood_fill_from_point(self, char_map: np.ndarray, style_map: np.ndarray, 
                              start_x: int, start_y: int, style: str):
        """Flood fill starting from a specific point"""
        height, width = char_map.shape
        if not (0 <= start_x < width and 0 <= start_y < height):
            return
        
        # Use a queue for flood fill
        queue = [(start_x, start_y)]
        seen = set()
        
        while queue:
            x, y = queue.pop(0)
            if (x, y) in seen or not (0 <= x < width and 0 <= y < height):
                continue
            
            if style_map[y, x] != style:  # Only fill if not already filled
                char_map[y, x] = ' '
                style_map[y, x] = style
                seen.add((x, y))
                
                # Add adjacent points
                for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
                    new_x, new_y = x + dx, y + dy
                    if (new_x, new_y) not in seen:
                        queue.append((new_x, new_y))

    def _draw_text(self, char_map: np.ndarray, style_map: np.ndarray, x: int, y: int, text: str, style: str):
        """Draw text on the character map with a background"""
        height, width = char_map.shape
        if 0 <= y < height:
            # Center the text
            start_x = max(0, x - len(text)//2)
            end_x = min(width, start_x + len(text))
            
            if start_x < width and end_x > 0:
                text_portion = text[max(0, -start_x):min(len(text), width-start_x)]
                logging.debug(f"Drawing text '{text_portion}' at ({start_x}, {y})")
                
                # Draw a background space before and after text
                for i in range(max(0, start_x - 1), min(width, end_x + 1)):
                    if 0 <= y < height:
                        char_map[y, i] = ' '
                        style_map[y, i] = style
                
                # Draw the text
                for i, char in enumerate(text_portion):
                    if 0 <= y < height and start_x + i < width:
                        char_map[y, start_x + i] = char
                        style_map[y, start_x + i] = style
                
                # Draw text above and below to make it more visible
                if y > 0:
                    char_map[y-1, start_x:end_x] = '‾' * len(text_portion)
                    style_map[y-1, start_x:end_x] = style
                if y < height - 1:
                    char_map[y+1, start_x:end_x] = '_' * len(text_portion)
                    style_map[y+1, start_x:end_x] = style

    def _draw_line_segment(self, char_map: np.ndarray, style_map: np.ndarray, x1: int, y1: int, x2: int, y2: int, char: str, style: str):
        """Draw a line segment using Bresenham's algorithm"""
        height, width = char_map.shape
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        steep = dy > dx

        if steep:
            x1, y1 = y1, x1
            x2, y2 = y2, x2

        if x1 > x2:
            x1, x2 = x2, x1
            y1, y2 = y2, y1

        dx = x2 - x1
        dy = abs(y2 - y1)
        error = dx // 2
        y = y1
        y_step = 1 if y1 < y2 else -1

        for x in range(x1, x2 + 1):
            if steep:
                if 0 <= y < width and 0 <= x < height:
                    char_map[x, y] = char
                    style_map[x, y] = style
            else:
                if 0 <= x < width and 0 <= y < height:
                    char_map[y, x] = char
                    style_map[y, x] = style
            error -= dy
            if error < 0:
                y += y_step
                error += dx

    def _project_coords(self, lat: float, lon: float, center_lat: float, center_lon: float, 
                       width: int, height: int, degrees_per_pixel_lat=None, 
                       degrees_per_pixel_lon=None, tile_bounds=None) -> tuple:
        """Project geographic coordinates to pixel coordinates relative to center"""
        if tile_bounds:
            lat1, lon1, lat2, lon2 = tile_bounds
            # Adjust calculation to center the reference point
            x = int(width/2 + ((lon - center_lon) / (lon2 - lon1)) * width)
            y = int(height/2 + ((center_lat - lat) / (lat1 - lat2)) * height)
            
            # Add bounds checking
            x = max(0, min(width - 1, x))
            y = max(0, min(height - 1, y))
            
            logging.debug(f"Projecting ({lat}, {lon}) to ({x}, {y}) using bounds: N={lat1}, S={lat2}, W={lon1}, E={lon2}")
        else:
            # Fallback to old calculation
            DEGREES_PER_TILE = 0.0439  # at zoom level 12
            scale = width / DEGREES_PER_TILE
            x = width//2 + int((lon - center_lon) * scale)
            y = height//2 - int((lat - center_lat) * scale)
            
            # Add bounds checking
            x = max(0, min(width - 1, x))
            y = max(0, min(height - 1, y))
        
        return x, y

    def render(self, size, focus=False):
        maxcol, maxrow = size
        result = []
        
        if self.radar_data is None or self.road_map is None:
            logging.debug("No radar or road map data available")
            empty_line = " " * maxcol
            for i in range(maxrow):
                result.append(([(None, maxcol)], empty_line.encode('utf-8')))
        else:
            # Use the original map size but ensure it fits in the display
            scaled_width = min(maxcol, self.road_map.shape[1])
            scaled_height = min(maxrow, self.road_map.shape[0])
            
            # Center horizontally and vertically
            h_offset = (maxcol - scaled_width) // 2
            v_offset = (maxrow - scaled_height) // 2
            
            # Resize radar data to match map dimensions
            image_radar = Image.fromarray((self.radar_data * 255).astype('uint8'))
            image_radar = image_radar.resize((scaled_width, scaled_height), Image.Resampling.NEAREST)
            radar_data = np.array(image_radar) / 255.0
            
            # Create display lines
            for i in range(maxrow):
                line = []
                attrs = []
                
                for j in range(maxcol):
                    map_y = i - v_offset
                    map_x = j - h_offset
                    
                    if 0 <= map_y < scaled_height and 0 <= map_x < scaled_width:
                        val = radar_data[map_y, map_x]
                        map_char = self.road_map[map_y, map_x]
                        map_style = self.style_map[map_y, map_x]
                        
                        # First, determine precipitation level if any
                        if val > 0.01:
                            precip_style = 'radar_' + (
                                'very_light' if val <= 0.05 else  # drizzle
                                'light' if val <= 0.1 else        # light rain
                                'moderate' if val <= 0.2 else     # moderate rain
                                'heavy' if val <= 0.4 else        # heavy rain
                                'extreme'                         # extreme rain
                            )
                        else:
                            precip_style = None

                        # Now determine what to show based on map features
                        if map_style == 'map_label':
                            # Labels always on top
                            char = map_char
                            style = map_style
                        elif map_style.startswith('map_road_'):
                            # Roads on top of precipitation
                            char = map_char
                            style = map_style
                        elif map_style in ['map_water', 'map_water_fill']:
                            # Water features on top of precipitation
                            char = map_char
                            style = map_style
                        elif precip_style:
                            # Show precipitation where there are no other features
                            char = self.block_char
                            style = precip_style
                        else:
                            # Background or other features
                            char = map_char
                            style = map_style
                    else:
                        char = ' '
                        style = 'map_background'
                    
                    line.append(char)
                    attrs.append((style, 1))
                
                line_str = ''.join(line)
                result.append((attrs, line_str.encode('utf-8')))

        return urwid.TextCanvas(
            [line for _, line in result],
            attr=[attrs for attrs, _ in result],
            maxcol=maxcol
        )

    def update_radar(self, radar_image_data, overpass_data, location_name=None, 
                    center_lat=None, center_lon=None, tile_bounds=None):
        """Update radar display with new image data and map features"""
        try:
            # Process radar data
            radar_image = Image.open(io.BytesIO(radar_image_data))
            if radar_image.mode != 'RGBA':  # Change from 'L' to 'RGBA'
                radar_image = radar_image.convert('RGBA')
            
            # Extract alpha channel which contains precipitation data
            radar_data = np.array(radar_image)
            # Use alpha channel (precipitation intensity) and normalize
            self.radar_data = radar_data[:, :, 3] / 255.0  # Changed from full array to alpha channel
            
            logging.debug(f"Radar data shape: {self.radar_data.shape}")
            logging.debug(f"Radar data range: {self.radar_data.min():.3f} to {self.radar_data.max():.3f}")
            
            # Store location name
            self.location_name = location_name
            
            # Process Overpass data into ASCII map
            if center_lat is not None and center_lon is not None:
                if tile_bounds:
                    lat1, lon1, lat2, lon2 = tile_bounds
                    degrees_per_pixel_lat = (lat1 - lat2) / self.height
                    degrees_per_pixel_lon = (lon2 - lon1) / self.width
                    
                    self.road_map, self.style_map = self._process_overpass_features(
                        overpass_data,
                        self.width,
                        self.height,
                        center_lat,
                        center_lon,
                        degrees_per_pixel_lat,
                        degrees_per_pixel_lon,
                        tile_bounds
                    )
                else:
                    self.road_map, self.style_map = self._process_overpass_features(
                        overpass_data,
                        self.width,
                        self.height,
                        center_lat,
                        center_lon
                    )
            else:
                self.road_map = np.full((self.height, self.width), ' ', dtype='U1')
                self.style_map = np.full((self.height, self.width), 'map_background', dtype=object)
            
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
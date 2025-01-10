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
import sys

# Create a logger specifically for radar
radar_logger = logging.getLogger('TermWeather.radar')

class RadarDisplay(urwid.Widget):
    _sizing = frozenset(['box'])
    
    INTENSITY_CHARS = {
        'none': ' ',
        'very_light': '░',
        'light': '▒',
        'moderate': '▓',
        'heavy': '█',
        'extreme': '█'
    }
    
    MAP_CHARS = {
        'road': '═',
        'road_vertical': '║',
        'city': '○',
        'location': '◎',
        'water': '≈',
        'corner_tl': '╔',
        'corner_tr': '╗',
        'corner_bl': '╚',
        'corner_br': '╝'
    }
    
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
        self.zoom = 11  # Add default zoom level
        self.cache_dir = os.path.expanduser("~/.cache/terminalweather")
        os.makedirs(self.cache_dir, exist_ok=True)
        radar_logger.debug(f"RadarDisplay initialized with size: {width}x{height}")

    def _get_cache_path(self, lat: float, lon: float, radius: float) -> str:
        """Get path for cached Overpass data"""
        # Include zoom level in the cache key
        return os.path.join(self.cache_dir, 
                           f"overpass_{lat:.4f}_{lon:.4f}_{radius}_{self.zoom}.json")

    def _is_cache_valid(self, cache_path: str, max_age_hours: int = 24) -> bool:
        """Check if cached data is still valid"""
        if not os.path.exists(cache_path):
            return False
        
        mtime = datetime.fromtimestamp(os.path.getmtime(cache_path))
        age = datetime.now() - mtime
        return age < timedelta(hours=max_age_hours)

    def _fetch_overpass_data(self, lat: float, lon: float, radius: float = None) -> Optional[Dict]:
        """Fetch map data from Overpass API with caching"""
        # Calculate radius based on zoom level
        if radius is None:
            base_radius = 5000
            zoom_diff = 11 - self.zoom
            radius = base_radius * (2 ** zoom_diff)
            radar_logger.debug(f"Using radius {radius}m for zoom level {self.zoom}")
        
        # Adjust road types based on zoom level
        road_filter = ""
        if self.zoom >= 11:
            # Show all road types at high zoom levels
            road_filter = '"highway"~"^(motorway|trunk|primary|secondary|tertiary)$"'
        elif self.zoom >= 10:
            # Show only major roads
            road_filter = '"highway"~"^(motorway|trunk|primary)$"'
        else:
            # Show only highways at low zoom levels
            road_filter = '"highway"~"^(motorway|trunk)$"'
        
        cache_path = self._get_cache_path(lat, lon, radius)
        
        # Try to use cached data
        if self._is_cache_valid(cache_path):
            try:
                with open(cache_path, 'r') as f:
                    data = json.load(f)
                radar_logger.debug(f"Using cached Overpass data from {cache_path}")
                return data
            except Exception as e:
                radar_logger.error(f"Error reading cache: {str(e)}")
        
        # Fetch new data if cache is invalid or missing
        try:
            query = f"""
                [out:json][timeout:25];
                (
                  way[{road_filter}]
                    (around:{radius},{lat},{lon});
                  way["natural"="water"]["water"="bay"]
                    (around:{radius},{lat},{lon});
                  relation["natural"="water"]["water"="bay"]
                    (around:{radius},{lat},{lon});
                  way["place"="sea"]
                    (around:{radius},{lat},{lon});
                  relation["place"="sea"]
                    (around:{radius},{lat},{lon});
                  way["water"="strait"]
                    (around:{radius},{lat},{lon});
                  relation["water"="strait"]
                    (around:{radius},{lat},{lon});
                  way["natural"="water"]
                    (around:{radius},{lat},{lon});
                  relation["natural"="water"]
                    (around:{radius},{lat},{lon});
                  relation["water"="lake"]
                    (around:{radius},{lat},{lon});
                  relation["water"="reservoir"]
                    (around:{radius},{lat},{lon});
                  way["waterway"="river"]
                    (around:{radius},{lat},{lon});
                  way["natural"="coastline"]
                    (around:{radius},{lat},{lon});
                  relation["place"="ocean"]
                    (around:{radius},{lat},{lon});
                  relation["place"="sea"]
                    (around:{radius},{lat},{lon});
                  way["place"="island"]
                    (around:{radius},{lat},{lon});
                  relation["place"="island"]
                    (around:{radius},{lat},{lon});
                  way["natural"="land"]
                    (around:{radius},{lat},{lon});
                  relation["natural"="land"]
                    (around:{radius},{lat},{lon});
                  way["landuse"~"^(residential|commercial|industrial)$"]
                    (around:{radius},{lat},{lon});
                  way["leisure"~"^(park|garden|nature_reserve)$"]
                    (around:{radius},{lat},{lon});
                  way["natural"~"^(wood|forest)$"]
                    (around:{radius},{lat},{lon});
                  node["place"~"^(city|town)$"]
                    (around:{radius},{lat},{lon});
                );
                out body;
                >;
                out skel qt;
            """
            
            radar_logger.debug(f"Fetching Overpass data for: {lat}, {lon}, radius: {radius}m")
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
            radar_logger.debug(f"Received elements by type: {element_types}")
            
            # Cache the response
            try:
                with open(cache_path, 'w') as f:
                    json.dump(data, f)
                radar_logger.debug(f"Cached Overpass data to {cache_path}")
            except Exception as e:
                radar_logger.error(f"Error caching data: {str(e)}")
            
            return data
        except Exception as e:
            radar_logger.error(f"Failed to fetch Overpass data: {str(e)}")
            return None

    def _process_overpass_features(self, data: Dict, width: int, height: int, 
                                 center_lat: float, center_lon: float,
                                 degrees_per_pixel_lat: float = None,
                                 degrees_per_pixel_lon: float = None,
                                 tile_bounds: tuple = None) -> tuple:
        """Process Overpass API data and create ASCII map and style map"""
        radar_logger.debug(f"Processing features for map size: {width}x{height}")
        
        # Debug the data we received
        water_features = [e for e in data['elements'] if e['type'] in ['way', 'relation'] 
                         and 'tags' in e and ('natural' in e['tags'] or 'water' in e['tags'] 
                         or 'place' in e['tags'])]
        radar_logger.debug(f"Found water features: {[f['tags'].get('name', 'unnamed') + ': ' + str(f['tags']) for f in water_features]}")
        
        char_map = np.full((height, width), ' ', dtype='U1')
        style_map = np.full((height, width), 'map_background', dtype=object)

        if not data or 'elements' not in data:
            radar_logger.warning("No elements found in Overpass data")
            return char_map, style_map

        # Initialize counters and lookups
        ways_count = {'highway': 0, 'water': 0, 'waterway': 0}
        places_count = 0
        nodes = {}
        ways = {}
        node_count = 0
        places = []
        
        # Build node and way lookups
        for element in data['elements']:
            if element['type'] == 'node':
                nodes[element['id']] = (element['lat'], element['lon'])
                node_count += 1
                if 'tags' in element and element['tags'].get('place') in ['city', 'town']:
                    places.append(element)
            elif element['type'] == 'way':
                ways[element['id']] = element

        # First pass: Process large water bodies (lakes, ocean)
        for element in data['elements']:
            if element['type'] in ['way', 'relation'] and 'tags' in element:
                tags = element['tags']
                
                # Check for water features
                if (tags.get('place') in ['sea', 'ocean', 'bay', 'strait', 'sound'] or
                    tags.get('natural') == 'water' or
                    tags.get('water') in ['lake', 'river', 'reservoir']):
                    
                    name = tags.get('name', 'unnamed')
                    # radar_logger.debug(f"Processing water body: {name} ({tags})")
                    
                    coords = self._get_element_coords(element, nodes, ways)
                    if coords:
                        coords_2d = self._project_coords_list(coords, center_lat, center_lon, width, height)
                        if len(coords_2d) >= 3:
                            # Fill water area
                            min_x = max(0, int(min(p[0] for p in coords_2d)))
                            max_x = min(width, int(max(p[0] for p in coords_2d)) + 1)
                            min_y = max(0, int(min(p[1] for p in coords_2d)))
                            max_y = min(height, int(max(p[1] for p in coords_2d)) + 1)
                            
                            fill_count = 0
                            for y in range(min_y, max_y):
                                if y < 0 or y >= height:
                                    continue
                                for x in range(min_x, max_x):
                                    if x < 0 or x >= width:
                                        continue
                                    if self._point_in_polygon(x, y, coords_2d):
                                        char_map[y, x] = '~'
                                        style_map[y, x] = 'map_water_fill'
                                        fill_count += 1
                            
                            # radar_logger.debug(f"Filled {fill_count} pixels for {name} (water)")

        # Second pass: Process land features to cut out from water
        for element in data['elements']:
            if element['type'] in ['way', 'relation'] and 'tags' in element:
                tags = element['tags']
                
                # Check for land features
                if (tags.get('place') == 'island' or 
                    tags.get('natural') == 'land' or
                    tags.get('landuse') in ['residential', 'commercial', 'industrial']):
                    
                    name = tags.get('name', 'unnamed')
                    # radar_logger.debug(f"Processing land feature: {name} ({tags})")
                    
                    coords = self._get_element_coords(element, nodes, ways)
                    if coords:
                        coords_2d = self._project_coords_list(coords, center_lat, center_lon, width, height)
                        if len(coords_2d) >= 3:
                            # Cut out land from water
                            min_x = max(0, int(min(p[0] for p in coords_2d)))
                            max_x = min(width, int(max(p[0] for p in coords_2d)) + 1)
                            min_y = max(0, int(min(p[1] for p in coords_2d)))
                            max_y = min(height, int(max(p[1] for p in coords_2d)) + 1)
                            
                            fill_count = 0
                            for y in range(min_y, max_y):
                                if y < 0 or y >= height:
                                    continue
                                for x in range(min_x, max_x):
                                    if x < 0 or x >= width:
                                        continue
                                    if self._point_in_polygon(x, y, coords_2d):
                                        char_map[y, x] = ' '
                                        style_map[y, x] = 'map_land'
                                        fill_count += 1
                            
                            # radar_logger.debug(f"Cut out {fill_count} pixels for {name} (land)")

        # Third pass: Draw rivers as lines only, no filling
        for element in data['elements']:
            if element['type'] == 'way' and 'tags' in element:
                tags = element['tags']
                if tags.get('waterway') == 'river' or (tags.get('natural') == 'water' and tags.get('water') == 'river'):
                    coords = [nodes[ref] for ref in element['nodes'] if ref in nodes]
                    if coords:
                        # Draw river as a line feature
                        self._draw_line_feature(char_map, style_map, coords, '~', 'map_water',
                                              center_lat, center_lon, width, height,
                                              fill=False)  # Explicitly set fill=False for rivers

        # Fourth pass: Draw urban and natural areas
        for element in data['elements']:
            if element['type'] in ['way', 'relation'] and 'tags' in element:
                style = None
                char = ' '
                
                # Determine style based on tags
                if element['tags'].get('landuse') in ['residential', 'commercial', 'industrial']:
                    style = 'map_urban'
                    char = 'O'  # Changed from '░' to '█' for urban areas
                elif (element['tags'].get('leisure') in ['park', 'garden', 'nature_reserve'] or
                      element['tags'].get('natural') in ['wood', 'forest']):
                    style = 'map_nature'
                    char = '^'
                
                if style:
                    coords = self._get_element_coords(element, nodes, ways)
                    if coords:
                        coords_2d = self._project_coords_list(coords, center_lat, center_lon, width, height)
                        if len(coords_2d) >= 3:
                            # Fill the area
                            for y in range(height):
                                for x in range(width):
                                    if self._point_in_polygon(x, y, coords_2d):
                                        char_map[y, x] = char
                                        style_map[y, x] = style

        # Fifth pass: Draw roads and waterways on top
        for element in data['elements']:
            if element['type'] == 'way' and 'tags' in element:
                coords = [nodes[ref] for ref in element['nodes'] if ref in nodes]
                if coords:
                    char = None
                    style = None
                    
                    if element['tags'].get('waterway') in ['river', 'stream', 'canal']:
                        char = '~'
                        style = 'map_water'
                        ways_count['waterway'] += 1
                    elif element['tags'].get('highway'):
                        highway_type = element['tags']['highway']
                        
                        # Adjust road rendering based on zoom level
                        if self.zoom >= 11:
                            char = {
                                'motorway': '#',
                                'trunk': '=',
                                'primary': '-',
                                'secondary': '-',
                                'tertiary': '-'
                            }.get(highway_type)
                        elif self.zoom >= 10:
                            char = {
                                'motorway': '#',
                                'trunk': '=',
                                'primary': '-'
                            }.get(highway_type)
                        else:
                            char = {
                                'motorway': '#',
                                'trunk': '='
                            }.get(highway_type)
                        
                        if char:  # Only process if we want to show this road type
                            style = 'map_road'
                            ways_count['highway'] += 1
                    
                    if char and style:
                        # Draw each segment with its geographic coordinates
                        for i in range(len(coords) - 1):
                            start = coords[i]
                            end = coords[i + 1]
                            
                            # Project coordinates to screen space
                            start_proj = self._project_coords(start[0], start[1], 
                                                            center_lat, center_lon, 
                                                            width, height)
                            end_proj = self._project_coords(end[0], end[1], 
                                                          center_lat, center_lon, 
                                                          width, height)
                            
                            if start_proj and end_proj:
                                x1, y1 = start_proj
                                x2, y2 = end_proj
                                # Pass the original geographic coordinates
                                geo_coords = (start[0], start[1], end[0], end[1])
                                self._draw_line_segment(char_map, style_map, 
                                                  x1, y1, x2, y2, char, style,
                                                  geo_coords=geo_coords)

        # Finally, draw place labels on top of everything
        for element in places:
            name = element['tags'].get('name', '')
            place_type = element['tags'].get('place')
            if name:
                # Adjust place visibility based on zoom level
                should_show = False
                if self.zoom >= 11:
                    # Show all places at high zoom
                    should_show = True
                elif self.zoom >= 10:
                    # Show cities and large towns
                    should_show = place_type in ['city', 'town']
                elif self.zoom >= 7:
                    # Show only cities
                    should_show = place_type == 'city'
                elif self.zoom >= 6:
                    # Show only major cities
                    should_show = (place_type == 'city' and 
                                 int(element['tags'].get('population', '0')) >= 100000)
                
                if should_show:
                    places_count += 1
                    projected = self._project_coords(
                        element['lat'], 
                        element['lon'], 
                        center_lat, 
                        center_lon, 
                        width, 
                        height,
                        tile_bounds=tile_bounds
                    )
                    
                    if projected is not None:
                        x, y = projected
                        # Check if the projected point is within the visible area
                        if 0 <= x < width and 0 <= y < height:
                            radar_logger.debug(f"Processing place label '{name}' at ({x}, {y})")
                            
                            # Draw text centered at coordinates
                            text_start_x = max(0, x - len(name)//2)
                            text_end_x = min(width, text_start_x + len(name))
                            
                            # Only draw if we have room for at least part of the name
                            if text_start_x < width and text_end_x > 0:
                                for i, char in enumerate(name):
                                    pos_x = text_start_x + i
                                    if 0 <= pos_x < width and 0 <= y < height:
                                        try:
                                            char_map[y, pos_x] = char
                                            style_map[y, pos_x] = 'map_label'
                                        except IndexError:
                                            radar_logger.error(f"Failed to place character at ({pos_x}, {y})")

        # After processing
        label_count = np.sum(style_map == 'map_label')
        radar_logger.debug(f"Total label characters placed in map: {label_count}")

        radar_logger.debug(f"Processed features: {ways_count['highway']} highways, "
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
            projected = self._project_coords(coord[0], coord[1], center_lat, center_lon, width, height)
            if projected is not None:
                points.append(projected)
        
        if not points:
            return
        
        # Draw the boundary lines
        for i in range(len(points) - 1):
            x1, y1 = points[i]
            x2, y2 = points[i + 1]
            self._draw_line_segment(char_map, style_map, x1, y1, x2, y2, char, style)
        
        # Close the polygon if it's a fill feature
        if fill and len(points) > 2:
            x1, y1 = points[-1]
            x2, y2 = points[0]
            self._draw_line_segment(char_map, style_map, x1, y1, x2, y2, char, style)
            
            # Try multiple fill points for better coverage
            center_x = sum(p[0] for p in points) // len(points)
            center_y = sum(p[1] for p in points) // len(points)
            
            # Try center point first
            self._flood_fill_from_point(char_map, style_map, center_x, center_y, style)
            
            # If center didn't work, try points along the boundary
            if style_map[center_y, center_x] != style:
                for i in range(0, len(points), max(1, len(points) // 8)):
                    x, y = points[i]
                    if 0 <= x < width and 0 <= y < height:
                        self._flood_fill_from_point(char_map, style_map, x, y, style)

    def _flood_fill_from_point(self, char_map: np.ndarray, style_map: np.ndarray, 
                              start_x: int, start_y: int, style: str):
        """Flood fill starting from a specific point, handling viewport boundaries"""
        height, width = char_map.shape
        
        # If starting point is outside viewport or invalid, try to find a valid starting point
        if not (0 <= start_x < width and 0 <= start_y < height) or style_map[start_y, start_x] != 'map_background':
            # Try points along the boundary of the water body
            for y in range(height):
                for x in range(width):
                    # Look for points adjacent to water boundaries
                    if style_map[y, x] == 'map_background':
                        has_water_neighbor = False
                        for dx, dy in [(1,0), (-1,0), (0,1), (0,-1)]:
                            nx, ny = x + dx, y + dy
                            if (0 <= nx < width and 0 <= ny < height and 
                                style_map[ny, nx] == 'map_water'):
                                has_water_neighbor = True
                                break
                        if has_water_neighbor:
                            start_x, start_y = x, y
                            break
                if style_map[start_y, start_x] == 'map_background':
                    break
            else:
                return  # No valid fill points found
        
        # Use a queue for breadth-first fill (more efficient for large areas)
        queue = [(start_x, start_y)]
        seen = set()
        
        while queue:
            x, y = queue.pop(0)  # Use pop(0) for BFS behavior
            
            if (x, y) in seen:
                continue
            
            if not (0 <= x < width and 0 <= y < height):
                continue
            
            # Only fill background pixels that are bounded by water
            if style_map[y, x] != 'map_background':
                continue
            
            # Check if this point is bounded by water or existing fill
            has_water_boundary = False
            for dx, dy in [(1,0), (-1,0), (0,1), (0,-1)]:
                nx, ny = x + dx, y + dy
                if not (0 <= nx < width and 0 <= ny < height):
                    continue
                neighbor_style = style_map[ny, nx]
                if neighbor_style in ['map_water', 'map_water_fill']:
                    has_water_boundary = True
                    break
            
            if not has_water_boundary:
                continue
            
            # Fill this point
            char_map[y, x] = '~'
            style_map[y, x] = style
            seen.add((x, y))
            
            # Add neighboring points to queue
            for dx, dy in [(1,0), (-1,0), (0,1), (0,-1)]:
                nx, ny = x + dx, y + dy
                if (nx, ny) not in seen and 0 <= nx < width and 0 <= ny < height:
                    queue.append((nx, ny))

    def _is_valid_fill_point(self, char_map: np.ndarray, style_map: np.ndarray, x: int, y: int) -> bool:
        """Check if a point is valid for flood filling"""
        height, width = char_map.shape
        
        # Basic bounds check
        if not (0 <= x < width and 0 <= y < height):
            return False
        
        # Check if point is background (fillable)
        if style_map[y, x] != 'map_background':
            return False
        
        # Check if point is bounded by water features or blocked by land
        has_water_boundary = False
        for dx, dy in [(1,0), (0,1), (-1,0), (0,-1)]:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            
            neighbor_style = style_map[ny, nx]
            # If we hit a land boundary, this point is not valid for filling
            if neighbor_style in ['map_land', 'map_landuse']:
                return False
            # Check for water boundaries
            if neighbor_style in ['map_water', 'map_water_fill']:
                has_water_boundary = True
        
        return has_water_boundary

    def _draw_text(self, char_map: np.ndarray, style_map: np.ndarray, x: int, y: int, text: str, style: str):
        """Draw text on the character map with a background"""
        height, width = char_map.shape
        if 0 <= y < height:
            # Center the text
            start_x = max(0, x - len(text)//2)
            end_x = min(width, start_x + len(text))
            
            if start_x < width and end_x > 0:
                text_portion = text[max(0, -start_x):min(len(text), width-start_x)]
                radar_logger.debug(f"Drawing text '{text_portion}' at ({start_x}, {y})")
                
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

    def _draw_line_segment(self, char_map: np.ndarray, style_map: np.ndarray, 
                          x1: int, y1: int, x2: int, y2: int, char: str, style: str,
                          geo_coords: tuple = None):
        """Draw a line segment using Bresenham's algorithm with proper clipping"""
        height, width = char_map.shape
        
        # Determine if the line is vertical based on geographic coordinates if available
        line_char = char
        if geo_coords:
            lat1, lon1, lat2, lon2 = geo_coords
            # Compare longitude difference vs latitude difference to determine if vertical
            # Use a threshold to account for projection distortion
            d_lon = abs(lon2 - lon1)
            d_lat = abs(lat2 - lat1)
            is_vertical = d_lon < (d_lat * 0.7)  # Use 0.7 as threshold to favor vertical lines
            line_char = '|' if is_vertical else char
        
        # Cohen-Sutherland line clipping
        def compute_code(x, y):
            code = 0
            if x < 0: code |= 1        # Left
            if x >= width: code |= 2    # Right
            if y < 0: code |= 4        # Top
            if y >= height: code |= 8   # Bottom
            return code
        
        # Clip line to viewport
        code1 = compute_code(x1, y1)
        code2 = compute_code(x2, y2)
        
        while True:
            if not (code1 | code2):  # Both points inside viewport
                break
            elif code1 & code2:  # Both points outside viewport on same side
                return
            else:
                # Pick a point outside viewport
                code = code1 if code1 else code2
                
                # Find intersection point
                if code & 1:  # Left edge
                    y = y1 + (y2 - y1) * (0 - x1) / (x2 - x1)
                    x = 0
                elif code & 2:  # Right edge
                    y = y1 + (y2 - y1) * (width-1 - x1) / (x2 - x1)
                    x = width-1
                elif code & 4:  # Top edge
                    x = x1 + (x2 - x1) * (0 - y1) / (y2 - y1)
                    y = 0
                else:  # Bottom edge
                    x = x1 + (x2 - x1) * (height-1 - y1) / (y2 - y1)
                    y = height-1
                
                # Replace point outside viewport
                if code == code1:
                    x1, y1 = int(x), int(y)
                    code1 = compute_code(x1, y1)
                else:
                    x2, y2 = int(x), int(y)
                    code2 = compute_code(x2, y2)
        
        # Now draw the clipped line
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        steep = dy > dx
        
        # Store original coordinates for direction check
        orig_x1, orig_y1 = x1, y1
        orig_x2, orig_y2 = x2, y2
        
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
                if 0 <= y < width and 0 <= x < height:  # Only draw if in bounds
                    # Use original coordinates to determine character
                    char_map[x, y] = line_char
                    style_map[x, y] = style
            else:
                if 0 <= x < width and 0 <= y < height:  # Only draw if in bounds
                    char_map[y, x] = line_char
                    style_map[y, x] = style
            error -= dy
            if error < 0:
                y += y_step
                error += dx

    def _project_coords(self, lat: float, lon: float, center_lat: float, center_lon: float, 
                       width: int, height: int, degrees_per_pixel_lat=None, 
                       degrees_per_pixel_lon=None, tile_bounds=None) -> tuple:
        """Project geographic coordinates to pixel coordinates relative to center."""
        try:
            if tile_bounds:
                lat1, lon1, lat2, lon2 = tile_bounds
                # Project relative to center within the tile bounds
                x = int(width/2 + ((lon - center_lon) / (lon2 - lon1)) * width)
                y = int(height/2 + ((center_lat - lat) / (lat1 - lat2)) * height)
                
                # Scale based on zoom level
                if self.zoom != 11:  # Only adjust if not at base zoom
                    zoom_factor = 2 ** (11 - self.zoom)  # >1 for zoomed out, <1 for zoomed in
                    dx = x - width//2
                    dy = y - height//2
                    x = width//2 + int(dx / zoom_factor)
                    y = height//2 + int(dy / zoom_factor)
            else:
                # Adjust scale based on zoom level
                base_degrees = 0.1  # Base scale at zoom level 11
                zoom_diff = 11 - self.zoom  # Difference from base zoom
                DEGREES_PER_TILE = base_degrees * (2 ** zoom_diff)
                
                scale = width / DEGREES_PER_TILE
                x = width//2 + int((lon - center_lon) * scale)
                y = height//2 - int((lat - center_lat) * scale)
            
            return (x, y)
        except Exception as e:
            radar_logger.error(f"Projection error: {str(e)}")
            return None

    def render(self, size, focus=False):
        maxcol, maxrow = size
        result = []
        
        if self.radar_data is None or self.road_map is None:
            radar_logger.debug("No radar or road map data available")
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
            
            # Create a copy of the road map and style map for modification
            display_map = np.copy(self.road_map)
            display_style = np.copy(self.style_map)
            
            # First pass: Draw base features and radar, excluding roads and place names
            for y in range(scaled_height):
                for x in range(scaled_width):
                    if (display_style[y, x] == 'map_label' or 
                        display_style[y, x] == 'map_road'):
                        # Skip roads and place names in first pass
                        continue
                    
                    # Apply radar data if present
                    val = radar_data[y, x]
                    if val > 0.01:  # Keep minimum threshold to show any precipitation
                        display_style[y, x] = 'radar_' + (
                            'very_light' if val <= 0.08 else    # Very light rain/drizzle (0.01-0.08)
                            'light' if val <= 0.15 else         # Light rain (0.08-0.15)
                            'moderate' if val <= 0.3 else       # Moderate rain (0.15-0.3)
                            'heavy' if val <= 0.6 else          # Heavy rain (0.3-0.6)
                            'extreme'                           # Extreme precipitation (>0.6)
                        )
            
            # Second pass: Draw roads on top of radar
            for y in range(scaled_height):
                for x in range(scaled_width):
                    if self.style_map[y, x] == 'map_road':
                        display_map[y, x] = self.road_map[y, x]
                        display_style[y, x] = 'map_road'
            
            # Third pass: Draw place names on top of everything
            for y in range(scaled_height):
                for x in range(scaled_width):
                    if self.style_map[y, x] == 'map_label':
                        display_map[y, x] = self.road_map[y, x]
                        display_style[y, x] = 'map_label'
            
            # Create display lines
            for i in range(maxrow):
                line = []
                attrs = []
                
                for j in range(maxcol):
                    map_y = i - v_offset
                    map_x = j - h_offset
                    
                    if 0 <= map_y < scaled_height and 0 <= map_x < scaled_width:
                        map_char = display_map[map_y, map_x]
                        style = display_style[map_y, map_x]
                        attrs.append((style, 1))
                        line.append(map_char)
                    else:
                        attrs.append((None, 1))
                        line.append(' ')
                
                # Join the line and encode to utf-8
                line_str = ''.join(line).encode('utf-8')
                result.append((attrs, line_str))

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
            
            radar_logger.debug(f"Radar data shape: {self.radar_data.shape}")
            radar_logger.debug(f"Radar data range: {self.radar_data.min():.3f} to {self.radar_data.max():.3f}")
            
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
            radar_logger.error(f"Error updating radar: {str(e)}", exc_info=True)

    def _point_in_polygon(self, x: int, y: int, polygon: List[tuple]) -> bool:
        """Ray casting algorithm to determine if a point is inside a polygon"""
        if len(polygon) < 3:
            radar_logger.debug(f"Polygon has fewer than 3 points: {len(polygon)}")
            return False
        
        inside = False
        j = len(polygon) - 1
        
        try:
            for i in range(len(polygon)):
                if ((polygon[i][1] > y) != (polygon[j][1] > y) and
                    x < (polygon[j][0] - polygon[i][0]) * (y - polygon[i][1]) /
                        (polygon[j][1] - polygon[i][1]) + polygon[i][0]):
                    inside = not inside
                j = i
        except Exception as e:
            radar_logger.error(f"Point-in-polygon error at ({x}, {y}): {str(e)}")
            return False
        
        return inside

    def _get_element_coords(self, element: Dict, nodes: Dict, ways: Dict) -> List[tuple]:
        """Extract coordinates from an OSM element (way or relation)"""
        coords = []
        if element['type'] == 'way':
            coords = [nodes[ref] for ref in element['nodes'] if ref in nodes]
        elif element['type'] == 'relation':
            # Handle multipolygon relations
            outer_coords = []
            inner_coords = []
            
            for member in element.get('members', []):
                if member['type'] == 'way' and member['ref'] in ways:
                    way = ways[member['ref']]
                    way_coords = [nodes[ref] for ref in way['nodes'] if ref in nodes]
                    
                    # Outer ways form the boundary, inner ways form holes
                    if member.get('role') == 'inner':
                        inner_coords.extend(way_coords)
                    else:  # 'outer' or no role specified
                        outer_coords.extend(way_coords)
            
            # Use outer boundary coordinates
            if outer_coords:
                coords = outer_coords
                # TODO: Handle inner holes if needed in the future
        
        return coords

    def _project_coords_list(self, coords: List[tuple], center_lat: float, center_lon: float, 
                            width: int, height: int) -> List[tuple]:
        """Project a list of coordinates to screen space"""
        coords_2d = []
        for coord in coords:
            projected = self._project_coords(coord[0], coord[1], 
                                           center_lat, center_lon, 
                                           width, height)
            if projected is not None:
                coords_2d.append(projected)
        return coords_2d

    def _draw_map(self):
        # Example UTF-8 characters you could use:
        # '█' for solid blocks
        # '▒' for medium shade
        # '░' for light shade
        # '▓' for dark shade
        # '◉' for location marker
        # '○' for cities
        # '═' for roads
        # '║' for vertical roads
        # '╔╗╚╝' for corners
        
        # When creating the canvas:
        canvas = urwid.Canvas(
            [], 
            self.width, 
            self.height,
            encoding='utf-8'  # Specify UTF-8 encoding
        )
        
        # When adding text to canvas:
        canvas.text(x, y, '█', 'radar_heavy')  # Example using UTF-8 character

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

# Add these to the palette definition where other map styles are defined
PALETTE = [
    # ... existing styles ...
    ('map_urban', 'dark gray', 'default'),  # Urban areas
    ('map_nature', 'dark green', 'default'),  # Parks and forests
    # ... other styles ...
] 

def check_unicode_support():
    """Check if terminal supports Unicode characters we want to use"""
    try:
        '░♠'.encode(sys.stdout.encoding)
        return True
    except UnicodeEncodeError:
        return False 
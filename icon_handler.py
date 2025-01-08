import logging
from typing import List, Tuple

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
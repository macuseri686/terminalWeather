# TermWeather

A terminal-based weather application with an interactive UI, built using Python and urwid. Get current conditions, hourly forecasts, daily forecasts, and weather radar - all in your terminal!

![Screenshot from 2025-01-08 15-01-02](https://github.com/user-attachments/assets/cc694817-5962-4560-9e2a-d46641b33289)

## Features

- 📊 Current weather conditions with large ASCII art icons
- ⏰ Hourly forecast for the next 24 hours
- 📅 5-day weather forecast
- 🗺️ Weather radar display
- ⚙️ Configurable settings:
  - Location (by city name or ZIP code)
  - Units (metric/imperial)
  - Time format (12/24 hour)
- 🌈 Color-coded temperatures
- 🔄 Auto-refreshing data
- 🎨 Terminal UI with mouse support

## Prerequisites

- Python 3.6+
- OpenWeather API key ([Get one here](https://openweathermap.org/api))

## Installation

1. Clone the repository:
```bash
git clone https://github.com/macuseri686/terminalWeather.git 
cd terminalWeather
```

2. Install required packages:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file in the project directory:
```bash
OPENWEATHER_API_KEY=your_api_key_here
DEFAULT_ZIP=98272        # Optional: Default ZIP code
DEFAULT_CITY=London      # Optional: Default city
DEFAULT_STATE=           # Optional: Default state/province
DEFAULT_COUNTRY=US       # Optional: Default country code
UNITS=metric            # Optional: 'metric' or 'imperial'
TIME_FORMAT=24          # Optional: '12' or '24'
```

## Usage

Run the application:

```bash
python TermWeather.py
```

### Controls

- Use arrow keys or mouse to navigate
- Press `Enter` or click to select
- Click the ⚙️ icon or press `s` to access settings
- Press `q` to quit

### Settings

Access the settings menu to configure:
- API Key
- Location (City/State or ZIP code)
- Units (Metric/Imperial)
- Time Format (12/24 hour)

## Dependencies

- urwid
- requests
- python-dotenv
- Pillow
- numpy

## Troubleshooting

1. **API Key Issues**
   - New API keys may take up to 2 hours to activate
   - Verify your API key is 32 characters long
   - Check the weather_app.log file for detailed error messages

2. **Location Not Found**
   - Try using ZIP code instead of city name
   - For cities, include the country code (e.g., "London,UK")
   - Check spelling and formatting

3. **Display Issues**
   - Ensure your terminal supports Unicode characters
   - Try resizing your terminal window
   - Check terminal color support

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License

## Acknowledgments

- Weather data provided by [OpenWeather](https://openweathermap.org/)
- Built with [urwid](http://urwid.org/) terminal interface library

## Support

For support, please:
1. Check the weather_app.log file for error messages
2. Open an issue in the GitHub repository
3. Include relevant error messages and your configuration

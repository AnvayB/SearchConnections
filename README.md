# LinkedIn Connections Search Tool

A web-based search tool for exploring LinkedIn connections data from multiple sources.

## Features

- **Web Interface**: Modern, responsive web interface for easy searching
- **Real-time Search**: Instant search results with autocomplete suggestions
- **Multiple Data Sources**: Search across both Anvay's and Anil's LinkedIn connections
- **Filtered Results**: Anil's connections are filtered to show only close connections (Closeness 1.0 or 2.0)
- **Direct LinkedIn Links**: Click to view profiles directly on LinkedIn

## Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the Application**:
   ```bash
   python app.py
   ```

3. **Access the Web Interface**:
   Open your browser and go to: `http://localhost:8080`

## Usage

1. **Search by Company**: Enter a company name in the search box
2. **Autocomplete**: The interface will suggest company names as you type
3. **View Results**: Results are displayed in two sections:
   - Anvay's connections
   - Anil's close connections (filtered by closeness score)
4. **LinkedIn Profiles**: Click the "View" button to open LinkedIn profiles

## Data Files

The application expects the following CSV files in the `files/` directory:
- `anvay-connections.csv` - Anvay's LinkedIn connections
- `anil-connections.csv` - Anil's LinkedIn connections

## API Endpoints

- `GET /` - Main web interface
- `GET /search?company=<company_name>` - Search for connections by company
- `GET /companies` - Get list of all unique companies

## Features

- **Responsive Design**: Works on desktop and mobile devices
- **Modern UI**: Clean, professional interface with gradients and animations
- **Fast Search**: Optimized search with autocomplete
- **Data Statistics**: Shows count of results from each data source
- **Direct Links**: One-click access to LinkedIn profiles 
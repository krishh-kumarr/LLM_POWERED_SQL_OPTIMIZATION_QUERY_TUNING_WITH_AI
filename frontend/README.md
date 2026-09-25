# AI SQL Copilot - Frontend

Modern React frontend for AI SQL Copilot.

## Quick Start

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build
```

## Tech Stack

- **React 18** - UI framework
- **Vite** - Build tool and dev server
- **Tailwind CSS** - Utility-first CSS
- **Axios** - HTTP client
- **Recharts** - Charts and visualizations
- **Lucide React** - Icon library

## Project Structure

- `src/App.jsx` - Main application component
- `src/components/` - React components
  - `DatabaseConnect.jsx` - Database connection form
  - `QueryAssistant.jsx` - Natural language query input
  - `ResultsDashboard.jsx` - Results and visualizations
- `src/api/apiClient.js` - API client with Axios

## Components

### DatabaseConnect
Form for connecting to SQLite, MySQL, or PostgreSQL databases.

### QueryAssistant
Natural language input interface with example queries and AI-powered SQL generation.

### ResultsDashboard
Tabbed interface showing:
- Overview with quick stats
- Generated and optimized SQL queries
- Performance comparison charts
- Optimization suggestions and issues

## API Integration

All API calls use Axios with automatic error handling and request/response interceptors.

## Styling

Tailwind CSS with custom configuration:
- Dark theme by default
- Custom color palette
- Responsive design
- Custom components (cards, buttons, inputs)

## Scripts

- `npm run dev` - Start development server (port 5173)
- `npm run build` - Build for production
- `npm run preview` - Preview production build

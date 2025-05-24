# React Frontend

This directory contains the React application that interacts with the FastAPI backend.

## Development

1. Install dependencies (requires Node.js and npm):
   ```bash
   npm install
   ```
2. Start the development server:
   ```bash
   npm run dev
   ```
3. The app expects the backend to run at the URL defined in a `.env` file (see `.env.example`) via `VITE_API_BASE_URL`.

## Production Build

Build the optimized production bundle with:
```bash
npm run build
```
The output will be generated in the `dist/` directory and can be served by FastAPI or any static file server.

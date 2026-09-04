# Vector dashboard

The React/Vinext dashboard for the Vector paper-trading system.

```powershell
npm ci
$env:NEXT_PUBLIC_API_URL="http://localhost:8000"
npm run dev
```

Use `npm run build` for a production build and `npm test` for the frontend verification suite. The dashboard connects to the FastAPI REST and WebSocket interfaces documented in the root README.

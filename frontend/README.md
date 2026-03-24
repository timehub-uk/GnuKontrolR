# frontend/

React 18 single-page application — the GnuKontrolR control panel UI.
Built with Vite + Tailwind CSS.

## Structure

```
frontend/
├── index.html
├── vite.config.js       Dev server + proxy to localhost:8000
├── tailwind.config.js
└── src/
    ├── main.jsx         React entry point
    ├── App.jsx          Router (React Router v6) + AuthContext provider
    ├── index.css        Global styles + Tailwind directives
    ├── pages/           Full-page components (one per panel section)
    ├── components/      Reusable UI components
    │   ├── Layout.jsx        Sidebar + topbar shell
    │   ├── Toggle.jsx        On/off switch
    │   ├── SmartInput.jsx    Input with live validation + autocomplete
    │   ├── SecurityAdvisor.jsx  Live security check panel (WS)
    │   ├── ConfigBackupsPanel.jsx  Config snapshot browser
    │   └── EventIdBadge.jsx  Shows UUID event ID for tracing errors
    ├── hooks/
    │   ├── useDebounce.js    Debounce any value
    │   ├── useLiveCheck.js   Poll an API endpoint on a timer
    │   ├── useLiveValidation.js  Validate input against API in real-time
    │   └── useAutoSuggest.js     Autocomplete suggestions from API
    ├── context/
    │   └── AuthContext.jsx   Token storage, user state, login/logout
    └── utils/
        ├── api.js       Axios instance — auto-attaches Bearer token +
        │                UUID X-Request-ID on every request
        ├── ws.js        WebSocket connection helper (auto-reconnect)
        └── pageCache.js Simple client-side page data cache
```

## Dev server

```bash
cd frontend
npm install
npm run dev        # Vite dev server on localhost:5173
                   # Proxies /api and /ws to localhost:8000
```

## Production build

```bash
npm run build      # outputs to frontend/dist/
```

The FastAPI backend serves `frontend/dist/` as a static SPA fallback.

## Request tracing

Every API call is stamped with a UUID `X-Request-ID`. The server echoes it back.
`api.lastEventId` always holds the most recent event ID so it can be shown in
error dialogs (`<EventIdBadge />`) for easy log correlation.

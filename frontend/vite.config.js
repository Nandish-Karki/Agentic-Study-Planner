import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
// VITE_API_URL points the SPA at the FastAPI backend (default localhost:8000).
export default defineConfig({
    plugins: [react()],
    server: { port: 5173 },
});

# Graxia OS Architecture

Graxia OS operates as a comprehensive personal sovereign OS with a unified control plane. 

## System Workflow

1. **Frontend (React)**: The canonical UI for operators, offering dashboards for leads, approval queues, opportunities, and metric visualizations. It communicates with the backend via REST and WebSockets.
2. **Backend (FastAPI)**: Manages business logic, coordinates AI agents, interfaces with the database (Supabase/PostgreSQL), and schedules background tasks.
3. **Database (Supabase/PostgreSQL)**: The primary source of truth for all entities (contacts, drafts, jobs, email threads, opportunities).
4. **Configuration & Scripts**: 
   - `config/`: Houses operational configurations for Docker, Redis, and process managers like PM2.
   - `scripts/`: Operational scripts for database migrations, deployments, and utility tasks.
5. **Agents & External Integrations**: Integrates with external APIs (like n8n, OpenAI) to perform autonomous data gathering and drafting. Human operators approve critical actions before they are executed.

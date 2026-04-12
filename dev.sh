#!/bin/bash
# BravOS Development Server Launcher
# Starts both Backend (FastAPI) and Frontend (Vite) in parallel

echo "=== BravOS Development Environment ==="
echo ""

# Activate Python venv
if [ ! -z "$VIRTUAL_ENV" ]; then
    echo "Activating Python virtual environment..."
    source ./backend/.venv/bin/activate
fi

# Install frontend dependencies if needed
if [ ! -d "./frontend/node_modules" ]; then
    echo "Installing frontend dependencies..."
    cd frontend
    bun install
    cd ..
fi

# Start Backend
echo "Starting Backend (FastAPI)..."
cd backend
python -m uvicorn app.main:app --reload --port 8000 &
BACKEND_PID=$!
cd ..

# Wait a moment for backend to start
sleep 2

# Start Frontend
echo "Starting Frontend (Vite)..."
cd frontend
bun run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo "=== Services Starting ==="
echo "Backend:  http://localhost:8000"
echo "Frontend: http://localhost:5173"
echo "Docs:     http://localhost:8000/docs"
echo ""
echo "Backend PID:  $BACKEND_PID"
echo "Frontend PID: $FRONTEND_PID"
echo ""
echo "Press Ctrl+C to stop all services"
echo ""

# Wait for both processes
wait

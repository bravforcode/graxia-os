module.exports = {
  apps: [
    {
      name: 'bravos-backend',
      script: 'C:/brav os/backend/.venv/Scripts/python.exe',
      args: '-m uvicorn app.main:app --host 0.0.0.0 --port 8000',
      cwd: 'C:/brav os/backend',
      interpreter: 'none'
    },
    {
      name: 'bravos-frontend',
      script: 'C:/Users/menum/.bun/bin/bun.exe',
      args: 'run dev',
      cwd: 'C:/brav os/frontend',
      interpreter: 'none'
    }
  ]
};

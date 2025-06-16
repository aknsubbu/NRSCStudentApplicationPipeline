module.exports = {
  apps: [
    {
      name: "ai-server",
      script: "servers/ai/server.py",
      interpreter: "python3",
      watch: ["servers/ai"],
      env: {
        PORT: 8003,
        NODE_ENV: "production",
      },
      max_memory_restart: "1G",
      exp_backoff_restart_delay: 100,
    },
    {
      name: "manager-server",
      script: "servers/manager/main.py",
      interpreter: "python3",
      watch: ["servers/manager"],
      env: {
        PORT: 8004,
        NODE_ENV: "production",
      },
      max_memory_restart: "1G",
      exp_backoff_restart_delay: 100,
    },
    {
      name: "email-out-server",
      script: "servers/emails/out/main.py",
      interpreter: "python3",
      watch: ["servers/emails/out"],
      env: {
        PORT: 8001,
        NODE_ENV: "production",
      },
      max_memory_restart: "1G",
      exp_backoff_restart_delay: 100,
    },
    {
      name: "email-in-server",
      script: "servers/emails/in/main.py",
      interpreter: "python3",
      watch: ["servers/emails/in"],
      env: {
        PORT: 8002,
        NODE_ENV: "production",
      },
      max_memory_restart: "1G",
      exp_backoff_restart_delay: 100,
    },
    {
      name: "db-server",
      script: "servers/db/main.py",
      interpreter: "python3",
      watch: ["servers/db"],
      env: {
        PORT: 8000,
        NODE_ENV: "production",
      },
      max_memory_restart: "1G",
      exp_backoff_restart_delay: 100,
    },
  ],

  deploy: {
    production: {
      user: "SSH_USERNAME",
      host: "SSH_HOSTMACHINE",
      ref: "origin/master",
      repo: "GIT_REPOSITORY",
      path: "DESTINATION_PATH",
      "pre-deploy-local": "",
      "post-deploy":
        "npm install && pm2 reload ecosystem.config.js --env production",
      "pre-setup": "",
    },
  },
};

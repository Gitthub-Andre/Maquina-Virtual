module.exports = {
    apps: [{
      name: "file-server",
      script: "src/server.js",
      env: {
        NODE_ENV: "production",
      },
      max_memory_restart: "300M"
    }]
  }
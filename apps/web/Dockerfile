FROM node:20-alpine

WORKDIR /app

COPY apps/web/package*.json ./
RUN npm install

COPY apps/web/ ./

# Create entrypoint script to inject Codespaces config at runtime
RUN cat > /entrypoint.sh << 'EOF'
#!/bin/sh
set -e

# Inject Codespaces config into a global JS variable for the frontend
if [ -n "$CODESPACE_NAME" ] && [ -n "$GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN" ]; then
  cat > /app/public/codespace-config.js << EOC
window.__CODESPACE_CONFIG__ = {
  codespaceName: "$CODESPACE_NAME",
  forwardingDomain: "$GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN"
};
EOC
else
  # Create empty config if not in Codespaces
  cat > /app/public/codespace-config.js << EOC
window.__CODESPACE_CONFIG__ = {};
EOC
fi

# Start Next.js
exec "$@"
EOF
RUN chmod +x /entrypoint.sh

EXPOSE 3000

ENTRYPOINT ["/entrypoint.sh"]
CMD ["npm", "run", "dev", "--", "-H", "0.0.0.0", "-p", "3000"]
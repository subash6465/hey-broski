/** @type {import('next').NextConfig} */
const { existsSync } = require('node:fs')
const { resolve } = require('node:path')
const { loadEnvConfig } = require('@next/env')

// Native development shares the repository-root .env with the Python API.
// Docker builds have no root .env; Compose supplies runtime overrides instead.
const repoRoot = resolve(__dirname, '../..')
if (existsSync(resolve(repoRoot, '.env'))) {
  loadEnvConfig(repoRoot, process.env.NODE_ENV !== 'production')
}

const nextConfig = {
  reactStrictMode: true,
  output: 'standalone',
}

module.exports = nextConfig

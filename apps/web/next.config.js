/** @type {import('next').NextConfig} */
const apiInternalBaseUrl =
  process.env.API_INTERNAL_BASE_URL ||
  process.env.API_BASE_URL ||
  process.env.HEYBROSKI_API_BASE_URL ||
  'http://localhost:8000'

const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${apiInternalBaseUrl}/api/:path*`,
      },
    ]
  },
}

module.exports = nextConfig
